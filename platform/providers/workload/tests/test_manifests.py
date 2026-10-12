import pytest

from workload_provider.manifests import NAMESPACE, UnsupportedSpec, render

DIGEST = "sha256:" + "b" * 64


def revision(replicas=None, instance="reviews"):
  spec = {"environment": "demo", "instance": instance, "component": "reviews", "revision": 3, "action": "deploy", "version": "2.1.0", "image": "ghcr.io/acme/reviews", "digest": DIGEST}
  if replicas is not None:
    spec["overrides"] = {"replicas": replicas}
  return {"metadata": {"name": f"demo.{instance}.3"}, "spec": spec}


def score(**extra):
  return {
    "apiVersion": "score.dev/v1b1",
    "metadata": {"name": "reviews"},
    "containers": {"api": {
      "image": ".",
      "variables": {"APP_NAME": "${metadata.name}", "LITERAL": "$${HOME}"},
      "resources": {"limits": {"memory": "128Mi"}},
      "readinessProbe": {"httpGet": {"path": "/healthz", "port": 8000}},
    }},
    "service": {"ports": {"http": {"port": 80, "targetPort": 8000}}},
    **extra,
  }


def test_deployment_and_service():
  objects, url = render(score(), revision(replicas=2))
  namespace, deployment, service = objects
  assert namespace["metadata"]["name"] == NAMESPACE
  assert deployment["spec"]["replicas"] == 2
  assert deployment["spec"]["progressDeadlineSeconds"] == 120
  container = deployment["spec"]["template"]["spec"]["containers"][0]
  assert container["image"] == f"ghcr.io/acme/reviews@{DIGEST}"
  assert container["env"] == [{"name": "APP_NAME", "value": "reviews"}, {"name": "LITERAL", "value": "${HOME}"}]
  assert container["readinessProbe"] == {"httpGet": {"path": "/healthz", "port": 8000}}
  assert service["spec"]["ports"] == [{"name": "http", "port": 80, "targetPort": 8000, "protocol": "TCP"}]
  assert url == "http://reviews.apps:80"


def test_selector_carries_the_instance():
  objects, _ = render(score(), revision(instance="reviews-pr-42"))
  selector = {"app.kubernetes.io/name": "reviews", "app.kubernetes.io/instance": "reviews-pr-42"}
  assert objects[1]["spec"]["selector"]["matchLabels"] == selector
  assert objects[2]["spec"]["selector"] == selector
  assert objects[1]["metadata"]["name"] == objects[2]["metadata"]["name"] == "reviews-pr-42"


def test_one_replica_and_no_service_by_default():
  spec = score()
  del spec["service"]
  objects, url = render(spec, revision())
  assert [obj["kind"] for obj in objects] == ["Namespace", "Deployment"]
  assert objects[1]["spec"]["replicas"] == 1
  assert url is None


BOUND = {"db": {"outputs": {"host": "reviews-db.apps", "port": 5432, "name": "app"}, "secretRef": {"name": "reviews-db", "keys": ["password"]}}}


def with_db(**variables):
  spec = score(resources={"db": {"type": "postgres"}})
  spec["containers"]["api"]["variables"] = variables
  return spec


def test_resource_outputs_and_secrets():
  objects, _ = render(with_db(DB_URL="postgres://${resources.db.host}:${resources.db.port}/${resources.db.name}", DB_PASSWORD="${resources.db.password}"), revision(), BOUND)
  env = objects[1]["spec"]["template"]["spec"]["containers"][0]["env"]
  assert env == [
    {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "reviews-db", "key": "password"}}},
    {"name": "DB_URL", "value": "postgres://reviews-db.apps:5432/app"},
  ]


@pytest.mark.parametrize("variables,message", [
  ({"DSN": "user:${resources.db.password}"}, "is a secret: only accepted as the whole value of a variable"),
  ({"HOST": "${resources.db.unknown}"}, "resources.db.unknown} cannot be resolved"),
  ({"HOST": "${resources.cache.host}"}, "resources.cache.host} cannot be resolved"),
])
def test_resource_placeholders_refused(variables, message):
  with pytest.raises(UnsupportedSpec, match=message):
    render(with_db(**variables), revision(), BOUND)


def test_a_secret_never_reaches_args():
  spec = with_db()
  spec["containers"]["api"]["args"] = ["--password", "${resources.db.password}"]
  with pytest.raises(UnsupportedSpec, match="args"):
    render(spec, revision(), BOUND)


@pytest.mark.parametrize("change,message", [
  (lambda s: s["containers"]["api"].update(files=[{"target": "/x"}]), "containers.api: files"),
  (lambda s: s["containers"]["api"].update(livenessProbe={"exec": {"command": ["true"]}}), "livenessProbe: exec"),
  (lambda s: s["containers"]["api"]["variables"].update(DB="${resources.db.host}"), "resources.db.host"),
  (lambda s: s["service"]["ports"]["http"].update(nodePort=30000), "nodePort"),
  (lambda s: s.update(extensions={}), "extensions"),
  (lambda s: s.update(containers={}), "at least one container"),
])
def test_unsupported_spec(change, message):
  spec = score()
  change(spec)
  with pytest.raises(UnsupportedSpec, match=message):
    render(spec, revision())


def test_namespace_has_sidecar_injection():
  # ADR 0035: the mesh of the environment routes between the instances of a component.
  objects, _ = render(score(), revision())
  assert objects[0]["metadata"]["labels"]["istio-injection"] == "enabled"

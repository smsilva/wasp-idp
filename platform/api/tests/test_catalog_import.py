import pytest

from platform_api.catalog_import import classify, owner_of


def doc(kind, name="x", spec=None, api_version="backstage.io/v1alpha1", **metadata):
  return {"apiVersion": api_version, "kind": kind, "metadata": {"name": name, **metadata}, "spec": {} if spec is None else spec}


def test_domain_with_subdomain_owner_and_description():
  item = classify("c.yaml#2", doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}, description="Messages"))
  assert (item.action, item.kind, item.name, item.source) == (None, "Domain", "messaging", "c.yaml#2")
  assert item.spec == {"owner": "team-alpha", "parent": "communication", "description": "Messages"}


def test_system_and_resource_fields():
  assert classify("s", doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging"})).spec == {"owner": "team-alpha", "domain": "messaging"}
  resource = classify("r", doc("Resource", "greeting-db", {"owner": "team-alpha", "system": "greeter", "type": "database"}))
  assert resource.spec == {"owner": "team-alpha", "system": "greeter", "type": "database"}


def test_backstage_only_fields_are_ignored():
  item = classify("s", doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging", "lifecycle": "production", "dependsOn": ["x"]}, tags=["a"], links=[]))
  assert item.action is None
  assert item.spec == {"owner": "team-alpha", "domain": "messaging"}


@pytest.mark.parametrize("value,expected", [
  ("group:default/team-alpha", "team-alpha"),
  ("group:team-alpha", "team-alpha"),
  ("Group:default/team-alpha", "team-alpha"),
  ("default/team-alpha", "team-alpha"),
  ("team-alpha", "team-alpha"),
  (None, None),
])
def test_owner_of(value, expected):
  assert owner_of(value) == expected


@pytest.mark.parametrize("owner,reason", [
  ("user:default/silvio", "'user:default/silvio' is not a group: the owner of a catalog entity is a team"),
  ("group:acme/team-alpha", "'group:acme/team-alpha': namespace 'acme' is not supported, only 'default'"),
  (42, "must be text"),
])
def test_invalid_owner_is_error(owner, reason):
  item = classify("s", doc("System", "greeter", {"owner": owner, "domain": "messaging"}))
  assert (item.action, item.field, item.reason) == ("error", "spec.owner", reason)


@pytest.mark.parametrize("document,reason", [
  ({"site_name": "communication"}, "not a Backstage entity"),
  (["a", "b"], "not a Backstage entity"),
  ("text", "not a Backstage entity"),
  (doc("System", api_version="example.com/v1"), "not a Backstage entity"),
  (doc("Component"), "lives in the repo catalog-info.yaml"),
  (doc("API"), "lives in the repo catalog-info.yaml"),
  (doc("Group"), "identity lives in Keycloak (#186)"),
  (doc("User"), "identity lives in Keycloak (#186)"),
  (doc("Template"), "Backstage configuration, not a catalog entity"),
  (doc("Location"), "Backstage configuration, not a catalog entity"),
  (doc("Widget"), "not a catalog kind"),
  (doc("System", namespace="acme"), "namespace 'acme': the platform catalog has no namespaces"),
])
def test_skips(document, reason):
  item = classify("f.yaml#1", document)
  assert (item.action, item.reason) == ("skip", reason)


def test_skip_keeps_kind_and_name_when_present():
  item = classify("o.yaml#1", doc("Group", "team-alpha"))
  assert (item.kind, item.name) == ("Group", "team-alpha")
  assert classify("m.yml#1", {"site_name": "x"}).view() == {"kind": None, "name": None, "action": "skip", "source": "m.yml#1", "reason": "not a Backstage entity"}


@pytest.mark.parametrize("document,field,reason", [
  ({"apiVersion": "backstage.io/v1alpha1", "kind": "System", "metadata": {}, "spec": {}}, "metadata.name", "required"),
  (doc("System", 123, {"owner": "team-alpha", "domain": "d"}), "metadata.name", "must be text"),
  ({"apiVersion": "backstage.io/v1alpha1", "kind": "System", "metadata": {"name": "greeter"}}, "spec", "required"),
  (doc("System", "Greeter", {"owner": "team-alpha", "domain": "d"}), "metadata.name", "lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters"),
  (doc("System", "greeter", {"domain": "d"}), "spec.owner", "required for system"),
  (doc("System", "greeter", {"owner": "team-alpha"}), "spec.domain", "required for system: declare the domain in the file"),
  (doc("Resource", "db", {"owner": "team-alpha", "system": "greeter"}), "spec.type", "required for resource"),
  (doc("Resource", "db", {"owner": "team-alpha", "type": "database"}), "spec.system", "required for resource: declare the system in the file"),
  (doc("Domain", "d", {"owner": "team-alpha", "subdomainOf": "Bad Name"}), "spec.subdomainOf", "lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters"),
])
def test_errors_name_the_backstage_field(document, field, reason):
  item = classify("f.yaml#1", document)
  assert (item.action, item.field, item.reason) == ("error", field, reason)

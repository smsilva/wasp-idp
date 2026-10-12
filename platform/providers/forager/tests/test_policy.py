from forager_provider.policy import resolve


def policy(name, items, environment=None, profile=None):
  spec = {"provisioners": items}
  if environment:
    spec["environment"] = environment
  if profile:
    spec["profile"] = profile
  return {"metadata": {"name": name}, "spec": spec}


DEFAULT = policy("platform-default", [{"type": "postgres", "mode": "provision"}])


def test_platform_default():
  assert resolve([DEFAULT], "demo", "postgres")["mode"] == "provision"


def test_environment_layer_wins_over_the_default():
  env = policy("demo", [{"type": "postgres", "mode": "compose"}], environment="demo")
  assert resolve([DEFAULT, env], "demo", "postgres")["mode"] == "compose"
  # Another environment's policy is not a layer of this one.
  assert resolve([DEFAULT, env], "other", "postgres")["mode"] == "provision"


def test_class_needs_an_item_with_that_class():
  restored = policy("demo", [{"type": "postgres", "class": "restored", "mode": "bind"}], environment="demo")
  assert resolve([DEFAULT, restored], "demo", "postgres", klass="restored")["mode"] == "bind"
  # Without the class, the item with class is skipped; a class nobody offers resolves nothing.
  assert resolve([DEFAULT, restored], "demo", "postgres")["mode"] == "provision"
  assert resolve([DEFAULT], "demo", "postgres", klass="restored") is None


def test_id_narrows_an_item():
  shared = policy("demo", [{"type": "postgres", "id": "orders-db", "mode": "compose"}], environment="demo")
  assert resolve([DEFAULT, shared], "demo", "postgres", resource_id="orders-db")["mode"] == "compose"
  assert resolve([DEFAULT, shared], "demo", "postgres", resource_id="other")["mode"] == "provision"


def test_order_by_name_then_position():
  first = policy("a", [{"type": "postgres", "mode": "bind"}, {"type": "postgres", "mode": "compose"}], environment="demo")
  second = policy("b", [{"type": "postgres", "mode": "provision"}], environment="demo")
  assert resolve([second, first], "demo", "postgres")["mode"] == "bind"


def test_unknown_type():
  assert resolve([DEFAULT], "demo", "dns") is None


EPHEMERAL = policy("profile-ephemeral", [{"type": "postgres", "mode": "compose", "params": {"instance": "shared-pg"}}], profile="ephemeral")


def test_profile_layer_between_the_environment_and_the_default():
  assert resolve([DEFAULT, EPHEMERAL], "demo", "postgres", profile="ephemeral")["mode"] == "compose"
  # Another profile's policy is not a layer of this environment, and neither is it without a profile.
  assert resolve([DEFAULT, EPHEMERAL], "demo", "postgres", profile="shared")["mode"] == "provision"
  assert resolve([DEFAULT, EPHEMERAL], "demo", "postgres")["mode"] == "provision"
  env = policy("env-demo", [{"type": "postgres", "mode": "provision"}], environment="demo")
  assert resolve([EPHEMERAL, env, DEFAULT], "demo", "postgres", profile="ephemeral")["mode"] == "provision"


def test_a_profile_policy_is_not_the_platform_default():
  # Without spec.environment but with spec.profile: never part of the platform layer.
  assert resolve([EPHEMERAL], "demo", "postgres") is None

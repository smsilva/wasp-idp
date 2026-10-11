import pytest
from pydantic import ValidationError

from fakes import FakeState
from platform_api.catalog import (
  CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, dependents, manifest, spec_from, view,
)
from platform_api.environments import is_owner_or_admin
from platform_api.state import Conflict, NotFound

DOMAINS, SYSTEMS, RESOURCES = KINDS["domains"], KINDS["systems"], KINDS["resources"]


def test_kinds_point_to_their_parent():
  assert (DOMAINS.parent_field, DOMAINS.parent_plural, DOMAINS.parent_required) == ("parent", "domains", False)
  assert (SYSTEMS.parent_field, SYSTEMS.parent_plural, SYSTEMS.parent_required) == ("domain", "domains", True)
  assert (RESOURCES.parent_field, RESOURCES.parent_plural, RESOURCES.required) == ("system", "systems", ("type",))
  assert list(KINDS) == ["domains", "systems", "resources"]


def test_spec_keeps_only_given_fields():
  request = EntityRequest(name="messaging", owner="team-alpha", parent="communication")
  assert spec_from(DOMAINS, request) == {"owner": "team-alpha", "parent": "communication"}


def test_spec_rejects_field_of_other_kind():
  with pytest.raises(InvalidRequest, match="type: not a field of domain"):
    spec_from(DOMAINS, EntityRequest(name="communication", owner="team-alpha", type="database"))
  with pytest.raises(InvalidRequest, match="parent: not a field of system"):
    spec_from(SYSTEMS, EntityRequest(name="greeter", owner="team-alpha", domain="messaging", parent="x"))


def test_spec_requires_parent_and_type():
  with pytest.raises(InvalidRequest, match="domain: required for system"):
    spec_from(SYSTEMS, EntityRequest(name="greeter", owner="team-alpha"))
  with pytest.raises(InvalidRequest, match="type, system: required for resource"):
    spec_from(RESOURCES, EntityRequest(name="greeting-db", owner="team-alpha"))


@pytest.mark.parametrize("field,value", [("name", "Greeter"), ("owner", "group:default/team-alpha"), ("name", "-x"), ("name", "a" * 64), ("name", "greeter\n"), ("owner", "team-alpha\n")])
def test_request_rejects_invalid_labels(field, value):
  fields = {"name": "greeter", "owner": "team-alpha", field: value}
  with pytest.raises(ValidationError):
    EntityRequest(**fields)


def test_request_rejects_unknown_fields():
  with pytest.raises(ValidationError):
    EntityRequest(name="greeter", owner="team-alpha", lifecycle="production")


def test_manifest_and_view():
  body = manifest(SYSTEMS, "greeter", {"owner": "team-alpha", "domain": "messaging"}, "user-1")
  assert body["apiVersion"] == "catalog.platform.wasp.silvios.me/v1alpha1"
  assert body["kind"] == "System"
  assert body["metadata"] == {"name": "greeter", "annotations": {CREATED_BY_ANNOTATION: "user-1"}}
  obj = {**body, "metadata": {**body["metadata"], "creationTimestamp": "2026-10-10T00:00:00Z"}}
  assert view(SYSTEMS, obj) == {
    "kind": "System", "name": "greeter", "owner": "team-alpha", "description": None,
    "domain": "messaging", "createdAt": "2026-10-10T00:00:00Z",
  }
  resource = manifest(RESOURCES, "greeting-db", {"owner": "team-alpha", "type": "database", "system": "greeter"}, "user-1")
  assert view(RESOURCES, resource)["type"] == "database"


def test_dependents_cover_subdomains_and_systems():
  state = FakeState()
  state.create("domains", manifest(DOMAINS, "communication", {"owner": "a"}, "u"))
  state.create("domains", manifest(DOMAINS, "messaging", {"owner": "a", "parent": "communication"}, "u"))
  state.create("systems", manifest(SYSTEMS, "notifier", {"owner": "a", "domain": "communication"}, "u"))
  state.create("systems", manifest(SYSTEMS, "greeter", {"owner": "a", "domain": "messaging"}, "u"))
  state.create("resources", manifest(RESOURCES, "greeting-db", {"owner": "a", "type": "database", "system": "greeter"}, "u"))
  assert dependents(state, DOMAINS, "communication") == ["domain/messaging", "system/notifier"]
  assert dependents(state, DOMAINS, "messaging") == ["system/greeter"]
  assert dependents(state, SYSTEMS, "greeter") == ["resource/greeting-db"]
  assert dependents(state, RESOURCES, "greeting-db") == []


def test_is_owner_or_admin_reads_the_given_annotation():
  class P:
    sub, groups = "user-1", ["platform-users"]

  obj = {"metadata": {"annotations": {CREATED_BY_ANNOTATION: "user-1"}}}
  assert is_owner_or_admin(obj, P(), CREATED_BY_ANNOTATION)
  assert not is_owner_or_admin(obj, P())


def test_spec_from_names_missing_fields():
  with pytest.raises(InvalidRequest) as raised:
    spec_from(KINDS["resources"], EntityRequest(name="db", owner="team-alpha"))
  assert raised.value.fields == ["type", "system"]
  assert str(raised.value) == "type, system: required for resource"


def test_fake_replace_checks_resource_version():
  state = FakeState()
  created = state.create("systems", {"metadata": {"name": "greeter"}, "spec": {"owner": "team-alpha", "domain": "messaging"}})
  replaced = state.replace("systems", {**created, "spec": {"owner": "team-beta", "domain": "messaging"}})
  assert replaced["spec"]["owner"] == "team-beta"
  assert replaced["metadata"]["uid"] == created["metadata"]["uid"]
  with pytest.raises(Conflict):
    state.replace("systems", {**created, "spec": {"owner": "team-gamma", "domain": "messaging"}})
  with pytest.raises(NotFound):
    state.replace("systems", {"metadata": {"name": "nope", "resourceVersion": "1"}, "spec": {}})

import pytest

from fakes import CATALOG_TEAMS, FakeState
from platform_api.auth import Principal
from platform_api.catalog import KINDS, manifest
from platform_api.catalog_import import classify, make_plan, owner_of


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
  (doc("Component"), "lives in the repo catalog-info.yaml; indexed by discovery (#205)"),
  (doc("API"), "lives in the repo catalog-info.yaml; indexed by discovery (#205)"),
  (doc("User"), "users live in Keycloak: they sign in, never imported"),
  (doc("Template"), "a template needs apiVersion scaffolder.backstage.io/v1beta3"),
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

TEAMS = set(CATALOG_TEAMS)
ADMIN = Principal("admin-1", None, ["platform-admins"])
USER = Principal("user-1", "dev@example.com", ["platform-users"])
OTHER = Principal("user-2", "other@example.com", ["platform-users"])


def sourced(*documents):
  return [{"source": f"t.yaml#{index}", "document": document} for index, document in enumerate(documents, 1)]


def seed(state, plural, name, spec, created_by="admin-1"):
  state.create(plural, manifest(KINDS[plural], name, spec, created_by))


def actions(plan):
  return [(item.kind, item.name, item.action) for item in plan.items]


COMMUNICATION = [
  doc("Resource", "greeting-db", {"owner": "group:default/team-alpha", "system": "greeter", "type": "database"}),
  doc("System", "greeter", {"owner": "group:default/team-alpha", "domain": "messaging"}),
  doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}),
  doc("Domain", "communication", {"owner": "group:default/team-alpha"}),
  doc("Group", "team-alpha"),
]


def test_parents_first_regardless_of_file_order():
  plan = make_plan(sourced(*COMMUNICATION), FakeState(), ADMIN, TEAMS)
  assert actions(plan) == [
    ("Group", "team-alpha", "unchanged"),
    ("Domain", "communication", "create"),
    ("Domain", "messaging", "create"),
    ("System", "greeter", "create"),
    ("Resource", "greeting-db", "create"),
  ]
  assert plan.view(applied=False)["summary"] == {"create": 4, "update": 0, "unchanged": 1, "skip": 0, "forbidden": 0, "error": 0}


def test_unchanged_and_update_with_changes():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "messaging", {"owner": "team-beta", "parent": "communication", "description": "old"})
  plan = make_plan(sourced(COMMUNICATION[3], COMMUNICATION[2]), state, ADMIN, TEAMS)
  assert actions(plan) == [("Domain", "communication", "unchanged"), ("Domain", "messaging", "update")]
  assert plan.items[1].view()["changes"] == {"description": ["old", None], "owner": ["team-beta", "team-alpha"]}
  assert "spec" not in plan.items[0].view()


def test_update_can_move_to_another_parent():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "bookstore", {"owner": "team-alpha"})
  seed(state, "systems", "greeter", {"owner": "team-alpha", "domain": "communication"})
  plan = make_plan(sourced(doc("System", "greeter", {"owner": "team-alpha", "domain": "bookstore"})), state, ADMIN, TEAMS)
  assert plan.items[0].changes == {"domain": ["communication", "bookstore"]}


def test_parent_found_in_the_platform():
  state = FakeState()
  seed(state, "domains", "messaging", {"owner": "team-alpha"})
  plan = make_plan(sourced(COMMUNICATION[1]), state, USER, TEAMS)
  assert actions(plan) == [("System", "greeter", "create")]


def test_broken_reference_names_entity_and_field():
  plan = make_plan(sourced(doc("System", "orphan", {"owner": "team-alpha", "domain": "nowhere"})), FakeState(), ADMIN, TEAMS)
  item = plan.items[0]
  assert (item.action, item.field, item.reason) == ("error", "spec.domain", "domain 'nowhere' not found")
  assert plan.blocked


def test_children_of_an_unimportable_parent_cascade():
  documents = sourced(
    doc("Domain", "messaging", {"owner": "team-alpha", "subdomainOf": "communication"}),
    doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging"}),
    doc("Domain", "communication", {}),  # no owner: error
  )
  plan = make_plan(documents, FakeState(), ADMIN, TEAMS)
  reasons = {item.name: (item.action, item.field, item.reason) for item in plan.items}
  assert reasons["communication"] == ("error", "spec.owner", "required for domain")
  assert reasons["messaging"] == ("error", "spec.subdomainOf", "domain 'communication' is not importable")
  assert reasons["greeter"] == ("error", "spec.domain", "domain 'messaging' is not importable")


def test_duplicates_are_errors_in_both_documents():
  plan = make_plan(sourced(COMMUNICATION[3], COMMUNICATION[3]), FakeState(), ADMIN, TEAMS)
  assert [(item.action, item.field, item.reason) for item in plan.items] == [
    ("error", "metadata.name", "domain 'communication' also declared in t.yaml#2"),
    ("error", "metadata.name", "domain 'communication' also declared in t.yaml#1"),
  ]


def test_same_name_in_two_kinds_is_not_a_duplicate():
  documents = sourced(doc("Domain", "platform", {"owner": "team-platform"}), doc("System", "platform", {"owner": "team-platform", "domain": "platform"}))
  assert actions(make_plan(documents, FakeState(), ADMIN, TEAMS)) == [("Domain", "platform", "create"), ("System", "platform", "create")]


def test_domain_cycle_is_an_error():
  documents = sourced(
    doc("Domain", "a", {"owner": "team-alpha", "subdomainOf": "b"}),
    doc("Domain", "b", {"owner": "team-alpha", "subdomainOf": "a"}),
    doc("Domain", "c", {"owner": "team-alpha", "subdomainOf": "c"}),
  )
  plan = make_plan(documents, FakeState(), ADMIN, TEAMS)
  assert all(item.action == "error" and item.field == "spec.subdomainOf" for item in plan.items)
  assert plan.items[0].reason.startswith("cycle: ")


def test_user_cannot_create_domain_and_children_cascade():
  plan = make_plan(sourced(*COMMUNICATION[:4]), FakeState(), USER, TEAMS)
  reasons = {item.name: (item.action, item.reason) for item in plan.items}
  assert reasons["communication"] == ("forbidden", "creating a domain requires group 'platform-admins'")
  assert reasons["messaging"][0] == "error"
  assert reasons["greeter"] == ("error", "domain 'messaging' is not importable")


def test_user_reimporting_unchanged_domains_imports_own_systems():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "messaging", {"owner": "team-alpha", "parent": "communication"})
  plan = make_plan(sourced(*COMMUNICATION[:4]), state, USER, TEAMS)
  assert actions(plan) == [
    ("Domain", "communication", "unchanged"),
    ("Domain", "messaging", "unchanged"),
    ("System", "greeter", "create"),
    ("Resource", "greeting-db", "create"),
  ]
  assert not plan.blocked


def test_user_cannot_update_domain():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-beta"})
  item = make_plan(sourced(COMMUNICATION[3]), state, USER, TEAMS).items[0]
  assert (item.action, item.reason) == ("forbidden", "updating a domain requires group 'platform-admins'")


def test_update_of_a_system_created_by_someone_else_is_forbidden():
  state = FakeState()
  seed(state, "domains", "messaging", {"owner": "team-alpha"})
  seed(state, "systems", "greeter", {"owner": "team-beta", "domain": "messaging"}, created_by="user-1")
  document = sourced(COMMUNICATION[1])
  assert make_plan(document, state, USER, TEAMS).items[0].action == "update"
  assert make_plan(document, state, ADMIN, TEAMS).items[0].action == "update"
  item = make_plan(document, state, OTHER, TEAMS).items[0]
  assert (item.action, item.reason) == ("forbidden", "system 'greeter' can only be updated by who created it or platform-admins")


def test_hash_is_stable_and_follows_the_state():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-beta"})
  documents = sourced(*COMMUNICATION[:4])
  first = make_plan(documents, state, ADMIN, TEAMS).hash
  assert first.startswith("sha256:")
  assert make_plan(documents, state, ADMIN, TEAMS).hash == first
  seed(state, "domains", "messaging", {"owner": "team-alpha", "parent": "communication"})
  assert make_plan(documents, state, ADMIN, TEAMS).hash != first


def test_view_shape():
  view = make_plan(sourced(COMMUNICATION[3], doc("Group", "team-alpha")), FakeState(), ADMIN, TEAMS).view(applied=False)
  assert view["items"][1] == {"kind": "Domain", "name": "communication", "action": "create", "source": "t.yaml#1", "spec": {"owner": "team-alpha"}}
  assert view["applied"] is False
  assert set(view) == {"items", "summary", "planHash", "applied"}


def test_update_under_a_descendant_in_the_platform_is_a_cycle():
  state = FakeState()
  seed(state, "domains", "a", {"owner": "team-alpha"})
  seed(state, "domains", "b", {"owner": "team-alpha", "parent": "a"})
  seed(state, "domains", "c", {"owner": "team-alpha", "parent": "b"})
  item = make_plan(sourced(doc("Domain", "a", {"owner": "team-alpha", "subdomainOf": "c"})), state, ADMIN, TEAMS).items[0]
  assert (item.action, item.field, item.reason) == ("error", "spec.subdomainOf", "cycle: a > c > b > a")


def test_cycle_through_the_import_and_the_platform():
  state = FakeState()
  seed(state, "domains", "a", {"owner": "team-alpha"})
  seed(state, "domains", "b", {"owner": "team-alpha", "parent": "a"})
  documents = sourced(doc("Domain", "a", {"owner": "team-alpha", "subdomainOf": "x"}), doc("Domain", "x", {"owner": "team-alpha", "subdomainOf": "b"}))
  plan = make_plan(documents, state, ADMIN, TEAMS)
  assert {item.name: item.action for item in plan.items} == {"a": "error", "x": "error"}
  assert plan.blocked


def test_duplicate_is_reported_even_when_a_copy_is_invalid():
  documents = sourced(doc("System", "z", {"owner": "team-alpha", "domain": "d"}), doc("System", "z", {"owner": "user:default/x", "domain": "d"}))
  plan = make_plan(documents, FakeState(), ADMIN, TEAMS)
  assert [(item.action, item.reason) for item in plan.items] == [
    ("error", "system 'z' also declared in t.yaml#2"),
    ("error", "system 'z' also declared in t.yaml#1"),
  ]


def test_null_namespace_is_default_and_other_types_are_errors():
  assert classify("f#1", doc("System", "greeter", {"owner": "team-alpha", "domain": "d"}, namespace=None)).action is None
  item = classify("f#1", doc("System", "greeter", {"owner": "team-alpha", "domain": "d"}, namespace=["x"]))
  assert (item.action, item.field, item.reason) == ("error", "metadata.namespace", "must be text")


def test_long_description_is_an_error():
  item = classify("f#1", doc("System", "greeter", {"owner": "team-alpha", "domain": "d"}, description="x" * 1001))
  assert (item.action, item.field, item.reason) == ("error", "metadata.description", "at most 1000 characters")


# Groups become teams and owners must be teams (ADR 0026, #236).

def test_group_is_a_team_to_create_by_admins_only():
  documents = sourced(doc("Group", "team-gamma", {"type": "team"}))
  assert actions(make_plan(documents, FakeState(), ADMIN, TEAMS)) == [("Group", "team-gamma", "create")]
  item = make_plan(documents, FakeState(), USER, TEAMS).items[0]
  assert (item.action, item.reason) == ("forbidden", "creating a team requires group 'platform-admins'")
  assert make_plan(sourced(doc("Group", "team-alpha", {"type": "team"})), FakeState(), USER, TEAMS).items[0].action == "unchanged"


@pytest.mark.parametrize("name,reason", [
  ("platform-admins", "'platform-admins' is reserved by the platform"),
  ("Team_Gamma", "lowercase letters, digits and '-', at most 63 characters"),
])
def test_group_names_follow_team_rules(name, reason):
  item = make_plan(sourced(doc("Group", name, {"type": "team"})), FakeState(), ADMIN, TEAMS).items[0]
  assert (item.action, item.field, item.reason) == ("error", "metadata.name", reason)


def test_owner_must_be_a_team():
  item = make_plan(sourced(doc("Domain", "lonely", {"owner": "team-nobody"})), FakeState(), ADMIN, TEAMS).items[0]
  assert (item.action, item.field) == ("error", "spec.owner")
  assert "team 'team-nobody' not found" in item.reason


def test_owner_declared_in_the_same_import():
  documents = sourced(doc("Domain", "fresh", {"owner": "team-gamma"}), doc("Group", "team-gamma", {"type": "team"}))
  assert actions(make_plan(documents, FakeState(), ADMIN, TEAMS)) == [("Group", "team-gamma", "create"), ("Domain", "fresh", "create")]


def test_owner_declared_but_not_importable_is_an_error():
  documents = sourced(doc("System", "fresh", {"owner": "team-gamma", "domain": "communication"}), doc("Group", "team-gamma", {"type": "team"}))
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  items = {item.kind: item for item in make_plan(documents, state, USER, TEAMS).items}
  assert items["Group"].action == "forbidden"
  assert (items["System"].action, items["System"].field) == ("error", "spec.owner")


def test_unchanged_entity_keeps_an_owner_that_is_no_team():
  state = FakeState()
  seed(state, "domains", "legacy", {"owner": "free-text"})
  assert actions(make_plan(sourced(doc("Domain", "legacy", {"owner": "free-text"})), state, ADMIN, TEAMS)) == [("Domain", "legacy", "unchanged")]

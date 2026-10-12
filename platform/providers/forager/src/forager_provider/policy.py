"""Which provisioner makes a resource of the Score (ADR 0031): BindingPolicy items in layers.

The policies of the environment come first, then those of its profile (spec.profile, #329), then the
platform default (neither spec.environment nor spec.profile); by name within a layer, by position
within a policy. The first item that matches wins:
- type equal;
- class equal: an item without class matches only a request without class, and a request with a
  class needs an item with that class (a branch asking for restored never gets an empty database);
- id equal, when the item has one.
"""


def layers(policies: list[dict], environment: str, profile: str | None = None) -> list[dict]:
  def of(environment: str | None, profile: str | None) -> list[dict]:
    def scope(policy: dict) -> tuple:
      spec = policy.get("spec") or {}
      return (spec.get("environment") or None, spec.get("profile") or None)
    return sorted((p for p in policies if scope(p) == (environment, profile)), key=lambda p: p["metadata"]["name"])
  ordered = (*of(environment, None), *(of(None, profile) if profile else ()), *of(None, None))
  return [item for policy in ordered for item in (policy["spec"].get("provisioners") or [])]


def matches(item: dict, kind: str, klass: str | None, resource_id: str | None) -> bool:
  if item.get("type") != kind:
    return False
  if (item.get("class") or None) != (klass or None):
    return False
  return not item.get("id") or item["id"] == resource_id


def resolve(policies: list[dict], environment: str, kind: str, klass: str | None = None, resource_id: str | None = None, profile: str | None = None) -> dict | None:
  return next((item for item in layers(policies, environment, profile) if matches(item, kind, klass, resource_id)), None)

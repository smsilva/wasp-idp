"""Which provisioner makes a resource of the Score (ADR 0031): BindingPolicy items in layers.

The policies of the environment come before the platform default (spec.environment empty); by name
within a layer, by position within a policy. The first item that matches wins:
- type equal;
- class equal: an item without class matches only a request without class, and a request with a
  class needs an item with that class (a branch asking for restored never gets an empty database);
- id equal, when the item has one.
"""


def layers(policies: list[dict], environment: str) -> list[dict]:
  def of(name: str | None) -> list[dict]:
    return sorted((p for p in policies if ((p.get("spec") or {}).get("environment") or None) == name), key=lambda p: p["metadata"]["name"])
  return [item for policy in (*of(environment), *of(None)) for item in (policy["spec"].get("provisioners") or [])]


def matches(item: dict, kind: str, klass: str | None, resource_id: str | None) -> bool:
  if item.get("type") != kind:
    return False
  if (item.get("class") or None) != (klass or None):
    return False
  return not item.get("id") or item["id"] == resource_id


def resolve(policies: list[dict], environment: str, kind: str, klass: str | None = None, resource_id: str | None = None) -> dict | None:
  return next((item for item in layers(policies, environment) if matches(item, kind, klass, resource_id)), None)

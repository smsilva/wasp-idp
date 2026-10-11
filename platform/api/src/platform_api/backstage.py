"""Shared pieces of reading Backstage documents: the catalog import and the template import."""


class Invalid(Exception):
  def __init__(self, field: str, reason: str):
    super().__init__(f"{field}: {reason}")
    self.field = field
    self.reason = reason


def owner_of(value):
  """group:default/team-alpha, group:team-alpha and default/team-alpha are the group team-alpha."""
  if value is None:
    return None
  if not isinstance(value, str):
    raise Invalid("spec.owner", "must be text")
  reference = value
  if ":" in reference:
    kind, reference = reference.split(":", 1)
    if kind.lower() != "group":
      raise Invalid("spec.owner", f"'{value}' is not a group: the owner of a catalog entity is a team")
  if "/" in reference:
    namespace, reference = reference.split("/", 1)
    if namespace != "default":
      raise Invalid("spec.owner", f"'{value}': namespace '{namespace}' is not supported, only 'default'")
  return reference

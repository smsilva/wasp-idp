"""What this version does: the list the home page and GET /api/info show.

Add an entry when you add an endpoint, with new=True while it is the change being shipped: after the
deploy, the page shows it under "What this version does".
"""
from pydantic import BaseModel


class Feature(BaseModel):
    name: str
    description: str
    endpoint: str
    new: bool = False

    @property
    def href(self) -> str:
        """The endpoint itself when it is a plain GET, else the API docs, where it can be tried."""
        method, _, path = self.endpoint.partition(" ")
        return path if method == "GET" and "{" not in path else "/docs"


FEATURES = [
    Feature(name="Describes itself", description="Its name, version and commit, as JSON.", endpoint="GET /api/info"),
    Feature(
        name="Checks its database",
        description="The same check as this page, as JSON. Answers 503 when the database is unreachable.",
        endpoint="GET /api/db",
    ),
]

"""workload route (#344): GET the route, change one rule, PUT it whole; --clear deletes it."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands.workload import routed_rules

runner = CliRunner()
SANDBOX = {"match": {"header": {"name": "x-sandbox", "value": "pr-42"}}, "to": "reviews-pr-42"}
BAGGAGE = {"match": {"baggage": {"key": "sandbox", "value": "pr-42"}}, "to": "reviews-pr-42"}


@pytest.mark.parametrize("rules,change,expected", [
  ([], {"header": ("x-sandbox", "pr-42")}, [SANDBOX]),
  # The same match is replaced, header names case-insensitive; the weights rule stays the last.
  ([{**SANDBOX, "match": {"header": {"name": "X-Sandbox", "value": "pr-42"}}}, {"weights": {"reviews": 90, "reviews-pr-7": 10}}], {"header": ("x-sandbox", "pr-42")}, [SANDBOX, {"weights": {"reviews": 90, "reviews-pr-7": 10}}]),
  ([SANDBOX], {"baggage": ("sandbox", "pr-42")}, [SANDBOX, BAGGAGE]),
  ([SANDBOX], {"weight": 10}, [SANDBOX, {"weights": {"reviews-pr-42": 10, "reviews": 90}}]),
  # Other instances keep their share; the main one takes the rest.
  ([{"weights": {"reviews-pr-7": 20, "reviews": 80}}], {"weight": 10}, [{"weights": {"reviews-pr-42": 10, "reviews-pr-7": 20, "reviews": 70}}]),
  ([{"weights": {"reviews-pr-42": 10, "reviews": 90}}], {"weight": 100}, [{"weights": {"reviews-pr-42": 100}}]),
  ([SANDBOX, {"weights": {"reviews-pr-42": 10, "reviews": 90}}], {"weight": 0}, [SANDBOX]),
])
def test_routed_rules(rules, change, expected):
  assert routed_rules(rules, "reviews", "reviews-pr-42", **change) == expected


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "route": None, "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"] and request.method == "PUT":
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "GET":
      if state["route"] is None:
        return httpx.Response(404, json={"error": {"code": "x", "message": "no route of 'reviews' in environment 'demo'"}})
      return httpx.Response(200, json={"rules": state["route"]})
    if request.method == "PUT":
      state["route"] = json.loads(request.content)["rules"]
      return httpx.Response(200, json={"name": "demo.reviews", "rules": state["route"], "status": "Pending"})
    state["route"] = None
    return httpx.Response(202, json={"name": "demo.reviews", "status": "deleting"})

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return state


def run(*args):
  return runner.invoke(app, ["workload", "route", "--component", "reviews", "--environment", "demo", *args])


def test_header_route(api):
  result = run("--header", "x-sandbox=pr-42", "--to", "reviews-pr-42")
  assert result.exit_code == 0, result.output
  assert [(r.method, r.url.path) for r in api["requests"]] == [("GET", "/v1/environments/demo/workloads/routes/reviews"), ("PUT", "/v1/environments/demo/workloads/routes/reviews")]
  assert api["route"] == [SANDBOX]
  assert "x-sandbox=pr-42 → reviews-pr-42" in result.output
  assert "otherwise → reviews" in result.output


def test_weight_keeps_the_header_rule(api):
  api["route"] = [SANDBOX]
  result = run("--weight", "10", "--to", "reviews-pr-42")
  assert result.exit_code == 0, result.output
  assert api["route"] == [SANDBOX, {"weights": {"reviews-pr-42": 10, "reviews": 90}}]
  assert "reviews-pr-42 10% · reviews 90%" in result.output


def test_weight_zero_of_the_last_rule_clears(api):
  api["route"] = [{"weights": {"reviews-pr-42": 10, "reviews": 90}}]
  result = run("--weight", "0", "--to", "reviews-pr-42")
  assert result.exit_code == 0, result.output
  assert api["requests"][-1].method == "DELETE"
  assert "cleared" in result.output


def test_clear(api):
  api["route"] = [SANDBOX]
  result = run("--clear")
  assert result.exit_code == 0, result.output
  assert [r.method for r in api["requests"]] == ["DELETE"]


@pytest.mark.parametrize("args,message", [
  (["--to", "reviews-pr-42"], "one of --header, --baggage or --weight"),
  (["--header", "x-sandbox=pr-42"], "give --to"),
  (["--header", "x-sandbox=pr-42", "--weight", "10", "--to", "reviews-pr-42"], "one of --header"),
  (["--header", "x-sandbox", "--to", "reviews-pr-42"], "--header takes key=value"),
  (["--weight", "10", "--to", "reviews"], "reviews takes the rest"),
  (["--clear", "--to", "reviews-pr-42"], "--clear takes no"),
])
def test_refusals(api, args, message):
  result = run(*args)
  assert result.exit_code == 1
  assert message in result.output


def test_api_refusal_passes_through(api):
  api["error"] = (409, "route of 'reviews': reviews-pr-42@demo runs component 'ratings'")
  result = run("--header", "x-sandbox=pr-42", "--to", "reviews-pr-42")
  assert result.exit_code == 1
  assert "409: route of 'reviews'" in result.output

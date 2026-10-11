"""Journal redaction (ADR 0025): no credential reaches the file."""
import json

from platform_api.journal import Journal, redact

PEM = "-----BEGIN PRIVATE KEY-----\nMIIEfake\n-----END PRIVATE KEY-----\n"


def test_redacts_sensitive_keys_and_any_pem():
  redacted = redact({"org": "acme", "privateKeyPem": "abc", "nested": [{"note": PEM}], "token": None})
  assert redacted["org"] == "acme"
  assert redacted["privateKeyPem"].startswith("<redacted, sha256:")
  assert redacted["nested"][0]["note"].startswith("<redacted, sha256:")
  assert redacted["token"] is None


def test_same_value_same_digest():
  assert redact({"pem": PEM})["pem"] == redact({"secret": PEM})["secret"]
  assert redact({"pem": PEM}) != redact({"pem": PEM + "x"})


def test_no_pem_in_the_file(tmp_path):
  path = tmp_path / "journal.jsonl"
  Journal(path).record("create", "ScmConnection", "acme", {"privateKeyPem": PEM, "org": "acme"}, "admin")
  text = path.read_text()
  assert "BEGIN" not in text
  assert json.loads(text)["spec"]["org"] == "acme"

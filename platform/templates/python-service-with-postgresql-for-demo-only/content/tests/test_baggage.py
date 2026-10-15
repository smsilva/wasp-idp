import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from fastapi.testclient import TestClient

import app.main


class Backend(BaseHTTPRequestHandler):
    received = []

    def do_GET(self):
        Backend.received.append(dict(self.headers))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_outgoing_calls_carry_the_incoming_baggage():
    """The contract of the platform's routing (ADR 0035): an httpx call made while handling a request
    carries that request's baggage, so a route by baggage holds down the whole chain of calls."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    backend = f"http://127.0.0.1:{server.server_port}/"

    @app.main.app.get("/chain")
    def chain() -> dict[str, int]:
        return {"status": httpx.get(backend).status_code}

    try:
        Backend.received.clear()
        response = TestClient(app.main.app).get("/chain", headers={"baggage": "sandbox=pr-42"})
        assert response.json() == {"status": 200}
        assert Backend.received[0].get("baggage") == "sandbox=pr-42"

        Backend.received.clear()
        TestClient(app.main.app).get("/chain")
        assert "baggage" not in Backend.received[0]
    finally:
        server.shutdown()

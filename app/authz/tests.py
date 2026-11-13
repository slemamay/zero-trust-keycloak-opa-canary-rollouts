"""Tests du PEP (sans Django ni OPA réel) : python -m unittest authz.tests"""
import json
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from authz import pep


class FakeOPA(BaseHTTPRequestHandler):
    reply = {"result": {"allow": True, "reasons": []}}
    last_body = None

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        FakeOPA.last_body = json.loads(self.rfile.read(n))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(FakeOPA.reply).encode())

    def log_message(self, *a):
        pass


class PepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeOPA)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        pep.OPA_URL = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    manager = {"sub": "uuid-1", "username": "bob", "roles": ["manager"],
               "branch": "AG01", "agent_scopes": []}
    res = {"type": "transaction", "id": "1", "branch": "AG01", "amount": 500.0,
           "created_by": "alice"}
    ctx = {"hour": 10, "weekday": "Tuesday"}

    def test_subject_human_uses_username_as_sub(self):
        s = pep.build_subject(self.manager)
        self.assertEqual((s["type"], s["sub"]), ("human", "bob"))

    def test_subject_agent_when_only_scopes(self):
        s = pep.build_subject({"sub": "u", "username": "bot", "roles": [],
                               "branch": "AG01", "agent_scopes": ["transactions:draft"]})
        self.assertEqual(s["type"], "agent")

    def test_context_uses_tunis_time(self):
        c = pep.build_context(datetime(2026, 11, 11, 9, 0, tzinfo=ZoneInfo("UTC")).astimezone(pep.TZ))
        self.assertEqual((c["hour"], c["weekday"]), (10, "Wednesday"))

    def test_allow_and_payload_shape(self):
        FakeOPA.reply = {"result": {"allow": True, "reasons": []}}
        ok, reasons, _, err = pep.decide(pep.build_subject(self.manager), "approve", self.res, self.ctx)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(set(FakeOPA.last_body["input"]), {"subject", "resource", "action", "context"})

    def test_deny_returns_reasons(self):
        FakeOPA.reply = {"result": {"allow": False, "reasons": ["branch mismatch"]}}
        ok, reasons, _, _ = pep.decide(pep.build_subject(self.manager), "approve", self.res, self.ctx)
        self.assertFalse(ok)
        self.assertEqual(reasons, ["branch mismatch"])

    def test_empty_result_is_deny(self):
        FakeOPA.reply = {}
        ok, reasons, _, _ = pep.decide(pep.build_subject(self.manager), "approve", self.res, self.ctx)
        self.assertFalse(ok)

    def test_opa_down_is_fail_closed(self):
        old = pep.OPA_URL
        pep.OPA_URL = "http://127.0.0.1:9"
        try:
            ok, reasons, _, err = pep.decide(pep.build_subject(self.manager), "approve", self.res, self.ctx)
        finally:
            pep.OPA_URL = old
        self.assertFalse(ok)
        self.assertEqual(reasons, ["pdp_unavailable"])
        self.assertIsNotNone(err)


class ConfigConsistencyTests(unittest.TestCase):
    """Garde-fou : Keycloak (realm-export.json) et OPA (data.json) doivent parler la meme langue."""

    root = __import__("pathlib").Path(__file__).resolve().parents[2]

    def _realm(self):
        return json.loads((self.root / "keycloak" / "realm-export.json").read_text(encoding="utf-8"))

    def _data(self):
        return json.loads((self.root / "policies" / "data.json").read_text(encoding="utf-8"))["config"]

    def test_agent_scopes_exist_in_policy(self):
        known = set(self._data()["agent_scope_actions"])
        for u in self._realm()["users"]:
            for sc in (u.get("attributes") or {}).get("agent_scopes", []):
                self.assertIn(sc, known, f"{u['username']}: scope inconnu d'OPA: {sc}")

    def test_agent_user_is_classified_as_agent(self):
        business = set(self._data()["role_permissions"])
        agents = [u for u in self._realm()["users"] if (u.get("attributes") or {}).get("agent_scopes")]
        self.assertTrue(agents)
        for u in agents:
            roles = [r for r in u["realmRoles"] if r in business]
            ident = {"sub": "x", "username": u["username"], "roles": roles,
                     "branch": "AG01", "agent_scopes": u["attributes"]["agent_scopes"]}
            self.assertEqual(pep.build_subject(ident)["type"], "agent")


if __name__ == "__main__":
    unittest.main()
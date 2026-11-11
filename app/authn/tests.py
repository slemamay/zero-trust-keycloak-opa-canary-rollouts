from django.test import SimpleTestCase
from .jwks import extract_identity


class ExtractIdentityTests(SimpleTestCase):
    def test_manager_with_branch(self):
        claims = {
            "sub": "123",
            "preferred_username": "bob",
            "realm_access": {"roles": ["manager", "offline_access"]},
            "agence": "AG01",
        }
        who = extract_identity(claims)
        self.assertEqual(who["roles"], ["manager"])   # rôles techniques filtrés
        self.assertEqual(who["branch"], "AG01")
        self.assertEqual(who["agent_scopes"], [])

    def test_agent_scopes_string_becomes_list(self):
        claims = {
            "sub": "456",
            "preferred_username": "agent-ia",
            "realm_access": {"roles": ["caissier"]},
            "agent_scopes": "read:transactions",
        }
        who = extract_identity(claims)
        self.assertEqual(who["agent_scopes"], ["read:transactions"])
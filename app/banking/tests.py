from django.test import SimpleTestCase


class AuthRequiredTests(SimpleTestCase):
    def test_transactions_without_token_is_401(self):
        self.assertEqual(self.client.get("/transactions/").status_code, 401)

    def test_whoami_with_garbage_token_is_401(self):
        r = self.client.get("/whoami/", headers={"Authorization": "Bearer abc.def.ghi"})
        self.assertEqual(r.status_code, 401)
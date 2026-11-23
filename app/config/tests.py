from django.test import TestCase


class SaudeTests(TestCase):
    def test_saude_responde_ok(self):
        resposta = self.client.get("/saude/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

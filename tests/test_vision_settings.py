import os
import sys
import tempfile
import unittest
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

import app as backend_app
import vision_fallback as vision_module


class VisionSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_upload_folder = backend_app.app.config["UPLOAD_FOLDER"]
        backend_app.app.config["UPLOAD_FOLDER"] = self.tmp.name
        backend_app.reset_vision_fallback()

    def tearDown(self):
        backend_app.app.config["UPLOAD_FOLDER"] = self.old_upload_folder
        backend_app.reset_vision_fallback()
        self.tmp.cleanup()

    def test_switching_provider_without_new_key_clears_saved_api_key(self):
        backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-3.6-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "dashscope-secret",
        })

        public = backend_app.save_vision_settings({
            "enabled": True,
            "provider": "custom",
            "model": "llama3.2-vision",
            "base_url": "http://localhost:11434/v1",
        })
        secret = backend_app.load_vision_settings(include_secret=True)

        self.assertEqual(public["provider"], "custom")
        self.assertFalse(public["has_api_key"])
        self.assertEqual(secret["api_key"], "")

    def test_probe_vision_models_lists_openai_compatible_models(self):
        old_urlopen = vision_module.urllib.request.urlopen
        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "data": [
                        {"id": "qwen-3.6-flash"},
                        {"id": "qwen-vl-max"},
                        {"id": "text-only-model"},
                    ]
                }).encode("utf-8")

        def fake_urlopen(req, timeout=0):
            seen["url"] = req.full_url
            seen["auth"] = req.headers.get("Authorization")
            seen["timeout"] = timeout
            return FakeResponse()

        try:
            vision_module.urllib.request.urlopen = fake_urlopen
            result = vision_module.probe_vision_models({
                "provider": "qwen",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "dashscope-secret",
            })
        finally:
            vision_module.urllib.request.urlopen = old_urlopen

        self.assertTrue(result["success"], result)
        self.assertEqual(seen["url"], "https://dashscope.aliyuncs.com/compatible-mode/v1/models")
        self.assertEqual(seen["auth"], "Bearer dashscope-secret")
        self.assertIn("qwen-vl-max", [item["value"] for item in result["models"]])
        self.assertTrue(any(item["vision_hint"] for item in result["models"]))

    def test_probe_vision_settings_endpoint_does_not_save_settings(self):
        old_probe = backend_app.probe_vision_models

        try:
            backend_app.probe_vision_models = lambda data, saved_settings=None: {
                "success": True,
                "models": [{"value": "qwen-vl-max", "label": "qwen-vl-max", "vision_hint": True}],
                "warnings": [],
            }
            response = backend_app.app.test_client().post(
                "/api/vision-settings/probe",
                json={
                    "provider": "qwen",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": "dashscope-secret",
                },
            )
        finally:
            backend_app.probe_vision_models = old_probe

        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["models"][0]["value"], "qwen-vl-max")
        saved = backend_app.load_vision_settings(include_secret=True)
        self.assertEqual(saved["api_key"], "")

    def test_reveal_saved_api_key_endpoint_returns_saved_secret(self):
        backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "dashscope-secret",
        })

        response = backend_app.app.test_client().get("/api/vision-settings/api-key")

        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["has_api_key"])
        self.assertEqual(data["api_key"], "dashscope-secret")


if __name__ == "__main__":
    unittest.main()

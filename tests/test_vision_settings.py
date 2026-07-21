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

    def test_switching_provider_preserves_saved_api_key_profile(self):
        backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-3.6-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "dashscope-secret",
        })

        public = backend_app.save_vision_settings({
            "enabled": True,
            "provider": "ollama",
            "model": "qwen3-vl:8b",
            "base_url": "http://localhost:11434",
        })
        secret = backend_app.load_vision_settings(include_secret=True)

        self.assertEqual(public["provider"], "ollama")
        self.assertFalse(public["has_api_key"])
        self.assertEqual(secret["api_key"], "")
        self.assertEqual(secret["profiles"]["qwen"]["api_key"], "dashscope-secret")

        public = backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-3.6-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        })
        secret = backend_app.load_vision_settings(include_secret=True)

        self.assertEqual(public["provider"], "qwen")
        self.assertTrue(public["has_api_key"])
        self.assertEqual(secret["api_key"], "dashscope-secret")

    def test_load_vision_settings_migrates_legacy_flat_file_to_profiles(self):
        path = backend_app.vision_settings_path()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "enabled": True,
                "provider": "custom",
                "model": "qwen3-vl:8b",
                "base_url": "http://localhost:11434/v1",
                "api_key": "",
                "threshold": 0.75,
            }, fh)

        secret = backend_app.load_vision_settings(include_secret=True)

        self.assertEqual(secret["provider"], "ollama")
        self.assertEqual(secret["model"], "qwen3-vl:8b")
        self.assertEqual(secret["base_url"], "http://localhost:11434")
        self.assertIn("ollama", secret["profiles"])

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

    def test_probe_ollama_models_reads_native_tags_endpoint(self):
        old_urlopen = vision_module.urllib.request.urlopen
        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "models": [
                        {"name": "qwen3-vl:8b"},
                        {"name": "llama3.2-vision"},
                    ]
                }).encode("utf-8")

        def fake_urlopen(req, timeout=0):
            seen["url"] = req.full_url
            seen["auth"] = req.headers.get("Authorization")
            return FakeResponse()

        try:
            vision_module.urllib.request.urlopen = fake_urlopen
            result = vision_module.probe_vision_models({
                "provider": "ollama",
                "base_url": "http://localhost:11434",
            })
        finally:
            vision_module.urllib.request.urlopen = old_urlopen

        self.assertTrue(result["success"], result)
        self.assertEqual(seen["url"], "http://localhost:11434/api/tags")
        self.assertIsNone(seen["auth"])
        self.assertEqual(result["models"][0]["value"], "qwen3-vl:8b")

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

    def test_reveal_saved_api_key_uses_requested_provider_and_model_profile(self):
        backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-3.6-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "flash-secret",
        })
        backend_app.save_vision_settings({
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "vl-secret",
        })

        response = backend_app.app.test_client().get(
            "/api/vision-settings/api-key?provider=qwen&model=qwen-3.6-flash"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertTrue(data["has_api_key"])
        self.assertEqual(data["api_key"], "flash-secret")


if __name__ == "__main__":
    unittest.main()

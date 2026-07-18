import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

import app as backend_app


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
            "model": "qwen3.6-plus",
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


if __name__ == "__main__":
    unittest.main()

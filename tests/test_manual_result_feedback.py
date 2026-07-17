import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

import yaml
import app as app_module
from app import (
    apply_corrections,
    build_export_json_payload,
    build_field_values,
    normalize_corrections_payload,
)


class ManualResultFeedbackTest(unittest.TestCase):
    def make_result(self):
        return {
            "template": "demo",
            "fields": {
                "提单号": {
                    "label": "提单号",
                    "value": "BL001",
                    "cleaned": "BL001",
                    "confidence": 0.92,
                    "status": "extracted",
                }
            },
            "table": {
                "headers": ["箱号", "重量"],
                "rows": [["MSKU1", "100 KG"]],
            },
            "meta": {},
        }

    def test_legacy_flat_corrections_still_update_existing_fields(self):
        result = apply_corrections(self.make_result(), {"提单号": "BL999"})

        self.assertEqual(result["fields"]["提单号"]["corrected"], "BL999")
        self.assertEqual(result["fields"]["提单号"]["status"], "corrected")
        self.assertEqual(result["corrections"], {"提单号": "BL999"})

    def test_manual_fields_are_merged_as_exportable_fields(self):
        result = apply_corrections(
            self.make_result(),
            {
                "fields": {},
                "manual_fields": [
                    {"label": "客户备注", "value": "需要冷藏"},
                ],
            },
        )

        self.assertIn("客户备注", result["fields"])
        manual = result["fields"]["客户备注"]
        self.assertEqual(manual["label"], "客户备注")
        self.assertEqual(manual["value"], "需要冷藏")
        self.assertEqual(manual["status"], "manual_added")
        self.assertEqual(manual["source"], "manual")
        self.assertEqual(manual["confidence"], 1.0)
        self.assertEqual(result["meta"]["manual_fields_count"], 1)

    def test_table_patch_replaces_final_table_without_breaking_ocr_source(self):
        result = apply_corrections(
            self.make_result(),
            {
                "table_patch": {
                    "headers": ["品名", "数量"],
                    "rows": [["玩具", "12"]],
                }
            },
        )

        self.assertEqual(result["table"]["headers"], ["品名", "数量"])
        self.assertEqual(result["table"]["rows"], [["玩具", "12"]])
        self.assertEqual(result["table"]["source"], "ocr_with_manual_patch")
        self.assertTrue(result["meta"]["manual_table"])

    def test_build_field_values_returns_human_readable_mapping(self):
        result = apply_corrections(
            {
                "fields": {
                    "原产国": {
                        "label": "原产国",
                        "value": "",
                        "cleaned": "",
                        "status": "not_found",
                    },
                    "商品名称": {
                        "label": "商品名称",
                        "value": "纺织品",
                        "cleaned": "纺织品",
                        "status": "extracted",
                    },
                },
                "meta": {},
            },
            {"fields": {"原产国": "韩国"}},
        )

        self.assertEqual(
            build_field_values(result["fields"]),
            {"原产国": "韩国", "商品名称": "纺织品"},
        )

    def test_field_label_corrections_rename_exported_label(self):
        result = apply_corrections(
            self.make_result(),
            {
                "fields": {"提单号": "BL999"},
                "field_labels": {"提单号": "海运提单号"},
            },
        )

        self.assertEqual(result["fields"]["提单号"]["label"], "海运提单号")
        self.assertEqual(result["field_labels"], {"提单号": "海运提单号"})
        self.assertEqual(build_field_values(result["fields"]), {"海运提单号": "BL999"})

    def test_build_export_json_payload_can_export_values_only(self):
        result = apply_corrections(
            self.make_result(),
            {"fields": {"提单号": "BL999"}},
        )

        payload = build_export_json_payload(
            result,
            {
                "field_values": True,
                "field_details": False,
                "table": False,
                "meta": False,
            },
        )

        self.assertEqual(payload, {"field_values": {"提单号": "BL999"}})

    def test_build_export_json_payload_combines_detail_values_and_table(self):
        result = apply_corrections(
            self.make_result(),
            {"fields": {"提单号": "BL999"}},
        )

        payload = build_export_json_payload(
            result,
            {
                "field_values": True,
                "field_details": True,
                "table": True,
                "meta": True,
            },
        )

        self.assertIn("fields", payload)
        self.assertIn("field_values", payload)
        self.assertIn("table", payload)
        self.assertEqual(payload["field_values"]["提单号"], "BL999")
        self.assertEqual(payload["table"]["headers"], ["箱号", "重量"])

    def test_normalize_new_payload_keeps_fields_manual_fields_and_table(self):
        payload = normalize_corrections_payload(
            {
                "fields": {"提单号": "BL002"},
                "field_labels": {"提单号": "海运提单号"},
                "manual_fields": [{"key": "remark", "label": "备注", "value": "加急"}],
                "table_patch": {"headers": ["A", "B"], "rows": [["1"]]},
            }
        )

        self.assertEqual(payload["fields"], {"提单号": "BL002"})
        self.assertEqual(payload["field_labels"], {"提单号": "海运提单号"})
        self.assertEqual(payload["manual_fields"], [{"key": "remark", "label": "备注", "value": "加急"}])
        self.assertEqual(payload["table_patch"]["rows"], [["1", ""]])

    def test_fewshot_from_result_merges_fields_and_table_into_existing_template(self):
        job_id = "abcdef123456"
        old_config_yaml_path = app_module.config_yaml_path
        old_get_extractor = app_module.get_extractor

        class FakeExtractor:
            def reload_config(self):
                self.reloaded = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    {
                        "templates": {
                            "target_tpl": {
                                "keywords": ["TARGET"],
                                "has_table": False,
                                "fields": {},
                                "output": [],
                            }
                        }
                    },
                    f,
                    allow_unicode=True,
                    sort_keys=False,
                )

            app_module.config_yaml_path = lambda: config_path
            app_module.get_extractor = lambda: FakeExtractor()
            app_module._jobs[job_id] = {
                "id": job_id,
                "status": "done",
                "result": self.make_result(),
                "corrections": {
                    "manual_fields": [{"label": "客户备注", "value": "需要冷藏"}],
                    "table_patch": {"headers": ["品名", "数量"], "rows": [["玩具", "12"]]},
                },
            }

            try:
                client = app_module.app.test_client()
                response = client.post(
                    "/api/fewshot/from-result",
                    json={
                        "job_id": job_id,
                        "template_name": "target_tpl",
                        "field_names": ["提单号", "客户备注"],
                        "include_table": True,
                        "mode": "merge",
                    },
                )

                self.assertEqual(response.status_code, 200, response.get_json())
                data = response.get_json()
                self.assertTrue(data["success"])
                self.assertIn("提单号", data["fields_added"])
                self.assertIn("客户备注", data["fields_added"])
                self.assertTrue(data["table_updated"])

                with open(config_path, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f)
                template = saved["templates"]["target_tpl"]
                self.assertIn("提单号", template["fields"])
                self.assertIn("客户备注", template["fields"])
                self.assertEqual(template["output"], ["提单号", "客户备注"])
                self.assertTrue(template["has_table"])
                self.assertEqual(template["table_headers"], ["品名", "数量"])
            finally:
                app_module._jobs.pop(job_id, None)
                app_module.config_yaml_path = old_config_yaml_path
                app_module.get_extractor = old_get_extractor

    def test_fewshot_from_result_can_create_new_template(self):
        job_id = "abcdef654321"
        old_config_yaml_path = app_module.config_yaml_path
        old_get_extractor = app_module.get_extractor

        class FakeExtractor:
            def reload_config(self):
                self.reloaded = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump({"templates": {}}, f, allow_unicode=True, sort_keys=False)

            app_module.config_yaml_path = lambda: config_path
            app_module.get_extractor = lambda: FakeExtractor()
            app_module._jobs[job_id] = {
                "id": job_id,
                "status": "done",
                "result": {
                    "template": "unknown",
                    "fields": {
                        "Custom Field": {
                            "label": "Custom Field",
                            "value": "ABC",
                            "cleaned": "ABC",
                            "confidence": 0.9,
                            "status": "extracted",
                            "anchor": "Custom Field",
                        }
                    },
                    "table": {"headers": ["Col A", "Col B"], "rows": [["1", "2"]]},
                    "meta": {},
                },
                "corrections": {},
            }

            try:
                client = app_module.app.test_client()
                response = client.post(
                    "/api/fewshot/from-result",
                    json={
                        "job_id": job_id,
                        "template_name": "new_custom_template",
                        "field_names": ["Custom Field"],
                        "include_table": True,
                        "mode": "create",
                    },
                )

                self.assertEqual(response.status_code, 200, response.get_json())
                data = response.get_json()
                self.assertTrue(data["success"])
                self.assertEqual(data["mode"], "create")
                self.assertTrue(data["created"])
                self.assertIn("Custom Field", data["fields_added"])

                with open(config_path, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f)
                template = saved["templates"]["new_custom_template"]
                self.assertTrue(template["enabled"])
                self.assertFalse(template["hidden"])
                self.assertTrue(template["has_table"])
                self.assertEqual(template["table_headers"], ["Col A", "Col B"])
                self.assertIn("Custom Field", template["fields"])
                self.assertEqual(template["output"], ["Custom Field"])
            finally:
                app_module._jobs.pop(job_id, None)
                app_module.config_yaml_path = old_config_yaml_path
                app_module.get_extractor = old_get_extractor

    def test_fewshot_from_result_ai_enhance_merges_model_suggestions(self):
        job_id = "abcdef777777"
        old_config_yaml_path = app_module.config_yaml_path
        old_get_extractor = app_module.get_extractor
        old_ai_enhance = getattr(app_module, "ai_enhance_feedback_template", None)

        class FakeExtractor:
            def reload_config(self):
                self.reloaded = True

        def fake_ai_enhance_feedback_template(**kwargs):
            target_template = kwargs["target_template"]
            warnings = kwargs["warnings"]
            return app_module.apply_ai_template_enhancement(
                target_template,
                {
                    "template_keywords": ["BILL OF LADING", "MAERSK LINE"],
                    "fields": [
                        {
                            "field": "提单号",
                            "anchors": ["B/L No.", "Bill of Lading No."],
                            "position": "right",
                            "value_pattern": r"^BL\d+$",
                            "multi_line": False,
                            "confidence": 0.91,
                        }
                    ],
                    "table_headers": ["Container No.", "Gross Weight"],
                    "warnings": ["提单号建议来自 AI 增强"],
                },
                selected_fields=kwargs["selected_fields"],
                include_table=kwargs["include_table"],
                warnings=warnings,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    {
                        "templates": {
                            "target_tpl": {
                                "keywords": ["TARGET"],
                                "has_table": False,
                                "fields": {},
                                "output": [],
                            }
                        }
                    },
                    f,
                    allow_unicode=True,
                    sort_keys=False,
                )

            app_module.config_yaml_path = lambda: config_path
            app_module.get_extractor = lambda: FakeExtractor()
            app_module.ai_enhance_feedback_template = fake_ai_enhance_feedback_template
            app_module._jobs[job_id] = {
                "id": job_id,
                "status": "done",
                "result": self.make_result(),
                "corrections": {},
            }

            try:
                client = app_module.app.test_client()
                response = client.post(
                    "/api/fewshot/from-result",
                    json={
                        "job_id": job_id,
                        "template_name": "target_tpl",
                        "field_names": ["提单号"],
                        "include_table": True,
                        "mode": "merge",
                        "ai_enhance": True,
                    },
                )

                self.assertEqual(response.status_code, 200, response.get_json())
                data = response.get_json()
                self.assertTrue(data["ai_enhanced"])
                self.assertIn("提单号", data["ai_changes"]["fields"])

                with open(config_path, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f)
                template = saved["templates"]["target_tpl"]
                self.assertEqual(template["keywords"], ["TARGET", "BILL OF LADING", "MAERSK LINE"])
                self.assertIn("Container No.", template["table_headers"])
                self.assertIn("Gross Weight", template["table_headers"])
                field_cfg = template["fields"]["提单号"]
                self.assertIn("B/L No.", field_cfg["anchors"])
                self.assertEqual(field_cfg["value_pattern"], r"^BL\d+$")
                self.assertFalse(field_cfg["multi_line"])
            finally:
                app_module._jobs.pop(job_id, None)
                app_module.config_yaml_path = old_config_yaml_path
                app_module.get_extractor = old_get_extractor
                if old_ai_enhance is None:
                    try:
                        delattr(app_module, "ai_enhance_feedback_template")
                    except AttributeError:
                        pass
                else:
                    app_module.ai_enhance_feedback_template = old_ai_enhance


if __name__ == "__main__":
    unittest.main()

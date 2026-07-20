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
    apply_ai_fewshot_enhancement,
    apply_ai_template_enhancement,
    apply_ocr_feedback_learning,
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

    def test_anchor_layout_detection_is_sanitized_without_keywords(self):
        detection = app_module._sanitize_anchor_layout_detection({
            "mode": "anchor_layout",
            "min_score": 0.2,
            "min_matches": 99,
            "features": [
                {"text": "陌生标签", "x": 0.25, "y": 0.4, "weight": 8, "role": "field_anchor"},
                {"text": "越界", "x": 2, "y": 0.5},
            ],
        })

        self.assertEqual(detection["mode"], "anchor_layout")
        self.assertEqual(detection["min_score"], 0.35)
        self.assertEqual(detection["features"][0]["weight"], 3.0)
        self.assertEqual(len(detection["features"]), 1)

    def test_feedback_signature_comes_from_ocr_text_and_coordinates(self):
        blocks = [
            {"text": "完全陌生确认书", "rect": [300, 20, 700, 60]},
            {"text": "陌生标签", "rect": [50, 100, 180, 140]},
            {"text": "ABC-001", "rect": [250, 100, 400, 140]},
        ]
        detection = app_module._feedback_layout_signature(
            blocks,
            {"fields": {"陌生标签": {"anchors": ["陌生标签"]}}},
            ["陌生标签"],
            {"陌生标签": {"value": "ABC-001"}},
            [1000, 1000],
        )

        self.assertEqual(detection["mode"], "anchor_layout")
        texts = {feature["text"] for feature in detection["features"]}
        self.assertIn("陌生标签", texts)
        self.assertIn("完全陌生确认书", texts)
        self.assertNotIn("ABC-001", texts)

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

    def test_manual_field_payload_preserves_ocr_position_metadata(self):
        payload = normalize_corrections_payload({
            "manual_fields": [{
                "key": "gross_weight",
                "label": "Gross Weight",
                "value": "4292 KG",
                "anchor_text": "Gross Weight",
                "anchor_rect": [10, 20, 80, 45],
                "value_rect": [130, 20, 220, 45],
                "position": "right",
                "learned_value_offset": {
                    "dx": 130,
                    "dy": 0,
                    "tolerance_x": 90,
                    "tolerance_y": 45,
                },
            }],
            "excluded_fields": ["old_field"],
        })

        self.assertEqual(payload["excluded_fields"], ["old_field"])
        manual = payload["manual_fields"][0]
        self.assertEqual(manual["anchor_text"], "Gross Weight")
        self.assertEqual(manual["anchor_rect"], [10.0, 20.0, 80.0, 45.0])
        self.assertEqual(manual["value_rect"], [130.0, 20.0, 220.0, 45.0])
        self.assertEqual(manual["position"], "right")
        self.assertEqual(manual["learned_value_offset"]["dx"], 130.0)

    def test_apply_corrections_marks_excluded_fields_and_keeps_manual_positions(self):
        result = apply_corrections(
            {
                "fields": {
                    "keep": {"label": "Keep", "value": "A", "cleaned": "A", "status": "extracted"},
                    "drop": {"label": "Drop", "value": "B", "cleaned": "B", "status": "extracted"},
                },
                "meta": {},
            },
            {
                "manual_fields": [{
                    "key": "gross_weight",
                    "label": "Gross Weight",
                    "value": "4292 KG",
                    "anchor_text": "Gross Weight",
                    "anchor_rect": [10, 20, 80, 45],
                    "value_rect": [130, 20, 220, 45],
                    "position": "right",
                }],
                "excluded_fields": ["drop"],
            },
        )

        self.assertTrue(result["fields"]["drop"]["excluded"])
        self.assertEqual(result["excluded_fields"], ["drop"])
        manual = result["fields"]["gross_weight"]
        self.assertEqual(manual["anchor"], "Gross Weight")
        self.assertEqual(manual["anchor_text"], "Gross Weight")
        self.assertEqual(manual["anchor_rect"], [10.0, 20.0, 80.0, 45.0])
        self.assertEqual(manual["value_rect"], [130.0, 20.0, 220.0, 45.0])
        self.assertEqual(manual["position"], "right")

    def test_build_field_values_skips_excluded_fields(self):
        values = build_field_values({
            "keep": {"label": "Keep", "value": "A", "cleaned": "A"},
            "drop": {"label": "Drop", "value": "B", "cleaned": "B", "excluded": True},
        })

        self.assertEqual(values, {"Keep": "A"})

    def test_export_json_field_details_skips_excluded_fields(self):
        result = {
            "fields": {
                "keep": {"label": "Keep", "value": "A", "cleaned": "A"},
                "drop": {"label": "Drop", "value": "B", "cleaned": "B", "excluded": True},
            },
            "excluded_fields": ["drop"],
            "meta": {},
        }

        payload = build_export_json_payload(
            result,
            {"field_values": False, "field_details": True, "table": False, "meta": False},
        )

        self.assertEqual(set(payload["fields"].keys()), {"keep"})
        self.assertNotIn("excluded_fields", payload)

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

    def test_ocr_feedback_learning_links_manual_value_to_ocr_offset(self):
        target_template = {
            "fields": {
                "原产国": {
                    "label": "原产国",
                    "anchors": ["原产国"],
                    "position": "right",
                    "value_pattern": r"^[A-Z]+$",
                }
            }
        }
        final_fields = {
            "原产国": {
                "label": "原产国",
                "corrected": "韩国",
                "status": "corrected",
            }
        }
        blocks = [
            {"text": "原产国", "rect": [840, 356, 932, 393], "confidence": 1.0},
            {"text": "韩国", "rect": [1114, 356, 1178, 395], "confidence": 1.0},
        ]
        warnings = []

        changes = apply_ocr_feedback_learning(
            target_template,
            final_fields,
            selected_fields=["原产国"],
            blocks=blocks,
            warnings=warnings,
        )

        field_cfg = target_template["fields"]["原产国"]
        self.assertTrue(changes["applied"])
        self.assertIn("原产国", changes["fields"])
        self.assertEqual(field_cfg["position"], "right")
        self.assertNotIn("value_pattern", field_cfg)
        self.assertEqual(field_cfg["learned_sample_value"], "韩国")
        self.assertIn("learned_value_offset", field_cfg)
        self.assertGreater(field_cfg["learned_value_offset"]["dx"], 0)
        self.assertTrue(any("value_pattern" in item for item in warnings))

    def test_ocr_feedback_learning_uses_bound_manual_field_rects_before_text_lookup(self):
        target_template = {"fields": {}}
        final_fields = {
            "gross_weight": {
                "label": "Gross Weight",
                "value": "4292 KG",
                "status": "manual_added",
                "source": "manual",
                "anchor_text": "Gross Weight",
                "anchor_rect": [10, 20, 80, 45],
                "value_rect": [130, 20, 220, 45],
            }
        }
        warnings = []

        changes = apply_ocr_feedback_learning(
            target_template,
            final_fields,
            selected_fields=["gross_weight"],
            blocks=[],
            warnings=warnings,
        )

        field_cfg = target_template["fields"]["gross_weight"]
        self.assertTrue(changes["applied"])
        self.assertEqual(field_cfg["anchors"], ["Gross Weight", "gross_weight"])
        self.assertEqual(field_cfg["position"], "right")
        self.assertEqual(field_cfg["learned_sample_value"], "4292 KG")
        self.assertGreater(field_cfg["learned_value_offset"]["dx"], 0)
        self.assertEqual(warnings, [])

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

    def test_build_export_json_payload_includes_multiple_tables(self):
        result = {
            "fields": {
                "TO:": {
                    "label": "TO:",
                    "value": "K. A. Sparrow",
                    "cleaned": "K. A. Sparrow",
                    "status": "extracted",
                }
            },
            "table": {
                "title": "WITHIN THE REGION",
                "headers": ["NAME OF ACCOUNT", "NO. OF STORES"],
                "rows": [["Sico Serve", "18"]],
            },
            "tables": [
                {
                    "title": "WITHIN THE REGION",
                    "headers": ["NAME OF ACCOUNT", "NO. OF STORES"],
                    "rows": [["Sico Serve", "18"]],
                },
                {
                    "title": "OUTSIDE THE REGION",
                    "headers": ["NAME OF ACCOUNT", "NO. OF STORES"],
                    "rows": [["Kroger", "21"]],
                },
            ],
            "meta": {},
        }

        payload = build_export_json_payload(
            result,
            {
                "field_values": True,
                "field_details": False,
                "table": True,
                "meta": False,
            },
        )

        self.assertIn("table", payload)
        self.assertIn("tables", payload)
        self.assertEqual(len(payload["tables"]), 2)
        self.assertEqual(payload["tables"][1]["title"], "OUTSIDE THE REGION")

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

    def test_apply_ai_fewshot_enhancement_merges_suggestions_and_regenerates_yaml(self):
        learned = {
            "template_name": "bol_learned",
            "keywords": [],
            "source": "fewshot",
            "detection": {
                "mode": "anchor_layout",
                "min_score": 0.55,
                "min_matches": 2,
                "features": [
                    {"text": "提单号", "x": 0.1, "y": 0.2, "weight": 1.0, "role": "field_anchor"},
                    {"text": "承运人", "x": 0.1, "y": 0.1, "weight": 1.0, "role": "stable_text"},
                ],
            },
            "fields": {
                "提单号": {
                    "label": "提单号",
                    "canonical_key": "bl_no",
                    "anchors": ["提单号"],
                    "position": "right",
                }
            },
            "validators": {},
            "yaml_text": "old yaml",
        }
        warnings = []

        changes = apply_ai_fewshot_enhancement(
            learned,
            {
                "template_keywords": ["MAERSK LINE"],
                "fields": [
                    {
                        "field": "提单号",
                        "label": "提单号",
                        "anchors": ["B/L No.", "Bill of Lading No."],
                        "position": "right",
                        "value_pattern": r"^[A-Z]{2}\d+$",
                        "multi_line": False,
                        "allow_shared": False,
                        "confidence": 0.92,
                        "notes": "AI enhanced",
                    }
                ],
                "table_headers": ["Container No.", "Gross Weight"],
                "warnings": ["表头来自 AI 增强"],
            },
            warnings,
        )

        self.assertTrue(changes["applied"])
        self.assertEqual(learned["keywords"], [])
        self.assertNotIn("MAERSK LINE", learned["yaml_text"])
        self.assertIn("anchor_layout", learned["yaml_text"])
        self.assertIn("提单号", learned["detection"]["features"][0]["text"])
        self.assertIn("B/L No.", learned["fields"]["提单号"]["anchors"])
        self.assertEqual(learned["fields"]["提单号"]["value_pattern"], r"^[A-Z]{2}\d+$")
        self.assertTrue(learned["has_table"])
        self.assertEqual(learned["table_headers"], ["Container No.", "Gross Weight"])
        self.assertIn("B/L No.", learned["yaml_text"])
        self.assertIn("AI 增强：表头来自 AI 增强", warnings)


    def test_ai_template_enhancement_malformed_model_payload_warns_without_raising(self):
        target_template = {
            "keywords": ["TARGET"],
            "fields": {"Field A": {"label": "Field A", "anchors": ["Field A"]}},
            "table_headers": [],
        }
        warnings = []

        changes = apply_ai_template_enhancement(
            target_template,
            {
                "template_keywords": 123,
                "fields": {"field": "Field A"},
                "table_headers": 456,
                "warnings": 789,
            },
            selected_fields=["Field A"],
            include_table=True,
            warnings=warnings,
        )

        self.assertFalse(changes["applied"])
        self.assertEqual(target_template["keywords"], ["TARGET"])
        self.assertTrue(any("AI" in warning for warning in warnings))

    def test_feedback_ai_enhance_bad_model_payload_does_not_break_feedback(self):
        old_get_vision_fallback = app_module.get_vision_fallback
        old_find_original_file = app_module.find_original_file
        old_render_first_page = app_module.render_first_page_for_vision
        old_load_blocks = app_module.load_blocks

        class FakeClient:
            def unavailable_reason(self):
                return None

            def enhance_template_config(self, **kwargs):
                return {
                    "success": True,
                    "result": {
                        "template_keywords": 123,
                        "fields": {"field": "Field A"},
                        "table_headers": 456,
                        "warnings": 789,
                    },
                }

        warnings = []
        target_template = {
            "keywords": ["TARGET"],
            "fields": {"Field A": {"label": "Field A", "anchors": ["Field A"]}},
            "output": ["Field A"],
        }

        try:
            app_module.get_vision_fallback = lambda: FakeClient()
            app_module.find_original_file = lambda job_id: ("sample.pdf", "pdf")
            app_module.render_first_page_for_vision = lambda file_path, file_type, tmp_dir: "sample.png"
            app_module.load_blocks = lambda job_id: []

            changes = app_module.ai_enhance_feedback_template(
                job_id="abcdef123456",
                template_name="target_tpl",
                target_template=target_template,
                final_result={"fields": {"Field A": {"label": "Field A", "value": "ABC"}}},
                selected_fields=["Field A"],
                include_table=True,
                warnings=warnings,
            )

            self.assertFalse(changes["applied"])
            self.assertTrue(any("AI" in warning for warning in warnings))
        finally:
            app_module.get_vision_fallback = old_get_vision_fallback
            app_module.find_original_file = old_find_original_file
            app_module.render_first_page_for_vision = old_render_first_page
            app_module.load_blocks = old_load_blocks

    def test_fewshot_ai_enhance_bad_model_payload_does_not_break_learning(self):
        old_get_vision_fallback = app_module.get_vision_fallback
        old_render_first_page = app_module.render_first_page_for_vision

        class FakeClient:
            def unavailable_reason(self):
                return None

            def enhance_template_config(self, **kwargs):
                return {
                    "success": True,
                    "result": {
                        "template_keywords": 123,
                        "fields": {"field": "Field A"},
                        "table_headers": 456,
                        "warnings": 789,
                    },
                }

        learned = {
            "template_name": "bad_ai_payload",
            "keywords": ["TARGET"],
            "fields": {"Field A": {"label": "Field A", "anchors": ["Field A"]}},
            "has_table": False,
            "table_headers": [],
            "yaml_text": "old yaml",
        }
        warnings = []

        try:
            app_module.get_vision_fallback = lambda: FakeClient()
            app_module.render_first_page_for_vision = lambda file_path, file_type, tmp_dir: "sample.png"

            changes = app_module.ai_enhance_fewshot_learning(
                [("sample.txt", {"Field A": "ABC"})],
                learned,
                warnings,
            )

            self.assertFalse(changes["applied"])
            self.assertFalse(learned["ai_enhanced"])
            self.assertTrue(any("AI" in warning for warning in warnings))
        finally:
            app_module.get_vision_fallback = old_get_vision_fallback
            app_module.render_first_page_for_vision = old_render_first_page


if __name__ == "__main__":
    unittest.main()

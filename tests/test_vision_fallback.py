import os
import sys
import json
import tempfile
import unittest
import base64

# 低置信度分流与视觉兜底结果归一化的快速单元测试。

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from vision_fallback import (
    VisionFallbackClient,
    _field_schema,
    attach_quality_meta,
    default_vision_settings,
    evaluate_recognition_quality,
    merge_vision_fallback_result,
    normalize_vision_model,
    normalize_vision_payload,
    provider_defaults,
    vision_settings_options,
)


def block(text, confidence=0.95):
    return {
        "text": text,
        "rect": [0, 0, 10, 10],
        "confidence": confidence,
    }


class VisionFallbackRoutingTest(unittest.TestCase):
    def test_qwen_default_model_uses_current_available_model(self):
        self.assertEqual(provider_defaults("qwen")["default_model"], "qwen-3.6-flash")
        self.assertEqual(default_vision_settings()["model"], "qwen-3.6-flash")
        self.assertEqual(normalize_vision_model("qwen", "qwen-vl-plus"), "qwen-3.6-flash")

    def test_ollama_provider_defaults_to_native_local_model(self):
        ollama = provider_defaults("ollama")
        providers = {item["key"] for item in vision_settings_options()["providers"]}

        self.assertIn("ollama", providers)
        self.assertEqual(ollama["default_model"], "qwen3-vl:8b")
        self.assertEqual(ollama["default_base_url"], "http://localhost:11434")
        self.assertEqual(ollama["transport"], "ollama_chat")
        self.assertFalse(ollama["requires_api_key"])

    def test_custom_provider_defaults_to_openai_compatible_model(self):
        custom = provider_defaults("custom")
        providers = {item["key"] for item in vision_settings_options()["providers"]}

        self.assertIn("custom", providers)
        self.assertEqual(custom["default_model"], "custom-vision-model")
        self.assertEqual(custom["default_base_url"], "http://localhost:9000/v1")
        self.assertTrue(custom["requires_api_key"])

    def test_ollama_provider_uses_native_chat_without_required_api_key(self):
        client = VisionFallbackClient(
            enabled=True,
            settings={
                "provider": "ollama",
                "model": "qwen3-vl:8b",
                "base_url": "http://localhost:11434",
                "api_key": "",
            },
        )

        self.assertIsNone(client.unavailable_reason())
        self.assertEqual(client.api_key, "ollama")
        self.assertEqual(client.endpoint, "http://localhost:11434/api/chat")
        self.assertEqual(client.endpoint_type, "ollama_chat")

    def test_ollama_payload_uses_native_images_and_num_ctx(self):
        fd, image_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        with open(image_path, "wb") as fh:
            fh.write(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            ))
        try:
            client = VisionFallbackClient(
                enabled=True,
                settings={
                    "provider": "ollama",
                    "model": "qwen3-vl:8b",
                    "base_url": "http://localhost:11434",
                    "api_key": "",
                },
            )

            payload = client._build_payload("Return JSON", image_path)

            self.assertEqual(payload["model"], "qwen3-vl:8b")
            self.assertEqual(payload["format"], "json")
            self.assertFalse(payload["stream"])
            self.assertEqual(payload["options"]["num_ctx"], 8192)
            self.assertIn("images", payload["messages"][0])
            self.assertIsInstance(payload["messages"][0]["images"][0], str)
            self.assertNotIn("response_format", payload)
        finally:
            os.remove(image_path)

    def test_ollama_failure_warning_explains_local_compute_limits(self):
        client = VisionFallbackClient(
            enabled=True,
            settings={
                "provider": "ollama",
                "model": "qwen3-vl:8b",
                "base_url": "http://localhost:11434",
                "api_key": "",
            },
        )

        warning = client.failure_warning("timed out")

        self.assertIn("Ollama", warning)
        self.assertIn("本地模型", warning)
        self.assertIn("高性能电脑或服务器", warning)
        self.assertIn("timed out", warning)

    def test_custom_provider_accepts_full_chat_completions_endpoint(self):
        client = VisionFallbackClient(
            api_key="local-key",
            enabled=True,
            settings={
                "provider": "custom",
                "model": "my-vision-model",
                "base_url": "http://localhost:9000/v1/chat/completions",
            },
        )

        self.assertEqual(client.endpoint, "http://localhost:9000/v1/chat/completions")

    def test_high_confidence_local_rules_do_not_trigger_fallback(self):
        result = {
            "template": "maersk_style",
            "fields": {
                "Shipper": {"status": "extracted", "value": "ACME", "confidence": 0.92},
                "B/L No.": {"status": "extracted", "value": "BL123", "confidence": 0.95},
            },
            "meta": {"fields_total": 2, "fields_extracted": 2},
            "debug": {
                "extraction": {
                    "template_scores": {"maersk_style": {"score": 0.82}, "simple_style": {"score": 0.12}},
                    "fields": {
                        "Shipper": {"candidates": [{"score": 0.9}], "rejected": []},
                        "B/L No.": {"candidates": [{"score": 0.95}], "rejected": []},
                    },
                }
            },
        }

        quality = evaluate_recognition_quality(result, [block("MAERSK LINE"), block("Shipper ACME")], threshold=0.55)

        self.assertFalse(quality["should_fallback"])
        self.assertGreaterEqual(quality["overall_confidence"], 0.55)

    def test_unknown_template_triggers_fallback(self):
        result = {
            "template": "unknown",
            "fields": {},
            "meta": {"fields_total": 0, "fields_extracted": 0},
            "debug": {"extraction": {"template_scores": {}, "fields": {}}},
        }

        quality = evaluate_recognition_quality(result, [block("random form")], threshold=0.55)

        self.assertTrue(quality["should_fallback"])
        self.assertIn("template_unknown", quality["fallback_reasons"])

    def test_funsd_low_coverage_triggers_fallback(self):
        result = {
            "template": "funsd_public",
            "fields": {
                "FROM": {"status": "extracted", "value": "Alice", "confidence": 0.7},
                "TO": {"status": "not_found", "value": "", "confidence": 0.0},
                "SUBJECT": {"status": "not_found", "value": "", "confidence": 0.0},
            },
            "meta": {"fields_total": 3, "fields_extracted": 1},
            "debug": {
                "extraction": {
                    "template_scores": {"funsd_public": {"score": 0.5}},
                    "fields": {},
                }
            },
        }

        quality = evaluate_recognition_quality(result, [block("FROM Alice"), block("memo body")], threshold=0.3)

        self.assertTrue(quality["should_fallback"])
        self.assertIn("funsd_public_low_field_coverage", quality["fallback_reasons"])

    def test_vision_payload_uses_original_labels_as_field_keys(self):
        payload = {
            "document_type": "delivery_note",
            "fields": [
                {"label": "经营单位", "value": "华贸进出口有限公司", "confidence": 0.88},
                {"label": "经营单位", "value": "重复字段测试", "confidence": 0.6},
            ],
        }

        normalized = normalize_vision_payload(payload)

        self.assertEqual(normalized["template"], "vision_generic")
        self.assertIn("经营单位", normalized["fields"])
        self.assertIn("经营单位_2", normalized["fields"])
        self.assertEqual(normalized["fields"]["经营单位"]["canonical_key"], None)
        self.assertEqual(normalized["fields"]["经营单位"]["source"], "vision_fallback")

    def test_vision_schema_accepts_structured_tables(self):
        schema = _field_schema()

        self.assertIn("tables", schema["properties"])
        table_item = schema["properties"]["tables"]["items"]
        self.assertIn("title", table_item["properties"])
        self.assertIn("headers", table_item["properties"])
        self.assertIn("rows", table_item["properties"])
        self.assertIn("confidence", table_item["properties"])

    def test_vision_payload_converts_key_value_grid_table_back_to_fields(self):
        payload = {
            "document_type": "customs_declaration",
            "fields": [
                {"label": "\u6d77\u5173\u7f16\u53f7", "value": "CUS29603543", "confidence": 0.98},
                {"label": "\u7533\u62a5\u65e5\u671f", "value": "2024/11/04", "confidence": 0.98},
            ],
            "tables": [
                {
                    "title": "",
                    "headers": [
                        "\u8fdb\u53e3\u53e3\u5cb8",
                        "\u5b81\u6ce2\u6d77\u5173",
                        "\u8fd0\u8f93\u65b9\u5f0f",
                        "\u6d77\u8fd0",
                    ],
                    "rows": [
                        [
                            "\u7ecf\u8425\u5355\u4f4d",
                            "\u534e\u8d38\u8fdb\u51fa\u53e3\u6709\u9650\u516c\u53f8",
                            "\u6536\u8d27\u5355\u4f4d",
                            "\u4e2d\u5546\u56fd\u9645\u8d38\u6613\u516c\u53f8",
                        ],
                        [
                            "\u5546\u54c1\u540d\u79f0",
                            "\u7eba\u7ec7\u54c1",
                            "\u6570\u91cf\u53ca\u5355\u4f4d",
                            "67 \u4ef6",
                        ],
                        [
                            "\u603b\u4ef7",
                            "14991 USD",
                            "\u539f\u4ea7\u56fd",
                            "\u97e9\u56fd",
                        ],
                        [
                            "\u6bdb\u91cd",
                            "4292 KG",
                            "\u51c0\u91cd",
                            "3853 KG",
                        ],
                    ],
                    "confidence": 0.98,
                }
            ],
        }

        normalized = normalize_vision_payload(payload)

        self.assertEqual(len(normalized["tables"]), 0)
        self.assertEqual(normalized["table"], {})
        expected_fields = {
            "\u6d77\u5173\u7f16\u53f7",
            "\u7533\u62a5\u65e5\u671f",
            "\u8fdb\u53e3\u53e3\u5cb8",
            "\u8fd0\u8f93\u65b9\u5f0f",
            "\u7ecf\u8425\u5355\u4f4d",
            "\u6536\u8d27\u5355\u4f4d",
            "\u5546\u54c1\u540d\u79f0",
            "\u6570\u91cf\u53ca\u5355\u4f4d",
            "\u603b\u4ef7",
            "\u539f\u4ea7\u56fd",
            "\u6bdb\u91cd",
            "\u51c0\u91cd",
        }
        self.assertEqual(set(normalized["fields"].keys()), expected_fields)
        self.assertEqual(normalized["fields"]["\u8fdb\u53e3\u53e3\u5cb8"]["value"], "\u5b81\u6ce2\u6d77\u5173")
        self.assertEqual(normalized["fields"]["\u8fd0\u8f93\u65b9\u5f0f"]["value"], "\u6d77\u8fd0")
        self.assertEqual(normalized["fields"]["\u603b\u4ef7"]["value"], "14991 USD")
        self.assertEqual(normalized["fields"]["\u51c0\u91cd"]["value"], "3853 KG")

    def test_vision_extract_supplements_missing_key_value_grid_from_ocr_blocks(self):
        class SparseVisionClient(VisionFallbackClient):
            def _post_json(self, payload):
                model_payload = {
                    "document_type": "customs_declaration",
                    "fields": [
                        {"label": "\u6d77\u5173\u7f16\u53f7", "value": "CUS29603543", "confidence": 0.98},
                        {"label": "\u7533\u62a5\u65e5\u671f", "value": "2024/11/04", "confidence": 0.98},
                    ],
                    "tables": [],
                }
                return {"output_text": json.dumps(model_payload, ensure_ascii=False)}

        def ocr_cell(text, left, top, right, bottom, confidence=0.99):
            return {"text": text, "rect": [left, top, right, bottom], "confidence": confidence}

        blocks = [
            ocr_cell("\u6d77\u5173\u7f16\u53f7\uff1aCUS29603543", 547, 112, 816, 146),
            ocr_cell("\u7533\u62a5\u65e5\u671f\uff1a2024/11/04", 855, 112, 1111, 146),
            ocr_cell("\u8fdb\u53e3\u53e3\u5cb8", 67, 178, 195, 222),
            ocr_cell("\u5b81\u6ce2\u6d77\u5173", 347, 181, 463, 217),
            ocr_cell("\u8fd0\u8f93\u65b9\u5f0f", 830, 176, 964, 217),
            ocr_cell("\u6d77\u8fd0", 1111, 181, 1178, 220),
            ocr_cell("\u7ecf\u8425\u5355\u4f4d", 67, 237, 197, 281),
            ocr_cell("\u534e\u8d38\u8fdb\u51fa\u53e3\u6709\u9650\u516c\u53f8", 347, 237, 596, 278),
            ocr_cell("\u6536\u8d27\u5355\u4f4d", 835, 239, 961, 278),
            ocr_cell("\u4e2d\u5546\u56fd\u9645\u8d38\u6613\u516c\u53f8", 1119, 242, 1336, 276),
            ocr_cell("\u5546\u54c1\u540d\u79f0", 67, 295, 195, 337),
            ocr_cell("\u7eba\u7ec7\u54c1", 347, 298, 436, 334),
            ocr_cell("\u6570\u91cf\u53ca\u5355\u4f4d", 835, 295, 993, 337),
            ocr_cell("67\u4ef6", 1111, 295, 1198, 339),
            ocr_cell("\u603b\u4ef7", 67, 351, 138, 398),
            ocr_cell("14991 USD", 347, 354, 490, 395),
            ocr_cell("\u539f\u4ea7\u56fd", 840, 356, 932, 393),
            ocr_cell("\u97e9\u56fd", 1114, 356, 1178, 395),
            ocr_cell("\u6bdb\u91cd", 67, 415, 136, 454),
            ocr_cell("4292 KG", 347, 415, 456, 451),
            ocr_cell("\u51c0\u91cd", 835, 415, 904, 454),
            ocr_cell("3853 KG", 1114, 415, 1225, 451),
        ]
        client = SparseVisionClient(api_key="dummy", enabled=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = os.path.join(tmp_dir, "fake.png")
            with open(image_path, "wb") as image:
                image.write(b"fake")
            result = client.extract(image_path, blocks, {"fields": {}}, {})

        self.assertTrue(result["success"])
        fields = result["result"]["fields"]
        self.assertEqual(len(fields), 12)
        self.assertEqual(fields["\u8fdb\u53e3\u53e3\u5cb8"]["value"], "\u5b81\u6ce2\u6d77\u5173")
        self.assertEqual(fields["\u7ecf\u8425\u5355\u4f4d"]["value"], "\u534e\u8d38\u8fdb\u51fa\u53e3\u6709\u9650\u516c\u53f8")
        self.assertEqual(fields["\u603b\u4ef7"]["value"], "14991 USD")
        self.assertEqual(fields["\u51c0\u91cd"]["value"], "3853 KG")
        self.assertEqual(result["result"]["tables"], [])

    def test_vision_payload_normalizes_multiple_tables_without_duplicate_fields(self):
        payload = {
            "document_type": "progress_report",
            "fields": [
                {"label": "TO:", "value": "K. A. Sparrow", "confidence": 0.95},
                {"label": "SUBJECT:", "value": "STYLE LOW PRICE - PROGRESS REPORT", "confidence": 0.94},
            ],
            "tables": [
                {
                    "title": "DIRECT ACCOUNTS AND CHAINS HEADQUARTERED WITHIN THE REGION",
                    "headers": ["NAME OF ACCOUNT", "IND/LOR VOLUME", "NO. OF STORES"],
                    "rows": [
                        ["Sico Serve", "104/22", "18"],
                        ["Sheetz", "521/42", "150"],
                    ],
                    "confidence": 0.9,
                },
                {
                    "title": "DIRECT ACCOUNTS AND CHAINS HEADQUARTERED OUTSIDE THE REGION",
                    "headers": ["NAME OF ACCOUNT", "IND/LOR VOLUME", "NO. OF STORES"],
                    "rows": [
                        ["Kroger", "", "21"],
                        ["Rich Oil", "", "82"],
                    ],
                    "confidence": 0.88,
                },
            ],
        }

        normalized = normalize_vision_payload(payload)

        self.assertEqual(set(normalized["fields"].keys()), {"TO:", "SUBJECT:"})
        self.assertNotIn("NO. OF STORES", normalized["fields"])
        self.assertEqual(len(normalized["tables"]), 2)
        self.assertEqual(normalized["tables"][0]["title"], "DIRECT ACCOUNTS AND CHAINS HEADQUARTERED WITHIN THE REGION")
        self.assertEqual(normalized["tables"][0]["headers"], ["NAME OF ACCOUNT", "IND/LOR VOLUME", "NO. OF STORES"])
        self.assertEqual(normalized["tables"][0]["rows"][1], ["Sheetz", "521/42", "150"])
        self.assertEqual(normalized["table"], normalized["tables"][0])

    def test_merge_vision_result_replaces_low_confidence_local_fields(self):
        local = {
            "template": "unknown",
            "fields": {},
            "table": {"headers": [], "rows": []},
            "meta": {"ocr_blocks": 10},
        }
        quality = {"overall_confidence": 0.2, "fallback_reasons": ["template_unknown"]}
        vision = normalize_vision_payload({
            "document_type": "customs",
            "fields": [{"label": "海关编号", "value": "CUS123", "confidence": 0.93}],
        })

        merged = merge_vision_fallback_result(local, vision, quality)

        self.assertEqual(merged["template"], "vision_generic")
        self.assertEqual(merged["meta"]["extraction_source"], "vision_fallback")
        self.assertEqual(merged["meta"]["fields_total"], 1)
        self.assertIn("海关编号", merged["fields"])

    def test_merge_vision_result_preserves_tables_and_updates_table_meta(self):
        local = {
            "template": "unknown",
            "fields": {},
            "table": {"headers": [], "rows": []},
            "meta": {"ocr_blocks": 10},
        }
        quality = {"overall_confidence": 0.2, "fallback_reasons": ["template_unknown"]}
        vision = normalize_vision_payload({
            "document_type": "progress_report",
            "fields": [{"label": "TO:", "value": "K. A. Sparrow", "confidence": 0.93}],
            "tables": [
                {
                    "title": "WITHIN THE REGION",
                    "headers": ["NAME OF ACCOUNT", "NO. OF STORES"],
                    "rows": [["Sico Serve", "18"], ["Sheetz", "150"]],
                    "confidence": 0.91,
                },
                {
                    "title": "OUTSIDE THE REGION",
                    "headers": ["NAME OF ACCOUNT", "NO. OF STORES"],
                    "rows": [["Kroger", "21"]],
                    "confidence": 0.89,
                },
            ],
        })

        merged = merge_vision_fallback_result(local, vision, quality)

        self.assertEqual(merged["meta"]["extraction_source"], "vision_fallback")
        self.assertEqual(merged["meta"]["table_count"], 2)
        self.assertEqual(merged["meta"]["table_rows"], 3)
        self.assertEqual(len(merged["tables"]), 2)
        self.assertEqual(merged["table"], merged["tables"][0])

    def test_disabled_client_returns_warning_without_api_call(self):
        client = VisionFallbackClient(api_key=None, enabled=False)
        result = client.extract("not-needed.png", [], {}, {})

        self.assertFalse(result["success"])
        self.assertIn("VISION_FALLBACK_ENABLED", result["warning"])

    def test_default_timeout_gives_document_vision_enough_time(self):
        client = VisionFallbackClient(api_key="dummy", enabled=True)

        self.assertEqual(client.timeout, 90.0)

    def test_attach_quality_meta_preserves_local_rules_source(self):
        result = {"meta": {"template": "maersk_style"}, "fields": {}}
        quality = {
            "overall_confidence": 0.7,
            "template_score": 0.8,
            "template_score_gap": 0.5,
            "field_coverage": 1.0,
            "avg_field_score": 0.9,
            "rejected_ratio": 0.0,
            "ocr_text_quality": 0.9,
        }

        updated = attach_quality_meta(result, quality)

        self.assertEqual(updated["meta"]["extraction_source"], "local_rules")
        self.assertEqual(updated["meta"]["confidence"], 0.7)


if __name__ == "__main__":
    unittest.main()

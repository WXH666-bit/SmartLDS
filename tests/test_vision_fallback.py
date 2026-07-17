import os
import sys
import unittest

# 低置信度分流与视觉兜底结果归一化的快速单元测试。

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from vision_fallback import (
    VisionFallbackClient,
    attach_quality_meta,
    default_vision_settings,
    evaluate_recognition_quality,
    merge_vision_fallback_result,
    normalize_vision_model,
    normalize_vision_payload,
    provider_defaults,
)


def block(text, confidence=0.95):
    return {
        "text": text,
        "rect": [0, 0, 10, 10],
        "confidence": confidence,
    }


class VisionFallbackRoutingTest(unittest.TestCase):
    def test_qwen_default_model_uses_current_available_model(self):
        self.assertEqual(provider_defaults("qwen")["default_model"], "qwen3.6-plus")
        self.assertEqual(default_vision_settings()["model"], "qwen3.6-plus")
        self.assertEqual(normalize_vision_model("qwen", "qwen-vl-plus"), "qwen3.6-plus")

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

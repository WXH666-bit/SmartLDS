import unittest
import os
import sys

# 字段抽取增强逻辑的快速单元测试。

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
from field_extractor import FieldExtractor
from fewshot import FewShotLearner


def block(text, x1, y1, x2, y2, confidence=0.95):
    return {
        "text": text,
        "rect": [x1, y1, x2, y2],
        "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "confidence": confidence,
    }


class EnhancedFieldExtractorTest(unittest.TestCase):
    def make_extractor(self):
        extractor = FieldExtractor()
        extractor.config = {
            "validators": {
                "date": {"pattern": r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"},
                "amount": {"pattern": r"\$?\s*\d+(\.\d+)?"},
            },
            "field_defaults": {
                "value": "",
                "cleaned": "",
                "confidence": 0.0,
                "status": "not_found",
                "anchor_text": "",
                "rect": [0, 0, 0, 0],
            },
            "templates": {
                "demo": {
                    "keywords": ["DEMO FORM", "SHIPPER"],
                    "has_table": False,
                    "fields": {
                        "shipper": {
                            "label": "Shipper",
                            "anchors": ["Shipper"],
                            "position": "right",
                            "multi_line": True,
                        },
                        "date": {
                            "label": "Date",
                            "anchors": ["Place & Date of Issue", "Date"],
                            "position": "either",
                            "validator": "date",
                            "value_pattern": r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
                            "allow_shared": True,
                        },
                        "place": {
                            "label": "Place",
                            "anchors": ["Place & Date of Issue"],
                            "position": "right",
                            "allow_shared": True,
                        },
                        "amount": {
                            "label": "Amount",
                            "anchors": ["Total"],
                            "position": "right",
                            "validator": "amount",
                            "value_pattern": r"\$?\s*\d+(\.\d+)?",
                        },
                    },
                    "output": ["shipper", "date", "place", "amount"],
                }
            },
        }
        return extractor

    def test_candidate_scoring_multiline_shared_and_debug(self):
        extractor = self.make_extractor()
        blocks = [
            block("DEMO FORM", 0, 0, 100, 20),
            block("Shipper:", 10, 50, 80, 70),
            block("ACME LTD", 120, 50, 220, 70),
            block("Room 501", 120, 76, 220, 94),
            block("Place & Date of Issue", 10, 130, 170, 150),
            block("NINGBO, 14/11/2025", 200, 130, 360, 150),
            block("Total:", 10, 180, 70, 200),
            block("$ 123.45", 120, 180, 200, 200),
        ]
        result = extractor.extract(
            {"header": [blocks[0]], "body": blocks[1:], "table": []},
            [400, 240],
            blocks=blocks,
        )

        self.assertEqual(result["template"], "demo")
        self.assertEqual(result["fields"]["shipper"]["value"], "ACME LTD Room 501")
        self.assertEqual(result["fields"]["date"]["cleaned"], "14/11/2025")
        self.assertIn("NINGBO", result["fields"]["place"]["value"])
        self.assertIn("123.45", result["fields"]["amount"]["cleaned"])
        self.assertIn("debug", result)
        self.assertIn("template_scores", result["debug"]["extraction"])

    def test_weak_template_evidence_stays_unknown(self):
        extractor = self.make_extractor()
        extractor.config["templates"]["other"] = {
            "keywords": ["SHIPPER", "OTHER FORM"],
            "fields": {},
            "output": [],
        }
        blocks = [block("SHIPPER", 0, 0, 80, 20)]
        result = extractor.extract({"header": blocks, "body": [], "table": []}, [100, 40], blocks=blocks)
        self.assertEqual(result["template"], "unknown")

    def test_disabled_template_does_not_match(self):
        extractor = FieldExtractor()
        extractor.config = {
            "validators": {},
            "field_defaults": {
                "value": "",
                "cleaned": "",
                "confidence": 0.0,
                "status": "not_found",
                "anchor_text": "",
                "rect": [0, 0, 0, 0],
            },
            "templates": {
                "disabled_demo": {
                    "enabled": False,
                    "hidden": True,
                    "keywords": ["FROM:"],
                    "fields": {
                        "FROM": {"label": "FROM", "anchors": ["FROM:"], "position": "right"},
                    },
                    "output": ["FROM"],
                }
            },
        }
        blocks = [block("FROM:", 0, 0, 60, 20), block("Alice", 100, 0, 160, 20)]

        result = extractor.extract({"header": blocks, "body": [], "table": []}, [200, 60], blocks=blocks)

        self.assertEqual(result["template"], "unknown")
        self.assertEqual(result["fields"], {})

    def test_template_schema_is_independent(self):
        extractor = FieldExtractor()
        extractor.config = {
            "validators": {},
            "field_defaults": {
                "value": "",
                "cleaned": "",
                "confidence": 0.0,
                "status": "not_found",
                "anchor_text": "",
                "rect": [0, 0, 0, 0],
            },
            "templates": {
                "template_a": {
                    "keywords": ["FORM A"],
                    "fields": {
                        "XXX": {"label": "XXX", "anchors": ["XXX"], "position": "right"},
                    },
                    "output": ["XXX"],
                },
                "template_b": {
                    "keywords": ["FORM B"],
                    "fields": {
                        "YYY": {"label": "YYY", "anchors": ["YYY"], "position": "right"},
                    },
                    "output": ["YYY"],
                },
            },
        }
        blocks = [
            block("FORM A", 0, 0, 80, 20),
            block("XXX", 10, 50, 60, 70),
            block("VALUE-A", 100, 50, 180, 70),
        ]
        result = extractor.extract({"header": [blocks[0]], "body": blocks[1:], "table": []}, [240, 100], blocks=blocks)
        self.assertEqual(result["template"], "template_a")
        self.assertIn("XXX", result["fields"])
        self.assertNotIn("YYY", result["fields"])
        self.assertEqual(result["fields"]["XXX"]["value"], "VALUE-A")

    def test_learned_value_offset_can_recover_far_same_row_value(self):
        extractor = FieldExtractor()
        extractor.config = {
            "validators": {},
            "field_defaults": {
                "value": "",
                "cleaned": "",
                "confidence": 0.0,
                "status": "not_found",
                "anchor_text": "",
                "rect": [0, 0, 0, 0],
            },
            "templates": {
                "customs": {
                    "keywords": ["CUSTOMS"],
                    "fields": {
                        "原产国": {
                            "label": "原产国",
                            "anchors": ["原产国"],
                            "position": "right",
                            "learned_value_offset": {
                                "dx": 480.0,
                                "dy": 0.0,
                                "tolerance_x": 80.0,
                                "tolerance_y": 40.0,
                            },
                        }
                    },
                    "output": ["原产国"],
                }
            },
        }
        blocks = [
            block("CUSTOMS", 0, 0, 80, 20),
            block("原产国", 10, 50, 80, 70),
            block("韩国", 500, 50, 550, 70),
        ]

        result = extractor.extract(
            {"header": [blocks[0]], "body": blocks[1:], "table": []},
            [600, 120],
            blocks=blocks,
        )

        self.assertEqual(result["template"], "customs")
        self.assertEqual(result["fields"]["原产国"]["value"], "韩国")
        self.assertIn("learned_offset", result["debug"]["extraction"]["fields"]["原产国"]["selected"]["reasons"])

    def test_fewshot_yaml_uses_source_label_with_canonical_key(self):
        learner = object.__new__(FewShotLearner)
        yaml_text = learner._generate_yaml(
            "custom_template",
            ["CUSTOM"],
            {
                "经营单位": {
                    "label": "经营单位",
                    "canonical_key": "company",
                    "anchors": ["经营单位"],
                    "position": "right",
                }
            },
        )
        self.assertIn('"经营单位":', yaml_text)
        self.assertIn('label: "经营单位"', yaml_text)
        self.assertIn('canonical_key: "company"', yaml_text)
        self.assertIn('output: ["经营单位"]', yaml_text)

    def test_maersk_builtin_uses_source_document_fields(self):
        extractor = FieldExtractor()
        fields = extractor.config["templates"]["maersk_style"]["fields"]
        output = extractor.config["templates"]["maersk_style"]["output"]

        self.assertIn("Shipper", fields)
        self.assertIn("B/L No.", fields)
        self.assertIn("Place & Date of Issue", fields)
        self.assertNotIn("shipper", fields)
        self.assertNotIn("issue_date", fields)
        self.assertEqual(fields["Shipper"]["canonical_key"], "shipper")
        self.assertEqual(fields["B/L No."]["canonical_key"], "bl_no")
        self.assertIn("Shipper", output)
        self.assertNotIn("shipper", output)

    def test_all_config_templates_use_source_schema(self):
        extractor = FieldExtractor()
        internal_keys = {
            "shipper", "consignee", "notify_party", "bl_no", "pol", "pod",
            "por", "delivery", "vessel", "voyage", "freight", "issue_place",
            "issue_date", "sender", "recipient", "tracking_no", "sender_name",
            "recipient_name", "company", "receiver", "goods_name",
        }
        for template_name, template in extractor.config["templates"].items():
            fields = template.get("fields", {})
            output = template.get("output", [])
            self.assertEqual(set(output), set(fields), template_name)
            for field_key, field_cfg in fields.items():
                self.assertEqual(field_cfg.get("label"), field_key, f"{template_name}.{field_key}")
                self.assertTrue(field_cfg.get("canonical_key"), f"{template_name}.{field_key}")
                self.assertNotIn(field_key, internal_keys, f"{template_name}.{field_key}")

    def test_fallback_defaults_use_source_schema(self):
        templates = FieldExtractor._migrate_default_templates_to_source_schema(
            FieldExtractor._load_config.__globals__["_DEFAULT_TEMPLATES_CONFIG"]
        )
        self.assertIn("Shipper", templates["maersk_style"]["fields"])
        self.assertNotIn("shipper", templates["maersk_style"]["fields"])
        self.assertEqual(
            templates["maersk_style"]["fields"]["Shipper"]["canonical_key"],
            "shipper",
        )


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import sys

# 字段抽取增强逻辑的快速单元测试。

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
from field_extractor import FieldExtractor, validate_and_clean
from fewshot import FewShotLearner


def block(text, x1, y1, x2, y2, confidence=0.95):
    return {
        "text": text,
        "rect": [x1, y1, x2, y2],
        "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "confidence": confidence,
    }


class _FewShotFixtureEngine:
    def __init__(self, results):
        self.results = results

    def recognize_pdf(self, path):
        return [self.results[path]]


def customs_sample_blocks(values):
    rows = [
        ("海关编号", values["customs_no"], 40),
        ("申报日期", values["declare_date"], 70),
        ("进口口岸", values["import_port"], 100),
        ("运输方式", values["transport"], 130),
        ("经营单位", values["company"], 160),
        ("收货单位", values["receiver"], 190),
        ("商品名称", values["goods_name"], 220),
        ("数量及单位", f'{values["qty"]} {values["unit"]}', 250),
        ("总价", f'{values["total_price"]} {values["currency"]}', 280),
        ("原产国", values["origin"], 310),
        ("毛重", f'{values["gross_weight"]} KG', 340),
        ("净重", f'{values["net_weight"]} KG', 370),
    ]
    blocks = [block("中华人民共和国海关进口货物报关单", 10, 5, 330, 25)]
    for label, value, y in rows:
        blocks.extend([
            block(label, 10, y, 90, y + 20),
            block(value, 120, y, 380, y + 20),
        ])
    return blocks


def two_column_customs_sample_blocks(values):
    rows = [
        (("进口口岸", values["import_port"]), ("运输方式", values["transport"]), 180),
        (("经营单位", values["company"]), ("收货单位", values["receiver"]), 240),
        (("商品名称", values["goods_name"]), ("数量及单位", f'{values["qty"]}{values["unit"]}'), 300),
        (("总价", f'{values["total_price"]} {values["currency"]}'), ("原产国", values["origin"]), 360),
        (("毛重", f'{values["gross_weight"]} KG'), ("净重", f'{values["net_weight"]} KG'), 420),
    ]
    blocks = [
        block("完全陌生的星际货物申报确认书", 540, 60, 1110, 95),
        block(f'海关编号：{values["customs_no"]}', 540, 115, 820, 150),
        block(f'申报日期：{values["declare_date"]}', 850, 115, 1120, 150),
    ]
    for left, right, y in rows:
        blocks.extend([
            block(left[0], 70, y, 200, y + 40),
            block(left[1], 350, y, 650, y + 40),
            block(right[0], 835, y, 995, y + 40),
            block(right[1], 1115, y, 1390, y + 40),
        ])
    return blocks


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

    def test_fewshot_does_not_generate_ascii_pattern_for_chinese_values(self):
        learner = object.__new__(FewShotLearner)

        self.assertIsNone(learner._extract_pattern(["纺织品", "电子元器件"]))
        self.assertIsNone(learner._extract_pattern(["华贸进出口有限公司", "中商国际贸易公司"]))
        self.assertEqual(
            learner._extract_pattern(["AB1234", "CD5678"]),
            r"^[A-Z][A-Z]\d\d\d\d$",
        )

    def test_fewshot_recognizes_year_first_dates_as_a_general_date(self):
        learner = object.__new__(FewShotLearner)

        self.assertEqual(
            learner._infer_validator("declare_date", ["2024/11/04", "2024/11/05"]),
            ("date", r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}"),
        )

    def test_date_validator_accepts_year_first_dates(self):
        extractor = FieldExtractor()
        cleaned, valid = validate_and_clean(
            "申报日期",
            "2024/11/04",
            extractor.validators_cfg["date"],
        )

        self.assertTrue(valid)
        self.assertEqual(cleaned, "2024/11/04")

    def test_bol_201_learned_has_distinct_two_column_anchors(self):
        fields = FieldExtractor().config["templates"]["bol_201_learned"]["fields"]

        self.assertEqual(len(fields), 12)
        self.assertEqual(fields["收货单位"]["anchors"], ["收货单位"])
        self.assertEqual(fields["数量及单位"]["canonical_key"], "quantity_unit")
        self.assertEqual(fields["总价"]["canonical_key"], "total_price")
        self.assertEqual(fields["毛重"]["canonical_key"], "gross_weight")
        self.assertEqual(fields["净重"]["canonical_key"], "net_weight")
        self.assertEqual(fields["净重"]["anchors"], ["净重"])

    def test_fewshot_uses_an_unused_source_label_when_anchors_overlap(self):
        learner = object.__new__(FewShotLearner)

        label = learner._display_label_from_anchors(
            ["经营单位", "收货单位"],
            "receiver",
            used_labels={"经营单位"},
        )

        self.assertEqual(label, "收货单位")

    def test_fewshot_learns_all_customs_page_fields_without_cargo_details(self):
        first = {
            "template": "customs_declaration",
            "customs_no": "CUS29603543",
            "declare_date": "2024/11/04",
            "import_port": "宁波海关",
            "transport": "海运",
            "company": "华贸进出口有限公司",
            "receiver": "中商国际贸易公司",
            "goods_name": "纺织品",
            "qty": "67",
            "unit": "件",
            "total_price": "14991",
            "currency": "USD",
            "origin": "韩国",
            "gross_weight": "4292",
            "net_weight": "3853",
            "qty1": "99",
            "unit1": "箱",
        }
        second = {
            **first,
            "customs_no": "CUS78120456",
            "declare_date": "2024/12/05",
            "import_port": "上海海关",
            "transport": "空运",
            "company": "远洋贸易集团",
            "receiver": "华贸进出口有限公司",
            "goods_name": "电子元器件",
            "qty": "25",
            "total_price": "25800",
            "currency": "EUR",
            "origin": "德国",
            "gross_weight": "1520",
            "net_weight": "1380",
        }
        learner = object.__new__(FewShotLearner)
        learner.engine = _FewShotFixtureEngine({
            "first.pdf": {"blocks": customs_sample_blocks(first), "image_size": [400, 400]},
            "second.pdf": {"blocks": customs_sample_blocks(second), "image_size": [400, 400]},
        })

        result = learner.learn([("first.pdf", first), ("second.pdf", second)])

        self.assertEqual(set(result["fields"]), {
            "海关编号", "申报日期", "进口口岸", "运输方式", "经营单位", "收货单位",
            "商品名称", "数量及单位", "总价", "原产国", "毛重", "净重",
        })
        self.assertEqual(result["fields"]["数量及单位"]["canonical_key"], "quantity_unit")
        self.assertEqual(result["fields"]["总价"]["canonical_key"], "total_price")
        self.assertEqual(result["fields"]["毛重"]["canonical_key"], "gross_weight")
        self.assertEqual(result["fields"]["净重"]["canonical_key"], "net_weight")
        self.assertEqual(result["fields"]["经营单位"]["anchors"], ["经营单位"])
        self.assertEqual(result["fields"]["收货单位"]["anchors"], ["收货单位"])
        self.assertNotIn("qty1", {cfg["canonical_key"] for cfg in result["fields"].values()})

    def test_fewshot_uses_sample_layout_without_preset_keywords(self):
        first = {
            "template": "alien_customs",
            "customs_no": "ZXA29603543",
            "declare_date": "2026/07/18",
            "import_port": "月海关",
            "transport": "跃迁",
            "company": "星际物流甲公司",
            "receiver": "星际物流乙公司",
            "goods_name": "曲率线圈",
            "qty": "67",
            "unit": "件",
            "total_price": "14991",
            "currency": "ZCR",
            "origin": "火星",
            "gross_weight": "4292",
            "net_weight": "3853",
        }
        second = {
            **first,
            "customs_no": "ZXA78120456",
            "declare_date": "2026/07/19",
            "company": "星际物流丙公司",
            # Repeated values in different cells must still learn distinct anchors.
            "receiver": "星际物流丙公司",
            "goods_name": "反应堆外壳",
            "qty": "25",
            "total_price": "25800",
            "origin": "木卫二",
            "gross_weight": "1520",
            "net_weight": "1380",
        }
        learner = object.__new__(FewShotLearner)
        learner.engine = _FewShotFixtureEngine({
            "first.pdf": {"blocks": two_column_customs_sample_blocks(first), "image_size": [1656, 2342]},
            "second.pdf": {"blocks": two_column_customs_sample_blocks(second), "image_size": [1656, 2342]},
        })

        learned = learner.learn([("first.pdf", first), ("second.pdf", second)])

        self.assertEqual(learned["keywords"], [])
        self.assertEqual(learned["template_name"], "alien_customs_learned")
        self.assertEqual(learned["fields"]["净重"]["anchors"], ["净重"])
        self.assertEqual(learned["fields"]["收货单位"]["anchors"], ["收货单位"])
        self.assertEqual(learned["detection"]["mode"], "anchor_layout")
        feature_texts = {feature["text"] for feature in learned["detection"]["features"]}
        self.assertIn("净重", feature_texts)
        self.assertIn("完全陌生的星际货物申报确认书", feature_texts)

        extractor = FieldExtractor()
        extractor.config = {
            "validators": extractor.validators_cfg,
            "field_defaults": extractor.config["field_defaults"],
            "templates": {
                "alien_customs_learned": {
                    "keywords": [],
                    "detection": learned["detection"],
                    "fields": learned["fields"],
                    "output": list(learned["fields"]),
                }
            },
        }
        blocks = two_column_customs_sample_blocks(first)
        result = extractor.extract({"header": blocks[:3], "body": blocks[3:], "table": []}, [1656, 2342], blocks=blocks)

        self.assertEqual(result["template"], "alien_customs_learned")
        self.assertEqual(result["fields"]["净重"]["value"], "3853 KG")
        self.assertEqual(result["fields"]["收货单位"]["value"], first["receiver"])

    def test_anchor_layout_signature_rejects_same_text_in_wrong_layout(self):
        extractor = FieldExtractor()
        extractor.config = {
            "validators": {},
            "field_defaults": extractor.config["field_defaults"],
            "templates": {
                "learned": {
                    "keywords": [],
                    "detection": {
                        "mode": "anchor_layout",
                        "min_score": 0.55,
                        "features": [
                            {"text": "陌生字段甲", "x": 0.1, "y": 0.2, "weight": 1.0},
                            {"text": "陌生字段乙", "x": 0.6, "y": 0.7, "weight": 1.0},
                        ],
                    },
                    "fields": {},
                    "output": [],
                }
            },
        }
        wrong_layout = [
            block("陌生字段甲", 900, 900, 1050, 940),
            block("陌生字段乙", 50, 50, 200, 90),
        ]

        result = extractor.extract({"header": wrong_layout, "body": [], "table": []}, [1200, 1200], blocks=wrong_layout)

        self.assertEqual(result["template"], "unknown")

    def test_fewshot_suffix_value_matching_rejects_non_exact_numbers(self):
        learner = object.__new__(FewShotLearner)
        blocks = [
            block("14991 USD", 0, 0, 100, 20),
            block("149910 USD", 0, 30, 100, 50),
            block("4292 KG", 0, 60, 100, 80),
            block("42920 KG", 0, 90, 100, 110),
            block("4292 cartons", 0, 120, 100, 140),
        ]

        self.assertIs(learner._locate_value(blocks, "14991", allow_suffix="currency"), blocks[0])
        self.assertIs(learner._locate_value(blocks, "4292", allow_suffix="weight"), blocks[2])
        self.assertIsNone(learner._locate_value(blocks[1:2], "14991", allow_suffix="currency"))
        self.assertIsNone(learner._locate_value(blocks[3:4], "4292", allow_suffix="weight"))
        self.assertIsNone(learner._locate_value(blocks[4:], "4292", allow_suffix="weight"))

    def test_learned_customs_schema_preserves_existing_field_values(self):
        values = {
            "template": "customs_declaration",
            "customs_no": "CUS29603543",
            "declare_date": "2024/11/04",
            "import_port": "宁波海关",
            "transport": "海运",
            "company": "华贸进出口有限公司",
            "receiver": "中商国际贸易公司",
            "goods_name": "纺织品",
            "qty": "67",
            "unit": "件",
            "total_price": "14991",
            "currency": "USD",
            "origin": "韩国",
            "gross_weight": "4292",
            "net_weight": "3853",
        }
        other = {**values, "customs_no": "CUS78120456", "declare_date": "2024/12/05"}
        learner = object.__new__(FewShotLearner)
        learner.engine = _FewShotFixtureEngine({
            "first.pdf": {"blocks": customs_sample_blocks(values), "image_size": [400, 400]},
            "second.pdf": {"blocks": customs_sample_blocks(other), "image_size": [400, 400]},
        })
        learned = learner.learn([("first.pdf", values), ("second.pdf", other)])

        extractor = FieldExtractor()
        extractor.config = {
            "validators": extractor.validators_cfg,
            "field_defaults": extractor.config["field_defaults"],
            "templates": {
                "customs_learned": {
                    "keywords": ["中华人民共和国海关进口货物报关单"],
                    "fields": learned["fields"],
                    "output": list(learned["fields"]),
                }
            },
        }
        blocks = customs_sample_blocks(values)
        result = extractor.extract({"header": [blocks[0]], "body": blocks[1:], "table": []}, [400, 400], blocks=blocks)

        self.assertEqual(result["meta"]["fields_extracted"], 12)
        expected_existing_values = {
            "海关编号": values["customs_no"],
            "申报日期": values["declare_date"],
            "进口口岸": values["import_port"],
            "运输方式": values["transport"],
            "经营单位": values["company"],
            "收货单位": values["receiver"],
            "商品名称": values["goods_name"],
            "原产国": values["origin"],
        }
        for field_name, expected_value in expected_existing_values.items():
            self.assertEqual(result["fields"][field_name]["value"], expected_value, field_name)
        self.assertEqual(result["fields"]["数量及单位"]["value"], "67 件")
        self.assertEqual(result["fields"]["总价"]["value"], "14991 USD")
        self.assertEqual(result["fields"]["毛重"]["value"], "4292 KG")
        self.assertEqual(result["fields"]["净重"]["value"], "3853 KG")

    def test_fewshot_does_not_create_composites_when_a_pair_is_missing(self):
        learner = object.__new__(FewShotLearner)

        prepared = learner._prepare_sample_fields({
            "qty": "67",
            "total_price": "14991",
            "currency": "USD",
        })

        self.assertNotIn("quantity_unit", prepared)
        self.assertIn("total_price", prepared)

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

    def test_inline_value_requires_an_explicit_ascii_label_separator(self):
        extractor = FieldExtractor()

        self.assertIsNone(
            extractor._extract_inline_value(
                block("Shipper Information", 0, 0, 180, 20),
                "Shipper",
            )
        )
        self.assertEqual(
            extractor._extract_inline_value(
                block("Shipper: Morgan PLC", 0, 0, 180, 20),
                "Shipper",
            ),
            "Morgan PLC",
        )

    def test_short_ascii_anchor_only_matches_a_complete_token(self):
        extractor = FieldExtractor()
        blocks = [
            block("Transport Information", 0, 0, 180, 20),
            block("POD:", 0, 25, 60, 45),
            block("POR:", 0, 30, 60, 50),
        ]

        matches = extractor._find_anchor_blocks(blocks, ["POR"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0]["text"], "POR:")

    def test_ascii_fuzzy_anchor_rejects_a_different_label(self):
        extractor = FieldExtractor()
        blocks = [
            block("Container:", 0, 0, 100, 20),
            block("Consignee:", 0, 30, 100, 50),
        ]

        matches = extractor._find_anchor_blocks(blocks, ["Consignee"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0]["text"], "Consignee:")


if __name__ == "__main__":
    unittest.main()

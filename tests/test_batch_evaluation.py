import os
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "tests"))

import batch_test


class BatchEvaluationTest(unittest.TestCase):
    def test_source_label_field_matches_gt_by_canonical_key(self):
        evaluator = getattr(batch_test, "evaluate_extracted_fields", None)
        self.assertIsNotNone(
            evaluator,
            "batch evaluation must expose canonical-key-aware field comparison",
        )

        fields = {
            "B/L No.": {
                "label": "B/L No.",
                "canonical_key": "bl_no",
                "status": "extracted",
                "cleaned": "BL10398483",
            }
        }
        correct, total, details = evaluator(fields, {"bl_no": "BL10398483"})

        self.assertEqual((correct, total), (1, 1))
        self.assertEqual(details[0][3], "OK")

    def test_legacy_gt_aliases_and_composite_issue_value_are_supported(self):
        fields = {
            "Total Gross Weight": {
                "canonical_key": "total_gross_weight",
                "status": "extracted",
                "cleaned": "41064",
            },
            "Total Measurement": {
                "canonical_key": "total_measurement",
                "status": "extracted",
                "cleaned": "91.47",
            },
            "Place & Date of Issue": {
                "canonical_key": "place_date_of_issue",
                "status": "extracted",
                "cleaned": "NINGBO, 14/11/2025",
            },
        }
        gt = {
            "total_gw": "41064",
            "total_cbm": "91.47",
            "issue_place": "NINGBO",
            "issue_date": "14/11/2025",
        }

        correct, total, details = batch_test.evaluate_extracted_fields(fields, gt)

        self.assertEqual((correct, total), (3, 3))
        self.assertEqual([detail[3] for detail in details], ["OK", "OK", "OK"])

    def test_layout_punctuation_and_spacing_do_not_reduce_accuracy(self):
        fields = {
            "Vessel": {
                "canonical_key": "vessel",
                "status": "extracted",
                "cleaned": "COSCOSTAR",
            },
            "Place & Date of Issue": {
                "canonical_key": "place_date_of_issue",
                "status": "extracted",
                "cleaned": "SHENZHEN,16/02/2024",
            },
        }
        gt = {
            "vessel": "COSCO STAR",
            "issue_place": "SHENZHEN",
            "issue_date": "16/02/2024",
        }

        correct, total, details = batch_test.evaluate_extracted_fields(fields, gt)

        self.assertEqual((correct, total), (2, 2))
        self.assertEqual([detail[3] for detail in details], ["OK", "OK"])

    def test_not_found_mapped_field_counts_as_incorrect(self):
        fields = {
            "B/L No.": {
                "canonical_key": "bl_no",
                "status": "not_found",
                "cleaned": "",
            },
            "Unmapped Debug Field": {
                "canonical_key": "debug_only",
                "status": "extracted",
                "cleaned": "ignored",
            },
        }

        correct, total, details = batch_test.evaluate_extracted_fields(
            fields,
            {"bl_no": "BL10398483"},
        )

        self.assertEqual((correct, total), (0, 1))
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0][3], "MISS")

    def test_html_marks_missing_fields_with_missing_style(self):
        result = {
            "bol": "001",
            "desc": "Maersk",
            "template": "maersk_style",
            "acc": 0.0,
            "correct": 0,
            "total": 1,
            "details": [("B/L No. (bl_no)", "", "BL10398483", "MISS")],
            "table": {},
            "meta": {},
        }
        summary = {
            "total": 1,
            "synth_acc": 0.0,
            "synth_count": 1,
            "funsd_count": 0,
            "real_count": 0,
            "maersk_acc": 0.0,
            "cosco_acc": 0.0,
            "simple_acc": 0.0,
        }

        html = batch_test.build_html([result], summary)

        self.assertIn('<tr class="miss">', html)

    def test_report_path_is_converted_to_a_file_uri(self):
        uri = batch_test._report_file_uri("batch_output/report.html")

        self.assertTrue(uri.startswith("file:///"))
        self.assertTrue(uri.endswith("batch_output/report.html"))

    def test_preview_save_retries_a_transient_windows_error(self):
        class FlakyImage:
            def __init__(self):
                self.calls = 0

            def save(self, path, image_format):
                self.calls += 1
                if self.calls == 1:
                    raise OSError(22, "Invalid argument")

        image = FlakyImage()
        with patch.object(batch_test.time, "sleep"):
            saved = batch_test._save_preview(image, "preview.png")

        self.assertTrue(saved)
        self.assertEqual(image.calls, 2)


if __name__ == "__main__":
    unittest.main()

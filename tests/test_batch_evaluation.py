import os
import tempfile
import sys
import unittest
from pathlib import Path
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

    def test_compact_html_omits_preview_image_links(self):
        result = {
            "bol": "001",
            "desc": "Maersk",
            "template": "maersk_style",
            "acc": 100.0,
            "correct": 1,
            "total": 1,
            "details": [("B/L No. (bl_no)", "BL10398483", "BL10398483", "OK")],
            "table": {},
            "meta": {},
        }
        summary = {
            "total": 1,
            "synth_acc": 100.0,
            "synth_count": 1,
            "funsd_count": 0,
            "real_count": 0,
            "maersk_acc": 100.0,
            "cosco_acc": 0.0,
            "simple_acc": 0.0,
        }

        html = batch_test.build_html([result], summary, include_preview_images=False)

        self.assertNotIn("previews/bol_001.png", html)
        self.assertIn("Preview is included in report.pdf", html)

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

    def test_preview_files_are_temporary_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previews_dir = Path(tmpdir) / "previews"
            previews_dir.mkdir()
            (previews_dir / "bol_001.png").write_bytes(b"fake image")

            batch_test._cleanup_preview_artifacts(str(previews_dir))

            self.assertFalse(previews_dir.exists())

    def test_preview_files_can_be_kept_for_debugging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previews_dir = Path(tmpdir) / "previews"
            previews_dir.mkdir()
            preview = previews_dir / "bol_001.png"
            preview.write_bytes(b"fake image")

            batch_test._cleanup_preview_artifacts(str(previews_dir), keep=True)

            self.assertTrue(preview.exists())

    def test_finalize_report_rewrites_compact_html_after_pdf_success(self):
        result = {
            "bol": "001",
            "desc": "Maersk",
            "template": "maersk_style",
            "acc": 100.0,
            "correct": 1,
            "total": 1,
            "details": [("B/L No. (bl_no)", "BL10398483", "BL10398483", "OK")],
            "table": {},
            "meta": {},
        }
        summary = {
            "total": 1,
            "synth_acc": 100.0,
            "synth_count": 1,
            "funsd_count": 0,
            "real_count": 0,
            "maersk_acc": 100.0,
            "cosco_acc": 0.0,
            "simple_acc": 0.0,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "report.html"
            previews_dir = Path(tmpdir) / "previews"
            previews_dir.mkdir()
            (previews_dir / "bol_001.png").write_bytes(b"fake image")
            html_path.write_text(
                batch_test.build_html([result], summary),
                encoding="utf-8",
            )

            batch_test._finalize_report_artifacts(
                str(html_path),
                [result],
                summary,
                str(previews_dir),
                keep_previews=False,
            )

            html = html_path.read_text(encoding="utf-8")
            self.assertFalse(previews_dir.exists())
            self.assertNotIn("previews/bol_001.png", html)
            self.assertIn("Preview is included in report.pdf", html)


if __name__ == "__main__":
    unittest.main()

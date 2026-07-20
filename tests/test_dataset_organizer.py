import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))

import dataset_organizer


class DatasetOrganizerTest(unittest.TestCase):
    def _write_legacy_pair(self, root, number, payload, area="main"):
        if area == "unknown":
            folder = root / "unknown_templates"
            folder.mkdir(parents=True, exist_ok=True)
            pdf_path = folder / f"bol_{number}.pdf"
            json_path = folder / f"bol_{number}.json"
        else:
            (root / "pdf").mkdir(parents=True, exist_ok=True)
            (root / "json").mkdir(parents=True, exist_ok=True)
            pdf_path = root / "pdf" / f"bol_{number}.pdf"
            json_path = root / "json" / f"bol_{number}.json"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_migration_creates_requested_browsing_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            self._write_legacy_pair(root, "001", {"shipper": "A"})
            self._write_legacy_pair(root, "002", {"shipper": "B"})
            self._write_legacy_pair(root, "003", {"shipper": "C"})
            self._write_legacy_pair(root, "161", {"fields": {"sender": "A"}})
            self._write_legacy_pair(root, "169", {"fields": {"subject": "B"}})
            self._write_legacy_pair(root, "177", {"fields": {"single": "C"}})
            self._write_legacy_pair(root, "181", {"template": "takeout_order", "order_no": "1"})
            self._write_legacy_pair(root, "191", {"template": "courier_label", "tracking_no": "2"})
            self._write_legacy_pair(root, "201", {"template": "customs", "customs_no": "3"}, area="unknown")
            self._write_legacy_pair(root, "206", {"template": "receipt", "receipt_no": "4"}, area="unknown")

            manifest = dataset_organizer.write_dataset_index(root, migrate=True)

            expected_paths = [
                "synthetic_bol/maersk_style/bol_001.pdf",
                "synthetic_bol/cosco_style/bol_002.pdf",
                "synthetic_bol/simple_style/bol_003.pdf",
                "public_funsd/coupon_registration/bol_161.pdf",
                "public_funsd/retail_progress_report/bol_169.pdf",
                "public_funsd/challenge_singletons/bol_177.pdf",
                "real_scans/food_delivery/bol_181.pdf",
                "real_scans/express/bol_191.pdf",
                "fewshot_samples/customs_declaration/bol_201.pdf",
                "fewshot_samples/warehouse_receipt/bol_206.pdf",
            ]
            for rel_path in expected_paths:
                self.assertTrue((root / rel_path).exists(), rel_path)

            self.assertFalse((root / "pdf").exists())
            self.assertFalse((root / "json").exists())
            self.assertFalse((root / "unknown_templates").exists())
            self.assertEqual(manifest["summary"]["total_samples"], 10)

    def test_manifest_uses_new_group_keys_and_resolves_sample_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            self._write_legacy_pair(root, "001", {"shipper": "A"})
            self._write_legacy_pair(root, "004", {"shipper": "B"})

            manifest = dataset_organizer.write_dataset_index(root, migrate=True)
            by_id = {sample["id"]: sample for sample in manifest["samples"]}

            self.assertEqual(by_id["bol_001"]["group"], "synthetic_bol/maersk_style")
            self.assertEqual(by_id["bol_001"]["pdf"], "synthetic_bol/maersk_style/bol_001.pdf")
            self.assertEqual(by_id["bol_001"]["json"], "synthetic_bol/maersk_style/bol_001.json")

            pdf_path, json_path = dataset_organizer.resolve_sample_paths(root, "001")
            self.assertEqual(pdf_path, root / "synthetic_bol" / "maersk_style" / "bol_001.pdf")
            self.assertEqual(json_path, root / "synthetic_bol" / "maersk_style" / "bol_001.json")

    def test_root_readme_matches_requested_top_level_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            self._write_legacy_pair(root, "201", {"template": "customs"}, area="unknown")

            dataset_organizer.write_dataset_index(root, migrate=True)

            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("synthetic_bol/", readme)
            self.assertIn("public_funsd/", readme)
            self.assertIn("real_scans/", readme)
            self.assertIn("fewshot_samples/", readme)
            self.assertIn("bol_201", (root / "fewshot_samples" / "customs_declaration" / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

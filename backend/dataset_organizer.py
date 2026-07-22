"""
Dataset layout organizer for SmartLDS.

The project dataset is a test/demo corpus, so it is useful to browse by layout
family instead of by separate flat `pdf/` and `json/` folders. This module can
migrate the old layout into grouped folders and regenerate a manifest that other
test scripts can use for path lookup.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


GROUP_META: dict[str, dict[str, Any]] = {
    "synthetic_bol/maersk_style": {
        "title": "Synthetic BOL - Maersk style",
        "source": "synthetic_bol",
        "layout_consistency": "same_layout",
        "fewshot_use": "Stable generated layout; suitable for rule regression and Few-shot experiments.",
    },
    "synthetic_bol/cosco_style": {
        "title": "Synthetic BOL - COSCO style",
        "source": "synthetic_bol",
        "layout_consistency": "same_layout",
        "fewshot_use": "Stable generated layout; suitable for rule regression and Few-shot experiments.",
    },
    "synthetic_bol/simple_style": {
        "title": "Synthetic BOL - Simple style",
        "source": "synthetic_bol",
        "layout_consistency": "same_layout",
        "fewshot_use": "Stable generated layout; suitable for rule regression and Few-shot experiments.",
    },
    "public_funsd/coupon_registration": {
        "title": "Public FUNSD - Coupon registration",
        "source": "public_funsd",
        "layout_consistency": "curated_same_family",
        "fewshot_use": "Can be used as a public-form Few-shot family after visual review.",
    },
    "public_funsd/retail_progress_report": {
        "title": "Public FUNSD - Retail progress report",
        "source": "public_funsd",
        "layout_consistency": "curated_same_family",
        "fewshot_use": "Can be used as a public-form Few-shot family after visual review.",
    },
    "public_funsd/challenge_singletons": {
        "title": "Public FUNSD - Challenge singletons",
        "source": "public_funsd",
        "layout_consistency": "singletons_or_mixed",
        "fewshot_use": "Browse and test fallback behavior; not recommended for Few-shot grouping.",
    },
    "real_scans/food_delivery": {
        "title": "Real scans - Food delivery receipts",
        "source": "real_scans",
        "layout_consistency": "same_family",
        "fewshot_use": "Useful for OCR/preprocessing validation, not a logistics BOL schema.",
    },
    "real_scans/express": {
        "title": "Real scans - Express labels",
        "source": "real_scans",
        "layout_consistency": "same_family",
        "fewshot_use": "Useful for OCR/preprocessing validation, not a logistics BOL schema.",
    },
    "fewshot_samples/customs_declaration": {
        "title": "Few-shot samples - Customs declaration",
        "source": "fewshot_samples",
        "layout_consistency": "same_layout",
        "fewshot_use": "Recommended demo family for Few-shot learning and feedback.",
    },
    "fewshot_samples/warehouse_receipt": {
        "title": "Few-shot samples - Warehouse receipt",
        "source": "fewshot_samples",
        "layout_consistency": "same_layout",
        "fewshot_use": "Recommended second unknown-template family for Few-shot learning.",
    },
}

REQUESTED_TOP_LEVELS = ("synthetic_bol", "public_funsd", "real_scans", "fewshot_samples")
LEGACY_DIRS = ("pdf", "json", "unknown_templates", "groups")
REAL_SCAN_SEQUENCES = {
    "real_scans/food_delivery": 181,
    "real_scans/express": 188,
}


def group_for_number(number: int) -> str:
    if 1 <= number <= 160:
        remainder = number % 3
        if remainder == 1:
            return "synthetic_bol/maersk_style"
        if remainder == 2:
            return "synthetic_bol/cosco_style"
        return "synthetic_bol/simple_style"
    if 161 <= number <= 168:
        return "public_funsd/coupon_registration"
    if 169 <= number <= 176:
        return "public_funsd/retail_progress_report"
    if 177 <= number <= 180:
        return "public_funsd/challenge_singletons"
    if 181 <= number <= 187:
        return "real_scans/food_delivery"
    if 188 <= number <= 200:
        return "real_scans/express"
    if 201 <= number <= 205:
        return "fewshot_samples/customs_declaration"
    if 206 <= number <= 210:
        return "fewshot_samples/warehouse_receipt"
    return "unclassified"


def _sample_number(stem_or_id: str) -> int:
    text = stem_or_id.replace(".pdf", "").replace(".json", "")
    if text.startswith("bol_"):
        text = text.split("_", 1)[1]
    try:
        return int(text)
    except ValueError:
        return 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _field_keys(payload: dict[str, Any]) -> list[str]:
    fields = payload.get("fields")
    if isinstance(fields, dict):
        return list(fields.keys())
    return list(payload.keys())


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _destination_paths(root: Path, number: int) -> tuple[Path, Path]:
    group = group_for_number(number)
    stem = f"bol_{number:03d}"
    folder = root / group
    return folder / f"{stem}.pdf", folder / f"{stem}.json"


def _iter_real_scan_pairs(root: Path) -> list[tuple[int, Path, Path]]:
    pairs: list[tuple[int, Path, Path]] = []
    for group_key, start in REAL_SCAN_SEQUENCES.items():
        folder = root / group_key
        if not folder.exists():
            continue
        json_files = [
            path for path in sorted(folder.glob("*.json"))
            if path.name not in {"samples.json", "manifest.json"} and path.with_suffix(".pdf").exists()
        ]
        unnamed_index = 0
        for json_path in json_files:
            if json_path.stem.startswith("bol_"):
                number = _sample_number(json_path.stem)
            else:
                number = start + unnamed_index
                unnamed_index += 1
            if number:
                pairs.append((number, json_path.with_suffix(".pdf"), json_path))
    return pairs


def _iter_sample_pairs(root: Path) -> list[tuple[int, Path, Path]]:
    pairs: dict[int, tuple[Path, Path]] = {}

    for json_path in sorted((root / "json").glob("bol_*.json")):
        number = _sample_number(json_path.stem)
        pdf_path = root / "pdf" / f"{json_path.stem}.pdf"
        if number and pdf_path.exists():
            pairs[number] = (pdf_path, json_path)

    for json_path in sorted((root / "unknown_templates").glob("bol_*.json")):
        number = _sample_number(json_path.stem)
        pdf_path = json_path.with_suffix(".pdf")
        if number and pdf_path.exists():
            pairs[number] = (pdf_path, json_path)

    for top in REQUESTED_TOP_LEVELS:
        if top == "real_scans":
            for number, pdf_path, json_path in _iter_real_scan_pairs(root):
                pairs[number] = (pdf_path, json_path)
            continue
        for json_path in sorted((root / top).glob("**/bol_*.json")):
            number = _sample_number(json_path.stem)
            pdf_path = json_path.with_suffix(".pdf")
            if number and pdf_path.exists():
                pairs[number] = (pdf_path, json_path)

    return [(number, *paths) for number, paths in sorted(pairs.items())]


def _ensure_under_root(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"Refusing path outside dataset root: {resolved_path}")
    return resolved_path


def migrate_to_requested_layout(root: str | Path = "dataset") -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _ensure_under_root(root, root)

    for number, pdf_path, json_path in _iter_sample_pairs(root):
        dest_pdf, dest_json = _destination_paths(root, number)
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        for src, dest in ((pdf_path, dest_pdf), (json_path, dest_json)):
            _ensure_under_root(src, root)
            _ensure_under_root(dest, root)
            if src.resolve() == dest.resolve():
                continue
            if dest.exists():
                src.unlink()
            else:
                shutil.move(str(src), str(dest))

    old_groups = root / "groups"
    if old_groups.exists() and old_groups.is_dir():
        _ensure_under_root(old_groups, root)
        shutil.rmtree(old_groups)

    for dirname in ("pdf", "json", "unknown_templates"):
        folder = root / dirname
        if folder.exists() and folder.is_dir():
            _ensure_under_root(folder, root)
            if not any(folder.iterdir()):
                folder.rmdir()


def build_manifest(root: str | Path = "dataset") -> dict[str, Any]:
    root = Path(root)
    samples: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}

    for number, pdf_path, json_path in _iter_sample_pairs(root):
        payload = _load_json(json_path)
        keys = _field_keys(payload)
        group_key = group_for_number(number)
        sample = {
            "id": f"bol_{number:03d}",
            "number": number,
            "group": group_key,
            "pdf": _rel(pdf_path, root),
            "json": _rel(json_path, root),
            "field_count": len(keys),
            "field_keys": keys,
        }
        samples.append(sample)

        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "directory": group_key,
                **GROUP_META.get(
                    group_key,
                    {
                        "title": group_key.replace("_", " ").replace("/", " / ").title(),
                        "source": "unclassified",
                        "layout_consistency": "unverified",
                        "fewshot_use": "Review manually before using as Few-shot samples.",
                    },
                ),
                "sample_count": 0,
                "samples": [],
                "recommended_fewshot": [],
            },
        )
        group["sample_count"] += 1
        group["samples"].append(sample["id"])

    for group in groups.values():
        if group["layout_consistency"] in {"same_layout", "curated_same_family", "same_family"}:
            group["recommended_fewshot"] = group["samples"][: min(5, len(group["samples"]))]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_samples": len(samples),
            "group_count": len(groups),
            "source_paths": [f"{top}/" for top in REQUESTED_TOP_LEVELS],
        },
        "groups": [groups[key] for key in sorted(groups)],
        "samples": samples,
    }


def resolve_sample_paths(root: str | Path, bol: str | int) -> tuple[Path, Path]:
    root = Path(root)
    number = _sample_number(str(bol))
    if not number:
        raise FileNotFoundError(f"Invalid sample id: {bol}")

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = _load_json(manifest_path)
        for sample in manifest.get("samples", []):
            if sample.get("number") == number or sample.get("id") == f"bol_{number:03d}":
                pdf_path = root / str(sample["pdf"])
                json_path = root / str(sample["json"])
                if pdf_path.exists() and json_path.exists():
                    return pdf_path, json_path

    pdf_path, json_path = _destination_paths(root, number)
    if pdf_path.exists() and json_path.exists():
        return pdf_path, json_path

    legacy_pdf = root / "pdf" / f"bol_{number:03d}.pdf"
    legacy_json = root / "json" / f"bol_{number:03d}.json"
    if legacy_pdf.exists() and legacy_json.exists():
        return legacy_pdf, legacy_json

    legacy_unknown_pdf = root / "unknown_templates" / f"bol_{number:03d}.pdf"
    legacy_unknown_json = root / "unknown_templates" / f"bol_{number:03d}.json"
    if legacy_unknown_pdf.exists() and legacy_unknown_json.exists():
        return legacy_unknown_pdf, legacy_unknown_json

    raise FileNotFoundError(f"Sample bol_{number:03d} not found under {root}")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sample_link(sample: dict[str, Any]) -> str:
    name = sample["id"]
    return f"- [{name}]({Path(sample['pdf']).name}) + [JSON]({Path(sample['json']).name})"


def _group_readme(group: dict[str, Any], group_samples: list[dict[str, Any]]) -> str:
    lines = [
        f"# {group['title']}",
        "",
        f"- Directory: `{group['directory']}`",
        f"- Samples: {group['sample_count']}",
        f"- Layout consistency: `{group['layout_consistency']}`",
        f"- Few-shot use: {group['fewshot_use']}",
        "",
        "## Recommended Few-shot Samples",
        "",
    ]
    recommended = set(group.get("recommended_fewshot") or [])
    if recommended:
        for sample in group_samples:
            if sample["id"] in recommended:
                lines.append(_sample_link(sample))
    else:
        lines.append("- No automatic recommendation. Review samples manually.")

    lines.extend(["", "## All Samples", ""])
    for sample in group_samples:
        lines.append(_sample_link(sample))
    lines.append("")
    return "\n".join(lines)


def _root_readme(manifest: dict[str, Any]) -> str:
    lines = [
        "# SmartLDS Dataset",
        "",
        "This dataset is organized by layout family so samples can be browsed and selected for Few-shot learning.",
        "",
        "```text",
        "dataset/",
        "|-- synthetic_bol/",
        "|   |-- maersk_style/",
        "|   |-- cosco_style/",
        "|   `-- simple_style/",
        "|-- public_funsd/",
        "|   |-- coupon_registration/",
        "|   |-- retail_progress_report/",
        "|   `-- challenge_singletons/",
        "|-- real_scans/",
        "|   |-- food_delivery/",
        "|   `-- express/",
        "|-- fewshot_samples/",
        "|   |-- customs_declaration/",
        "|   `-- warehouse_receipt/",
        "|-- manifest.json",
        "`-- README.md",
        "```",
        "",
        "## Groups",
        "",
        "| Directory | Samples | Layout | Recommended Few-shot |",
        "| --- | ---: | --- | --- |",
    ]
    for group in manifest["groups"]:
        rec = ", ".join(group.get("recommended_fewshot") or []) or "manual review"
        lines.append(f"| `{group['directory']}` | {group['sample_count']} | `{group['layout_consistency']}` | {rec} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Each sample keeps its PDF and JSON side by side.",
            "- `public_funsd/challenge_singletons` is intentionally excluded from automatic Few-shot recommendations.",
            "- Re-run `.venv\\Scripts\\python.exe backend\\dataset_organizer.py` after adding or removing dataset samples.",
            "",
        ]
    )
    return "\n".join(lines)


def write_dataset_index(root: str | Path = "dataset", migrate: bool = False) -> dict[str, Any]:
    root = Path(root)
    if migrate:
        migrate_to_requested_layout(root)

    manifest = build_manifest(root)
    _write_json(root / "manifest.json", manifest)
    (root / "README.md").write_text(_root_readme(manifest), encoding="utf-8")

    samples_by_group: dict[str, list[dict[str, Any]]] = {}
    for sample in manifest["samples"]:
        samples_by_group.setdefault(sample["group"], []).append(sample)

    for group in manifest["groups"]:
        group_dir = root / group["directory"]
        group_samples = samples_by_group.get(group["key"], [])
        _write_json(group_dir / "samples.json", group_samples)
        (group_dir / "README.md").write_text(_group_readme(group, group_samples), encoding="utf-8")
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "dataset"
    manifest = write_dataset_index(root, migrate=True)
    print(
        f"Wrote dataset layout: {manifest['summary']['total_samples']} samples, "
        f"{manifest['summary']['group_count']} groups"
    )


if __name__ == "__main__":
    main()

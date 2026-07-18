# SmartLDS Dataset Organization Design

## Goal

Reorganize the 210 SmartLDS document pairs so a user can browse by document family and safely select Few-shot samples without mixing incompatible layouts. Keep every `bol_xxx` identifier stable, keep each PDF beside its JSON annotation, and provide one machine-readable catalog plus one human-readable guide.

## Non-goals

- Do not renumber `bol_001` through `bol_210`.
- Do not change the content of synthetic, real-scan, customs-declaration, or warehouse-receipt annotations.
- Do not present structurally different FUNSD forms as one Few-shot family.
- Do not add filesystem links or retain duplicate compatibility copies of the dataset.
- Do not change recognition algorithms as part of this migration.

## Target Directory Layout

```text
dataset/
|-- synthetic_bol/
|   |-- maersk_style/
|   |-- cosco_style/
|   `-- simple_style/
|-- public_funsd/
|   |-- coupon_registration/
|   |-- retail_progress_report/
|   `-- challenge_singletons/
|-- real_scans/
|   |-- food_delivery/
|   `-- express/
|-- fewshot_samples/
|   |-- customs_declaration/
|   `-- warehouse_receipt/
|-- manifest.json
`-- README.md
```

Every sample directory stores paired files directly:

```text
bol_161.pdf
bol_161.json
```

## Dataset Families And Counts

| Family | IDs | Count | Few-shot eligibility |
|---|---:|---:|---|
| `synthetic_bol/maersk_style` | Existing Maersk IDs in `001-160` | 54 | Yes |
| `synthetic_bol/cosco_style` | Existing COSCO IDs in `001-160` | 53 | Yes |
| `synthetic_bol/simple_style` | Existing Simple IDs in `001-160` | 53 | Yes |
| `public_funsd/coupon_registration` | `161-168` | 8 | Yes |
| `public_funsd/retail_progress_report` | `169-176` | 8 | Yes |
| `public_funsd/challenge_singletons` | `177-180` | 4 | No |
| `real_scans/food_delivery` | Existing food-delivery IDs in `181-200` | 7 | No by default |
| `real_scans/express` | Existing express IDs in `181-200` | 13 | No by default |
| `fewshot_samples/customs_declaration` | `201-205` | 5 | Yes |
| `fewshot_samples/warehouse_receipt` | `206-210` | 5 | Yes |

The total remains 210 PDF/JSON pairs.

## Deterministic FUNSD Selection

The current random FUNSD selection is replaced with an explicit source-to-ID map. Each source image and annotation has been verified to exist exactly once in `public_data/dataset`.

### Coupon Registration: `bol_161-168`

| Destination | FUNSD source |
|---|---|
| `bol_161` | `83996357` |
| `bol_162` | `86075409_5410` |
| `bol_163` | `87533049` |
| `bol_164` | `91391286` |
| `bol_165` | `91391310` |
| `bol_166` | `91974562` |
| `bol_167` | `93351929_93351931` |
| `bol_168` | `93380187` |

### Retail Progress Report: `bol_169-176`

| Destination | FUNSD source |
|---|---|
| `bol_169` | `81619486_9488` |
| `bol_170` | `81619511_9513` |
| `bol_171` | `82200067_0069` |
| `bol_172` | `82252956_2958` |
| `bol_173` | `82253245_3247` |
| `bol_174` | `82253362_3364` |
| `bol_175` | `83641919_1921` |
| `bol_176` | `86230203_0206` |

### Challenge Singletons: `bol_177-180`

| Destination | FUNSD source |
|---|---|
| `bol_177` | `87528380` |
| `bol_178` | `89856243` |
| `bol_179` | `91814768_91814769` |
| `bol_180` | `93106788` |

The conversion output records `template_family` and `fewshot_eligible`. The two stable families use distinct template-family names. Challenge samples use `funsd_singleton` and `fewshot_eligible: false`.

## Manifest Contract

`dataset/manifest.json` contains one entry per `bol_xxx` identifier:

```json
{
  "id": "bol_161",
  "pdf": "public_funsd/coupon_registration/bol_161.pdf",
  "json": "public_funsd/coupon_registration/bol_161.json",
  "source": "FUNSD",
  "source_id": "83996357",
  "template_family": "coupon_registration",
  "category": "public_form",
  "fewshot_eligible": true
}
```

Required rules:

- Entries are sorted numerically by ID.
- Paths are relative to `dataset/` and use forward slashes.
- Every entry references exactly one existing PDF and one existing JSON file.
- IDs and file basenames match.
- The manifest is generated from the organized directories, not maintained as a separate hand-edited truth source.

## Human Documentation

`dataset/README.md` explains:

- the purpose and count of each family;
- which folders are safe for Few-shot learning;
- why FUNSD challenge singletons must not be mixed into one learning run;
- the `bol_xxx` ranges and original data sources;
- how to rebuild and validate the manifest.

## Migration Strategy

1. Create the target family directories.
2. Move existing `001-160`, `181-210` pairs according to annotation metadata while preserving basenames.
3. Regenerate `161-180` from the fixed FUNSD source map directly into the new directories.
4. Update data generators and converters so future runs use the new paths and deterministic FUNSD map.
5. Update manual OCR scripts and documentation that reference `dataset/pdf`, `dataset/json`, or `dataset/unknown_templates`.
6. Generate `dataset/manifest.json` and `dataset/README.md`.
7. Remove the now-empty legacy directories only after validation succeeds.

The migration must fail before deleting legacy directories if any destination already contains an unexpected file, a source pair is missing, a JSON file is invalid, or a destination ID would collide.

## Code And Tooling Changes

- Add a small dataset catalog utility that locates samples through `manifest.json` and validates pair integrity.
- Refactor `public_data/convert_funsd.py` to use the fixed groups above instead of `random.sample()`.
- Update `backend/generate_data.py` to write synthetic samples into the three template-family directories.
- Update `real_data/convert_real.py` to write by real-scan category.
- Update manual evaluation scripts to resolve IDs through the manifest rather than hard-coded `dataset/pdf` and `dataset/json` paths.
- Update `.agents/AGENTS.md`, `final_report.md`, and dataset-facing comments with the new paths and group meanings.

No recognition API needs a compatibility layer because runtime uploads do not read from the project dataset. Internal scripts must use the manifest after migration.

## Validation

The completed migration must verify:

- 210 manifest entries;
- 210 PDFs and 210 JSON files under `dataset/`;
- no missing or duplicate IDs;
- every PDF/JSON basename matches its manifest ID;
- every JSON file parses successfully;
- family counts are `54/53/53/8/8/4/7/13/5/5`;
- `bol_161-168` all use `coupon_registration` and are Few-shot eligible;
- `bol_169-176` all use `retail_progress_report` and are Few-shot eligible;
- `bol_177-180` are marked ineligible;
- old `dataset/pdf`, `dataset/json`, and `dataset/unknown_templates` references are removed from active scripts;
- fast Python tests still pass;
- a real Few-shot replay can select samples from each eligible stable family without crossing directory boundaries.

## Rollback And Data Safety

- Existing `public_data`, `real_data`, and generated source files remain untouched.
- The migration preserves IDs and uses source-controlled file moves where possible.
- Validation occurs before deleting empty legacy directories.
- Unrelated modified files are not reverted or included in the design-document commit.

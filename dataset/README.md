# SmartLDS Dataset

This dataset is organized by layout family so samples can be browsed and selected for Few-shot learning.

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

## Groups

| Directory | Samples | Layout | Recommended Few-shot |
| --- | ---: | --- | --- |
| `fewshot_samples/customs_declaration` | 5 | `same_layout` | bol_201, bol_202, bol_203, bol_204, bol_205 |
| `fewshot_samples/warehouse_receipt` | 5 | `same_layout` | bol_206, bol_207, bol_208, bol_209, bol_210 |
| `public_funsd/challenge_singletons` | 4 | `singletons_or_mixed` | manual review |
| `public_funsd/coupon_registration` | 8 | `curated_same_family` | bol_161, bol_162, bol_163, bol_164, bol_165 |
| `public_funsd/retail_progress_report` | 8 | `curated_same_family` | bol_169, bol_170, bol_171, bol_172, bol_173 |
| `real_scans/express` | 10 | `same_family` | bol_191, bol_192, bol_193, bol_194, bol_195 |
| `real_scans/food_delivery` | 10 | `same_family` | bol_181, bol_182, bol_183, bol_184, bol_185 |
| `synthetic_bol/cosco_style` | 53 | `same_layout` | bol_002, bol_005, bol_008, bol_011, bol_014 |
| `synthetic_bol/maersk_style` | 54 | `same_layout` | bol_001, bol_004, bol_007, bol_010, bol_013 |
| `synthetic_bol/simple_style` | 53 | `same_layout` | bol_003, bol_006, bol_009, bol_012, bol_015 |

## Notes

- Each sample keeps its PDF and JSON side by side.
- `public_funsd/challenge_singletons` is intentionally excluded from automatic Few-shot recommendations.
- Re-run `.venv\Scripts\python.exe backend\dataset_organizer.py` after adding or removing dataset samples.

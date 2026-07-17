# AGENTS.md

This file gives coding agents the project context and operating rules for SmartLDS.

## Project

SmartLDS is a course-design system for logistics document recognition. It uses:

- Python backend: Flask + PaddleOCR + OpenCV/Pillow/PyMuPDF
- Frontend: Vue 3 + Vite + Element Plus
- Core flow: upload PDF/image → OCR → layout parsing → key information extraction → JSON/Excel export

Primary source files:

- `backend/app.py`: Flask API, job persistence, upload, recognition, correction, export, history
- `backend/ocr_engine.py`: PaddleOCR wrapper
- `backend/preprocess.py`: grayscale, orientation, deskew, CLAHE
- `backend/layout_parser.py`: row grouping and table region detection
- `backend/field_extractor.py`: anchor-based field extraction and table recovery
- `backend/vision_fallback.py`: low-confidence scoring and optional vision-model fallback
- `backend/config.yaml`: self-contained template definitions
- `tests/`: all test and evaluation scripts
- `frontend/src/App.vue`: main UI
- `frontend/src/api/index.js`: frontend API wrapper

## Current State

The first two hardening phases have been completed:

- Safe ZIP upload with path traversal protection, member count limits, uncompressed size limits, and allowed extension filtering.
- `job_id` validation and upload-root path containment.
- Disk restoration from `result.json`, `blocks.json`, `corrections.json`, and `original.*`.
- Unified single-file and batch recognition via `run_recognition_pipeline()`.
- Corrections are merged into field results and exported JSON/XLSX.
- Frontend displays corrected values after reload.
- Multi-page PDFs still process page 1 only, but metadata now records `page_count`, `processed_page`, and warnings.
- Frontend API base defaults to `/api` and can be overridden with `VITE_API_BASE_URL`.
- Field schemas are now template-local: each template should output its own source document labels, while `canonical_key` is only metadata.
- Low-confidence recognition can optionally route to `backend/vision_fallback.py`; this keeps local rules as the default path and uses a vision model only as a fallback.
- Test files have been consolidated under `tests/`. Fast unit tests are named `test_*.py`; heavy/manual OCR checks are not.
- Result page JSON preview has intentionally been rolled back to the simple first-version UI: a plain `JSON` collapse that shows the full JSON text only.
- Manual correction, manual fields, manual table editing, export options, and feedback-to-template are supported. Keep these workflows compatible when changing result data shape.
- Few-shot feedback can learn OCR value offsets from corrected/manual fields when the value and nearby anchor can be found in OCR blocks. This is what lets a corrected template recognize previously missing values on the next run.

Known remaining limits:

- FUNSD is not a normal logistics-template problem. Low-confidence FUNSD can use vision fallback, but a dedicated question-answer linking mode is still the cleaner long-term route.
- Handwriting is outside the strength of the current PaddleOCR print-oriented pipeline.
- Frontend build passes but has a large chunk warning.
- The repo may contain many generated or untracked files. Treat them as user-owned.

## 当前补充约定

- 识别输出优先使用“原单据字段名”。不同版式可以拥有完全独立的字段 schema；`canonical_key` 只做内部语义参考，不应该替代前端展示字段名。
- 默认识别路线是本地 PaddleOCR + 规则抽取；只有低置信度、unknown、FUNSD/real_scan 覆盖率低等情况才考虑视觉大模型兜底。
- 视觉兜底必须是可选能力：未配置 API key、未启用、超时或模型 JSON 不合法时，都应该返回本地结果并写入 `meta.warnings`。
- 视觉兜底设置通过前端“模型设置”管理，后端接口是 `/api/vision-settings`。默认供应商是千问，API Key 保存在本地 `uploads/vision_settings.json`，不要写入源码或 `config.yaml`。
- 测试脚本统一放在 `tests/`。快速单元测试命名为 `test_*.py`；会加载 OCR 模型或跑大量样本的人工/批量脚本不要用 `test_` 前缀。
- 结果页下方 JSON 展示区保持“第一版”样式：只保留一个标题为 `JSON` 的折叠块，展开后显示完整 JSON。不要再默认显示“字段键值 / 完整 JSON”双标签预览，避免和上方字段卡片重复。
- 字段卡片是主要人工校正入口：字段值可双击修改，字段名也可双击修改。人工校正后的内容应同步到 JSON 预览、保存校正、导出 JSON/Excel 和反哺版式流程。
- 表格展示仍在字段卡片和 JSON 折叠块之间；有表格时显示“货物明细”，无表格时不占位。表格人工编辑采用最终表格替换模式，并通过 `table_patch` 保存。
- 反哺版式支持选择已有版式或创建新版式；如果字段值能在 OCR blocks 中找到，会尝试学习锚点和值之间的位置偏移。不要把反哺只理解成保存字段名，它也可能更新 anchors、validators、`learned_value_offset` 和表头结构。
- 表格抽取当前仍偏向物流货物明细表。`has_table` 或表格表头参考不等于任意网格都会被自动结构化；普通中文网格/FUNSD 表单仍更适合后续 generic form 或视觉兜底路线。

## Commands

Run backend compile checks:

```powershell
.venv\Scripts\python.exe -m compileall -q backend tests run.py
```

Run unit tests:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -p "test*.py"
```

Run heavier/manual OCR evaluation only when needed:

```powershell
.venv\Scripts\python.exe tests\manual_ocr_pipeline.py
.venv\Scripts\python.exe tests\batch_test.py
```

Run frontend build:

```powershell
cd frontend
npm.cmd run build
```

Run backend:

```powershell
cd backend
python app.py
```

Run frontend dev server:

```powershell
cd frontend
npm.cmd run dev
```

Run the combined launcher:

```powershell
python run.py
```

Optional vision fallback environment:

```powershell
$env:VISION_FALLBACK_ENABLED="true"
$env:DASHSCOPE_API_KEY="..."
$env:VISION_FALLBACK_THRESHOLD="0.55"
$env:VISION_FALLBACK_MODEL="qwen3.6-plus"
```

## Engineering Rules

- Search with `rg` or `rg --files`.
- Use `apply_patch` for manual source edits.
- Do not revert unrelated dirty worktree changes.
- Do not edit generated datasets unless the user explicitly asks.
- Do not reintroduce `zipfile.extractall()` for user-provided ZIP files.
- Do not build task paths by string concatenation outside `job_dir()`.
- Do not duplicate recognition logic between single and batch endpoints. Change `run_recognition_pipeline()` first.
- Keep automated tests in `tests/test_*.py`; put heavy/manual OCR scripts in `tests/` without the `test_` prefix.
- If changing correction behavior, verify result reload and JSON/XLSX export.
- If changing result-page JSON preview, keep the simple `JSON` collapse unless the user explicitly asks to restore the richer preview table.
- If changing manual field/table correction, verify `node tests\frontend_result_state_check.mjs` in addition to backend unit tests.
- If changing frontend API calls, keep relative `/api` support.
- If changing vision fallback behavior, preserve the failure policy: no API key, disabled fallback, timeout, or invalid JSON must return local rules output plus `meta.warnings`, not a failed recognition job.
- If changing template fields, preserve source-label output and keep `canonical_key` as metadata only.
- When adding a form family, decide whether it belongs to:
  - logistics anchor extraction,
  - Few-shot YAML generation,
  - vision fallback for low-confidence generic forms,
  - or a separate mode such as FUNSD question-answer extraction.

## Verification Expectations

For backend-only safety/data changes:

- Run Python compile check.
- Run fast unit tests when field extraction, config, or fallback logic changes.
- Exercise a small Flask test client if possible for `job_id`, ZIP, result, correction, or export behavior.

For frontend changes:

- Run `node tests\frontend_result_state_check.mjs` when result-page state, JSON preview, field editing, or table editing changes.
- Run `npm.cmd run build`.
- If build fails with `spawn EPERM` under sandbox, rerun with approval/escalation.

For OCR algorithm changes:

- Avoid claiming quality improvements without a sample-level check.
- Keep synthetic logistics accuracy separate from FUNSD and handwriting observations.
- Use `tests/batch_test.py` for heavier report-style checks; do not include it in default unit-test discovery.

## Reporting

When handing work back to the user, mention:

- files changed,
- verification commands and results,
- any known remaining limitations,
- whether generated outputs or build artifacts were touched.

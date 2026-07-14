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
- `backend/config.yaml`: self-contained template definitions
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

Known remaining limits:

- FUNSD is not a normal logistics-template problem. It should eventually get a dedicated question-answer linking mode.
- Handwriting is outside the strength of the current PaddleOCR print-oriented pipeline.
- Frontend build passes but has a large chunk warning.
- The repo may contain many generated or untracked files. Treat them as user-owned.

## Commands

Run backend compile checks:

```powershell
.venv\Scripts\python.exe -m compileall -q backend run.py test.py
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

## Engineering Rules

- Search with `rg` or `rg --files`.
- Use `apply_patch` for manual source edits.
- Do not revert unrelated dirty worktree changes.
- Do not edit generated datasets unless the user explicitly asks.
- Do not reintroduce `zipfile.extractall()` for user-provided ZIP files.
- Do not build task paths by string concatenation outside `job_dir()`.
- Do not duplicate recognition logic between single and batch endpoints. Change `run_recognition_pipeline()` first.
- If changing correction behavior, verify result reload and JSON/XLSX export.
- If changing frontend API calls, keep relative `/api` support.
- When adding a form family, decide whether it belongs to:
  - logistics anchor extraction,
  - Few-shot YAML generation,
  - or a separate mode such as FUNSD question-answer extraction.

## Verification Expectations

For backend-only safety/data changes:

- Run Python compile check.
- Exercise a small Flask test client if possible for `job_id`, ZIP, result, correction, or export behavior.

For frontend changes:

- Run `npm.cmd run build`.
- If build fails with `spawn EPERM` under sandbox, rerun with approval/escalation.

For OCR algorithm changes:

- Avoid claiming quality improvements without a sample-level check.
- Keep synthetic logistics accuracy separate from FUNSD and handwriting observations.

## Reporting

When handing work back to the user, mention:

- files changed,
- verification commands and results,
- any known remaining limitations,
- whether generated outputs or build artifacts were touched.

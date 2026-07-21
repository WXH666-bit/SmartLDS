# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

物流单证智能识别系统 — 基于 OCR 与版面分析，从 PDF/图片中提取物流单证的关键字段（Shipper、B/L No.、Gross Weight 等），输出结构化 JSON。Python + PaddleOCR + Flask 后端 + Vue3 前端，课程设计项目。

## Current Engineering Status

As of 2026-07-21:

- ZIP upload validates member paths, limits member count (300), limits total uncompressed size (256 MB), and only writes allowed document/image files.
- Route-level `job_id` validation (12-char hex) is enforced via `@app.before_request`.
- Jobs can be restored from disk after restart using `result.json`, `blocks.json`, `corrections.json`, and `original.*`.
- Single-file and batch recognition share `run_recognition_pipeline()`, so both persist `result.json` and `blocks.json`.
- Corrections are merged back into field results and exported JSON/XLSX. Supports **manual fields** (add arbitrary fields with OCR anchor/offset), **field exclusion**, **field label overrides**, and **table patches** (replace mode).
- Multi-page PDFs are still processed page 1 only, but `meta.page_count`, `meta.processed_page`, and warnings make this limitation explicit.
- Frontend API base defaults to relative `/api` and supports `VITE_API_BASE_URL`.
- Vision fallback supports 4 providers: Qwen (阿里云百炼), OpenAI, custom OpenAI-compatible, and Ollama local models. Settings persist per-provider with individual model API keys.
- `funsd_public` and `real_scan` templates are disabled/hidden by default (`enabled: false, hidden: true`) — they exist for cross-domain validation, not as active extraction targets.
- Few-shot learned templates use **anchor-layout signatures** for detection (geometry-based matching of stable text positions across samples) rather than vocabulary keywords.
- AI template enhancement: optional vision-model pass during few-shot learning and result feedback to improve anchor selection, field configuration, and table headers.
- OCR feedback learning: when users correct fields, the correction's anchor→value offset is learned and persisted into the template for future extraction.

Latest verification:

```bash
.venv\Scripts\python.exe -m compileall -q backend run.py test.py
cd frontend && npm.cmd run build
```

Frontend production build passes but still reports a large chunk warning (~1 MB JS). This is a performance follow-up, not a correctness failure.

## Common Commands

```bash
# 激活虚拟环境
source .venv/Scripts/activate

# 运行 OCR 测试
cd tests && python batch_test.py

# 批量测试 + 生成报告 PDF
cd tests && python batch_test.py

# 生成合成数据（160份，bol_001~160）
cd backend && python generate_data.py

# 生成未知版式测试数据（报关单 + 入库单，bol_201~210）
cd backend && python gen_new_templates.py

# 运行 Flask 后端
cd backend && python app.py

# 运行 Vue3 前端（开发模式，默认 8080 端口）
cd frontend && npm run dev

# 一键启动（后端 + 前端）
python run.py

# 后端语法/导入编译检查
.venv\Scripts\python.exe -m compileall -q backend run.py

# 前端生产构建
cd frontend && npm.cmd run build

# Few-shot 学习（示例：用 dataset/fewshot_samples/ 下的样本）
cd backend && python -c "from fewshot import FewShotLearner; import json; l=FewShotLearner(); r=l.learn([('dataset/fewshot_samples/customs_declaration/bol_201.pdf',json.load(open('dataset/fewshot_samples/customs_declaration/bol_201.json'))),('dataset/fewshot_samples/customs_declaration/bol_202.pdf',json.load(open('dataset/fewshot_samples/customs_declaration/bol_202.json')))]); print(r['yaml_text'])"
```

## Architecture

```
PDF/图片 → preprocess.py → ocr_engine.py → layout_parser.py → field_extractor.py → Flask API
                                               ↑                        ↑
                                        template_signature.py    config.yaml
                                               ↑                        ↑
                                          fewshot.py            vision_fallback.py
                                          (Few-shot 学习)        (视觉大模型兜底)
```

### Pipeline Modules

| 模块 | 文件 | 职责 |
|------|------|------|
| 预处理 | `preprocess.py` | 三段式自动定向(0°~360°) → 纠斜(±0.5°) → CLAHE；不二值化 |
| OCR | `ocr_engine.py` | 封装 PaddleOCR，detect_only(15x)、归一化坐标、批量接口 |
| 版面分析 | `layout_parser.py` | Y投影分行 + 列对齐检测表格，分割为 header/body/table |
| 字段提取 | `field_extractor.py` | 锚点法：三级值定位(内联+右侧+下方+学习偏移)，统一候选评分，多行合并，正则清洗，版式识别 |
| 版式签名 | `template_signature.py` | Few-shot 学习产出的版式特征：归一化坐标+文本相似度匹配，几何驱动的版式检测（替代关键词法） |
| Few-shot | `fewshot.py` | 从 1~5 份标注样本自动发现锚点+位置+校验规则，生成 anchor-layout 签名和 YAML 配置 |
| 视觉兜底 | `vision_fallback.py` | 多供应商（通义/OpenAI/自定义/Ollama）视觉模型兜底，模型探测，AI 版式增强建议 |
| 数据集管理 | `dataset_organizer.py` | 按版式/来源重组数据集目录结构，生成 manifest.json |
| 配置 | `config.yaml` | 每版式自包含（keywords/detection + fields + output），source-label schema（字段 key 为显示名+canonical_key），仅 validators 全局共享 |

### Backend API Notes

`backend/app.py` is responsible for routing plus these important helpers:

| Helper | Purpose |
|------|------|
| `job_dir(job_id, create=True)` | Validates task id and resolves the task directory under `uploads/` |
| `load_job(job_id)` | Restores in-memory job state from disk artifacts |
| `apply_corrections(result, corrections)` | Deep-copies OCR result and overlays human corrections, manual fields, exclusions, and table patches |
| `normalize_corrections_payload(raw)` | Normalizes corrections from old flat format or new rich format (fields, field_labels, manual_fields, excluded_fields, table_patch) |
| `safe_extract_allowed_zip(zip_path, extract_dir)` | Safe ZIP extraction with traversal and size checks |
| `run_recognition_pipeline(job)` | Shared single/batch recognition pipeline — runs OCR → layout → extraction → quality eval → optional vision fallback |
| `apply_ocr_feedback_learning(...)` | Learns anchor→value offset from user corrections and persists into the template |
| `apply_ai_template_enhancement(...)` | Safely merges AI-suggested field config improvements into a target template |
| `ai_enhance_feedback_template(...)` | Calls vision model to enhance a feedback template's anchors and configuration |
| `ai_enhance_fewshot_learning(...)` | Calls vision model to enhance few-shot learned results before YAML generation |
| `export_options_from_args(args)` | Parses export presets: `values` (key-value only), `details` (full fields), `combined` (both + table + meta) |
| `build_export_json_payload(result, options)` | Assembles export JSON with flexible section inclusion |
| `load_vision_settings(include_secret)` | Loads multi-provider vision settings; masks API keys unless `include_secret=True` |
| `save_vision_settings(data)` | Persists provider-specific settings with per-model API keys |
| `render_first_page_for_vision(file_path, file_type, tmp_dir)` | Renders PDF page 1 to PNG at 200 DPI for vision model input |

When changing recognition behavior, update `run_recognition_pipeline()` first; do not duplicate logic separately in `/api/recognize/<id>` and `/api/recognize/batch`.

### API Endpoints (20+)

| Method | Endpoint | Purpose |
|------|------|------|
| POST | `/api/upload` | Upload single file |
| POST | `/api/upload/zip` | Upload ZIP batch |
| POST | `/api/recognize/<id>` | Trigger recognition pipeline |
| POST | `/api/recognize/batch` | Batch recognition |
| GET | `/api/result/<id>` | Get structured result (with corrections) |
| POST | `/api/correct/<id>` | Save corrections (fields, manual_fields, excluded_fields, table_patch) |
| GET | `/api/export/<id>` | Export JSON/XLSX with preset options |
| GET | `/api/image/<id>` | Get original image (PDF→PNG render) |
| GET | `/api/config` | List all templates (visualization-friendly) |
| DELETE | `/api/config/<name>` | Delete a template |
| POST | `/api/config/apply` | Apply few-shot learned config |
| POST | `/api/fewshot/learn` | Few-shot template learning (1-5 PDF+GT pairs) |
| POST | `/api/fewshot/from-result` | Feedback: merge current result fields into a template |
| GET | `/api/history` | List all completed jobs |
| DELETE | `/api/history/<id>` | Delete one job |
| DELETE | `/api/history` | Delete all history |
| GET | `/api/vision-settings` | Get vision fallback settings (keys masked) |
| POST | `/api/vision-settings` | Save vision settings |
| POST | `/api/vision-settings/probe` | Probe available vision models |
| GET | `/api/vision-settings/api-key` | Reveal saved API key (eye toggle) |
| DELETE | `/api/vision-settings` | Clear all vision settings |
| GET | `/api/health` | Health check |
| GET | `/api/jobs` | List all in-memory jobs |

### OCR Engine API

| 方法 | 作用 | 速度 |
|------|------|------|
| `recognize_image(img, normalize=False)` | 检测+识别 | ~0.28s (GPU) / ~2.5s (CPU) |
| `detect_only(img)` | 仅检测出文本框坐标 | ~0.05s |
| `recognize_images([img1, img2])` | 批量识别 | N×0.28s (GPU) |
| `recognize_pdf(path)` | PDF 逐页识别 | 同上 |
| `detect_pdf(path)` | PDF 逐页检测 | 逐页 0.05s |

### Field Extractor API

| 方法 | 作用 |
|------|------|
| `extract(regions, image_size, blocks)` | 从版面分析结果提取字段 + 表格（主入口） |
| `reload_config(path)` | 运行时热更新配置（不重启） |
| `_detect_template(blocks, image_size)` | 版式识别：anchor_layout 签名优先，关键词兜底 |
| `_find_anchor_blocks(blocks, anchors)` | 模糊匹配锚点关键词 |
| `_find_value_right_candidates(anchor, candidates)` | 同行右侧值定位（Y对齐+X邻近评分） |
| `_find_value_below_candidates(anchor, candidates)` | 紧邻下方值定位 |
| `_find_learned_offset_candidates(anchor, candidates, offset)` | 按反馈学习到的锚点→值块中心偏移定位 |
| `_extract_inline_value(block, anchor)` | 从标签+值合并块中提取值 |
| `_build_value_candidate(...)` | 统一候选评分（锚点分+几何分+OCR置信度+校验分-冲突/标签惩罚） |
| `_merge_multiline_value(block, candidates)` | 向下合并同列多行文本（地址/公司名等） |
| `_extract_table(table_blocks)` | 表格区域行列结构恢复 |
| `_detect_columns(header_blocks)` | 表头X聚类+多行标签合并 |
| `_merge_table_rows(rows, cols)` | 行分类+continuation合并+summary跳过 |

返回格式: `{"fields": {name: {value, cleaned, confidence, ...}}, "table": {"headers": [...], "rows": [[...], ...]}, "template": "maersk_style"}`

### template_signature.py API

| 函数 | 作用 |
|------|------|
| `build_anchor_layout_signature(sample_blocks, field_observations, image_sizes, excluded_block_ids)` | 从多份样本中提取稳定的归一化坐标特征（field_anchor + stable_text） |
| `score_anchor_layout_signature(detection, blocks, image_size)` | 对输入文档打分：归一化坐标匹配+文本相似度，返回 `{score, matched_count, accepted}` |
| `normalized_center(block, image_size)` | 将 OCR 块 rect 转为 (x_ratio, y_ratio) 归一化坐标 |
| `normalize_signature_text(text)` | 标准化签名文本（去空格/标点，小写） |

### Preprocessing Pipeline

| 方法 | 作用 | 备注 |
|------|------|------|
| `to_gray(image)` | 彩色→灰度图 | 所有处理的基础 |
| `deskew(gray_img)` | 霍夫线变换纠斜 | ±15° 精度到 ±0.5°，IQR 一致性检查防误纠 |
| `enhance_contrast(gray_img)` | CLAHE 增强 | 提升置信度 ~5pp |
| `auto_orient(gray_img, engine=None)` | 三段式自动定向 | 0°~360° 覆盖；传入 engine 启用 OCR 兜底 |
| `process_pdf(path, dpi=200, mode, engine)` | 完整 PDF 预处理 | 返回 `[(pil_img, gray_img), ...]` |
| `process_image(img, engine, mode)` | 单图预处理 | 自动定向→纠斜→CLAHE |

不推荐使用的工具方法（已退出默认管线）：`binarize()`, `denoise()`

```
灰度图 → _auto_orient_full() → deskew() → CLAHE → OCR
           │                    │          │
           │ Stage1 霍夫直方图  │ 细调±15° │ +5pp 置信度
           │ 失败→Stage2 OCR兜底 │          │
           └─ 覆盖 0°~360° ─────┘          │
```
传入 `engine` 参数可启用 Stage2 OCR 四方向兜底（用 `detect_only`，~1s）；不传则仅霍夫直方图。

### Dataset Structure

`dataset/` 已按版式+来源重组为子目录结构：

| 路径 | 编号 | 来源 | 版式标记 |
|------|------|------|------|
| `synthetic_bol/maersk_style/` | bol_001~160 (每3个一组) | 合成数据 (80%) | maersk_style |
| `synthetic_bol/cosco_style/` | bol_002~158 (每3个一组) | 合成数据 | cosco_style |
| `synthetic_bol/simple_style/` | bol_003~159 (每3个一组) | 合成数据 | simple_style |
| `public_funsd/coupon_registration/` | bol_161~168 | FUNSD 公开 | funsd_public |
| `public_funsd/retail_progress_report/` | bol_169~176 | FUNSD 公开 | funsd_public |
| `public_funsd/challenge_singletons/` | bol_177~180 | FUNSD 公开 | funsd_public |
| `real_scans/food_delivery/` | bol_181~190 | 真实扫描 | real_scan |
| `real_scans/express/` | bol_191~200 | 真实扫描 | real_scan |
| `fewshot_samples/customs_declaration/` | bol_201~205 | 未知版式测试 | customs_declaration |
| `fewshot_samples/warehouse_receipt/` | bol_206~210 | 未知版式测试 | warehouse_receipt |

每个子目录包含 `samples.json` 和 `README.md`。根 `manifest.json` 记录全量索引。
KIE 模块根据 `template` 字段自动选择对应的 anchor 配置（keywords 或 anchor_layout 签名）。

## Key Design Decisions

- **不用大模型**：PaddleOCR + 规则匹配，不训练 Donut/LayoutLMv3
- **坐标优先**：所有提取基于 bbox 坐标 (x1,y1,x2,y2)，不依赖文本顺序
- **先硬后软**：先死磕一种版式 100%，再通过 YAML 适配多版式
- **Playwright 替代 weasyprint**：Windows 兼容，不需要 GTK3，输出质量更好
- **PaddleOCR 2.x**：PaddleOCR 3.x 在 Windows 上有 ONEDNN/PIR 推理 bug，已降到 2.10 + Paddle 2.6 解决。`requirements.txt` 约束 `<3`
- **预处理不做二值化/去噪**：PaddleOCR 检测器需要自然灰度图的梯度信息，二值化反而破坏检测。实测 CLAHE 提升置信度 ~5pp
- **标签检测 `_looks_like_label()`**：字段提取的关键防线，防止把标签文本误当值。7 条规则：
  1. 冒号结尾（含全角：）+ 较短 → 标签
  2. 纯字母+冒号模式 → 标签
  3. 已知表头词 `_TABLE_HEADER_WORDS` → 标签
  4. 纯中文 1-4 字 → 标签
  5. 极短缩写（≤5字符）在 `_SHORT_LABELS` → 标签
  6. 含中文锚点关键词的短文本（<20字）→ 标签（防 `"订舱号 B/L"`、`"装货港 POL"` 等中英混合标签）
  7. 精确匹配 `_KNOWN_LABEL_TEXTS`（40+ 英文字段标签）→ 标签（防 `"SHIPPER"`、`"VESSEL"`、`"PORT OF LOADING"` 等无冒号英文标签）
  注意：不能把正常数据值（如 "SHANGHAI", "ONE HARBOUR"）误判为标签
- **标签残片检测 `_is_label_residue()`**：值定位时的二次过滤，排除含 "Place of"、"Date of"、"& Date" 等锚点关键词的文本块，防止标签被当成值
- **单位感知校验**：weight 字段拒绝含 "CBM" 的值，volume 字段拒绝含 "KGS" 的值。防止 `total_gross_weight` 抢走 `total_measurement` 的值（反之亦然）
- **表格标签过滤**：表格行→列分配时过滤 `_looks_like_label` 块，防止 `"Weight:"` 等标签碎片混入货物明细数据
- **短锚点陷阱**：避免使用 `"Weight:"` / `"Measurement:"` 等短锚点，易模糊匹配无关文本（如 `"Weight:"` 匹配 `"Freight:"` 得分 0.80）。改用版式特有精确锚点（`"G.W.(KGS)"` / `"CBM:"`）
- **PaddlePaddle GPU 加速**：RTX 4060，paddlepaddle-gpu 2.6.2 + CUDA 11.8 + cuDNN 8.9。OCR 从 2.5s/份 降至 **0.28s/份（9x 提速）**。需手动拷贝 NVIDIA DLL 到 `venv/Lib/site-packages/paddle/libs/`
- **Few-shot 版式自适应**：给定新版式的 2~5 份 PDF + GT JSON，自动发现锚点关键词、位置策略和校验规则（含正则模式自动生成）。支持**值块内联标签提取**（处理 `标签：值` 合并块）和**GT 值惩罚**（排除其他字段的值被误当锚点）。前端支持批量拖入文件按文件名自动配对、自定义版式命名。核心算法在 `fewshot.py`，API: `POST /api/fewshot/learn` + `POST /api/config/apply`
- **Anchor-Layout 版式签名**：Few-shot 学习产出的版式特征不再仅依赖关键词，而是记录字段锚点和稳定文本的归一化坐标 `(x_ratio, y_ratio)`。新文档匹配时用归一化距离+文本相似度打分，几何驱动，不依赖预设词汇表。实现在 `template_signature.py`。
- **统一候选评分**：`_build_value_candidate()` 统一了 inline/learned_offset/right/below 四种策略的评分：锚点分×0.32 + 几何分×0.28 + OCR置信度×0.22 + 校验分 - 使用冲突惩罚 - 标签惩罚。所有候选排序选最优，而非第一个可用。
- **OCR 反馈学习**：用户校正字段后，系统自动反查 OCR 块坐标，计算锚点中心→值块中心的偏移量 `(dx, dy)` 和容差，写入模板的 `learned_value_offset`。后续识别时该偏移量作为最高优先级的值定位策略。
- **AI 版式增强**：Few-shot 学习和结果反哺均可选调用视觉大模型（`ai_enhance=true`）。模型基于文档图片+OCR块+当前字段值，建议更优的锚点、位置策略、value_pattern 和 table_headers。失败不回退本地结果。
- **多供应商视觉兜底**：支持通义千问（阿里云百炼）、OpenAI、自定义 OpenAI-compatible 端点和 Ollama 本地模型。每个供应商独立保存 profile（base_url、model、api_key、model_api_keys）。模型检测端点 `/api/vision-settings/probe` 可探测可用模型列表。
- **版式配置可视化**：前端「版式管理」抽屉展示所有模板的字段、锚点、位置、校验规则，非技术人员可读。API: `GET /api/config`
- **未识别版式处理**：上传未知版式时前端显示 OCR 文本块预览 + Few-shot 学习引导，不再静默失败
- **识别历史**：顶栏「历史」按钮，列出所有已完成任务，点击新标签页查看。支持逐条删除 + 一键清空全部。API: `GET /api/history` + `DELETE /api/history/<id>` + `DELETE /api/history`
- **自包含版式配置**：config.yaml 重构为每个模板自包含结构（keywords/detection + fields + output 全在模板内部），仅 `validators` 和 `field_defaults` 全局共享。旧格式文件首次加载时自动内存迁移。
- **Source-Label Schema**：字段 key 使用文档原始显示名（如 `"Shipper"`、`"B/L No."`），通过 `canonical_key` 保留内部标识（`shipper`、`bl_no`）。每个版式用自己的字段名体系。字段支持 `multi_line`、`value_pattern`、`allow_shared`、`search_in` 等细粒度控制。
- **人工字段与校正**：校正接口支持新增字段（`manual_fields`，可指定 OCR 锚点文本/坐标和值坐标）、排除字段（`excluded_fields`）、覆盖字段标签（`field_labels`）、替换表格（`table_patch` 的 replace 模式）。校正后的字段在导出和前端回显中保持一致。
- **导出预设**：`GET /api/export/<id>?format=xlsx&preset=values` 支持三个预设：`values`（简洁键值）、`details`（完整字段明细）、`combined`（两者+表格+元信息，默认）。
- **测试目录**：测试文件已迁至 `tests/` 目录。
- **FUNSD 不是物流模板**：当前 `funsd_public` 是 `enabled: false, hidden: true`，仅用于跨域验证。FUNSD 本质是通用表单 question-answer linking，不适合继续强行套物流锚点抽取法。若要提升 FUNSD，应单独实现 FUNSD 模式，输出动态 question-answer pairs。
- **手写识别不是当前强项**：PaddleOCR 默认通用印刷体模型适合清晰打印件。手写、连笔、低清扫描、表格线干扰属于不同 OCR/HTR 任务，不能只靠锚点规则修好。
- Playwright Chromium 已安装在 `C:\Users\18246\AppData\Local\ms-playwright\`

## Safety and Maintenance Rules

- The repository often has a dirty worktree with generated data and local reports. Do not revert unrelated changes.
- Use `rg`/`rg --files` for search. On Windows, prefer PowerShell-native safe filesystem operations.
- Use `apply_patch` for manual source edits.
- Avoid editing generated datasets unless the task explicitly asks for data regeneration.
- Do not reintroduce raw ZIP `extractall()`.
- Do not bypass `job_dir()` for task paths.
- Do not add a second recognition path for batch processing; keep batch and single recognition unified.
- If adding a new form family, decide whether it belongs to logistics anchor extraction, Few-shot YAML generation, or a separate mode such as FUNSD question-answer extraction.
- When adding a new field property (like `multi_line`, `allow_shared`), propagate it through: config.yaml schema → field_extractor.py extraction → fewshot.py generation → app.py config/apply serialization.
- Vision fallback settings changes must go through `save_vision_settings()` / `load_vision_settings()` — never write directly to `vision_settings.json`.

## Progress

- ✅ Day 1-2: 环境搭建、合成数据生成器、200份数据集
- ✅ Day 3: OCR 引擎封装，合成+真实三版式验证通过
- ✅ Day 4: 图像预处理，纠斜+CLAHE，移除二值化/去噪，批量验证通过
- ✅ Day 5-6: OCR 引擎完善，detect_only(15x加速)、坐标归一化、三段式自动定向
- ✅ Day 7: 版面分析，Y投影分行+列对齐检测表格，三版式验证通过
- ✅ Day 8-9: 字段提取，锚点法三级值定位+模糊匹配+正则清洗，97.9% 准确率
- ✅ Day 10-11: 动态 Schema 配置，config.yaml 驱动，配置与逻辑分离。**已重构为自包含版式结构**，每模板独立管理字段+锚点+输出列表
- ✅ Day 12: 表格结构恢复，列检测+行分类+多行合并，输出 {headers, rows} 结构化 JSON
- ✅ Day 13-14: Flask 后端 API，20+ REST 端点（含 ZIP/批量/Few-shot/版式管理/历史/历史删除/视觉设置/模型探测/AI增强）
- ✅ Day 15-18: Vue3 前端（Element Plus + Hero 首页 + 拖拽上传 + 批量处理 + Few-shot 批量文件配对 + 版式命名 + 历史删除 + 版式管理 + 模型设置面板 + 多供应商切换 + 模型探测）
- ✅ 联调测试：20+ API 端点通过，3 版式准确率 97.9%
- ✅ Few-shot 版式自适应 + 内联标签提取 + GT值惩罚 + top 3 锚点 + 多行检测 + 一键应用到 config.yaml
- ✅ GPU 加速：PaddleOCR RTX 4060，0.28s/份，9x 提速
- ✅ Source-Label Schema：字段 key 使用文档显示名 + canonical_key 映射 + multi_line/allow_shared/value_pattern 细粒度控制
- ✅ 视觉大模型兜底：多供应商（通义/OpenAI/自定义/Ollama），模型探测，AI 版式增强，前端完整配置面板
- ✅ Anchor-Layout 版式签名：Few-shot 学习产出几何驱动的版式特征，归一化坐标匹配替代关键词法
- ✅ OCR 反馈学习：校正值反查 OCR 坐标 → 学习偏移量 → 写入模板，后续识别优先使用
- ✅ AI 版式增强：Few-shot 学习/结果反哺可选调用视觉模型优化锚点和字段配置
- ✅ 未识别版式处理：OCR 文本块预览 + Few-shot 引导
- ✅ 工程硬化：安全 ZIP、job_id/path 校验、磁盘恢复、校正回显/导出一致、单张/批量 pipeline 统一
- ✅ 数据集重组：按版式/来源分目录，manifest.json 索引
- ✅ 人工字段/排除/表格补丁/标签覆盖：校正接口完整支持
- ✅ 导出预设：values/details/combined 三种模式，灵活组装 JSON/XLSX
- ⏳ Day 21: 收尾（README、课程设计报告），详见 `TASKS.md`
- 详细设计见 `.claude/plans/composed-conjuring-eich.md`

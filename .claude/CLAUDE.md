# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

物流单证智能识别系统 — 基于 OCR 与版面分析，从 PDF/图片中提取物流单证的关键字段（Shipper、B/L No.、Gross Weight 等），输出结构化 JSON。Python + PaddleOCR + Flask 后端 + Vue3 前端，课程设计项目。

## Current Engineering Status

As of 2026-07-14, the first two hardening phases are implemented:

- ZIP upload no longer uses `extractall()`. It validates member paths, limits member count, limits total uncompressed size, and only writes allowed document/image files.
- Route-level `job_id` validation is enabled for task endpoints. Job paths are resolved under the upload root and history deletion no longer creates empty directories for missing IDs.
- Jobs can be restored from disk after restart using `result.json`, `blocks.json`, `corrections.json`, and `original.*`.
- Single-file and batch recognition now share `run_recognition_pipeline()`, so both persist `result.json` and `blocks.json`.
- Corrections are merged back into field results and exported JSON/XLSX. Frontend reload now displays corrected values instead of reverting to OCR values.
- Multi-page PDFs are still processed page 1 only, but `meta.page_count`, `meta.processed_page`, and warnings make this limitation explicit.
- Frontend API base defaults to relative `/api` and supports `VITE_API_BASE_URL`.

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

# 运行 OCR 测试（11 项，覆盖 Day 3-12 全部模块）
python test.py

# 批量测试 + 生成报告 PDF（70 份，含合成+FUNSD+真实扫描）
cd backend && python batch_test.py

# 生成合成数据（160份，bol_001~160）
cd backend && python generate_data.py

# 转换 FUNSD 公开数据（20份，bol_161~180）
cd public_data && python convert_funsd.py

# 转换真实扫描数据（20份，bol_181~200）
cd real_data && python convert_real.py

# 运行 Flask 后端
cd backend && python app.py

# 运行 Vue3 前端（开发模式，默认 8080 端口）
cd frontend && npm run dev

# 一键启动（后端 + 前端）
python run.py

# 后端语法/导入编译检查
.venv\Scripts\python.exe -m compileall -q backend run.py test.py

# 前端生产构建
cd frontend && npm.cmd run build

# 生成未知版式测试数据（报关单 + 入库单，bol_201~210）
cd backend && python gen_new_templates.py

# Few-shot 学习（从 2 份 Maersk 样本自动生成配置）
cd backend && python -c "from fewshot import FewShotLearner; import json; l=FewShotLearner(); r=l.learn([('dataset/pdf/bol_001.pdf',json.load(open('dataset/json/bol_001.json'))),('dataset/pdf/bol_004.pdf',json.load(open('dataset/json/bol_004.json')))]); print(r['yaml_text'])"
```

## Architecture

```
PDF/图片 → preprocess.py → ocr_engine.py → layout_parser.py → field_extractor.py → Flask API
                                                                      ↑
                                                               config.yaml
```

### Pipeline Modules

| 模块 | 文件 | 职责 |
|------|------|------|
| 预处理 | `preprocess.py` | 三段式自动定向(0°~360°) → 纠斜(±0.5°) → CLAHE；不二值化 |
| OCR | `ocr_engine.py` | 封装 PaddleOCR，detect_only(15x)、归一化坐标、批量接口 |
| 版面分析 | `layout_parser.py` | Y投影分行 + 列对齐检测表格，分割为 header/body/table |
| 字段提取 | `field_extractor.py` | 锚点法：三级值定位(内联+右侧+下方)，模糊匹配，正则清洗，版式识别，97.9% 准确率 |
| Few-shot | `fewshot.py` | 从 1~5 份标注样本自动发现锚点+位置+校验规则，生成 YAML 配置 |
| 视觉兜底 | `vision_fallback.py` | 本地规则置信度不足时调用视觉大模型兜底（通义/Claude/OpenAI），可配置开关 |
| 配置 | `config.yaml` | 每版式自包含（keywords + fields + output），source-label schema（字段 key 为显示名+canonical_key），仅 validators 全局共享 |

### Backend API Notes

`backend/app.py` is now responsible for more than routing. Important helpers:

| Helper | Purpose |
|------|------|
| `job_dir(job_id, create=True)` | Validates task id and resolves the task directory under `uploads/` |
| `load_job(job_id)` | Restores in-memory job state from disk artifacts |
| `apply_corrections(result, corrections)` | Deep-copies OCR result and overlays human corrections into fields |
| `safe_extract_allowed_zip(zip_path, extract_dir)` | Safe ZIP extraction with traversal and size checks |
| `run_recognition_pipeline(job)` | Shared single/batch recognition pipeline and persistence path |

When changing recognition behavior, update `run_recognition_pipeline()` first; do not duplicate logic separately in `/api/recognize/<id>` and `/api/recognize/batch`.

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
| `extract(regions, image_size)` | 从版面分析结果提取字段 + 表格 |
| `reload_config(path)` | 运行时热更新配置（不重启） |
| `_find_anchor_blocks(blocks, anchors)` | 模糊匹配锚点关键词 |
| `_find_value_right(anchor, candidates)` | 同行右侧值定位（Y对齐+X邻近评分） |
| `_find_value_below(anchor, candidates)` | 紧邻下方值定位 |
| `_extract_inline_value(block, anchor)` | 从标签+值合并块中提取值 |
| `_extract_table(table_blocks)` | 表格区域行列结构恢复 |
| `_detect_columns(header_blocks)` | 表头X聚类+多行标签合并 |
| `_merge_table_rows(rows, cols)` | 行分类+continuation合并+summary跳过 |

返回格式: `{"fields": {name: {value, cleaned, confidence, ...}}, "table": {"headers": [...], "rows": [[...], ...]}, "template": "maersk_style"}`

支持的字段: 物流15字段(shipper~issue_date) + FUNSD 5字段(sender~region) + 真实扫描 10字段(tracking_no~courier)

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

`dataset/` 下 pdf/ 和 json/ 一一对应，按 `bol_001~200` 编号：

| 编号 | 来源 | 版式标记 |
|------|------|------|
| 001-160 | 合成数据 (80%) | maersk_style / cosco_style / simple_style |
| 161-180 | FUNSD 公开 (10%) | funsd_public |
| 181-200 | 真实扫描 (10%) | real_scan (express / food_delivery) |
| 201-210 | 未知版式测试 | customs_declaration / warehouse_receipt（`dataset/unknown_templates/`）|

KIE 模块根据 `template` 字段自动选择对应的 anchor 配置。

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
- **版式配置可视化**：前端「版式管理」抽屉展示所有模板的字段、锚点、位置、校验规则，非技术人员可读。API: `GET /api/config`
- **未识别版式处理**：上传未知版式时前端显示 OCR 文本块预览 + Few-shot 学习引导，不再静默失败
- **识别历史**：顶栏「历史」按钮，列出所有已完成任务，点击新标签页查看。支持逐条删除 + 一键清空全部。API: `GET /api/history` + `DELETE /api/history/<id>` + `DELETE /api/history`
- **自包含版式配置**：config.yaml 重构为每个模板自包含结构（keywords + fields + output 全在模板内部），仅 `validators` 全局共享。旧格式文件首次加载时自动内存迁移。
- **Source-Label Schema**：字段 key 使用文档原始显示名（如 `"Shipper"`、`"B/L No."`），通过 `canonical_key` 保留内部标识（`shipper`、`bl_no`）。每个版式用自己的字段名体系。
- **视觉大模型兜底**：本地规则低置信度时自动调用视觉模型兜底。开关可控，兜底失败保留本地结果。前端「模型设置」面板可配置 provider/API Key/阈值。API: `GET/POST /api/vision/settings`。
- **测试目录**：测试文件已迁至 `tests/` 目录。
- **FUNSD 不是物流模板**：当前 `funsd_public` 只是用少量固定字段做跨域验证。FUNSD 本质是通用表单 question-answer linking，不适合继续强行套物流锚点抽取法。若要提升 FUNSD，应单独实现 FUNSD 模式，输出动态 question-answer pairs。
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

## Progress

- ✅ Day 1-2: 环境搭建、合成数据生成器、200份数据集
- ✅ Day 3: OCR 引擎封装，合成+真实三版式验证通过
- ✅ Day 4: 图像预处理，纠斜+CLAHE，移除二值化/去噪，批量验证通过
- ✅ Day 5-6: OCR 引擎完善，detect_only(15x加速)、坐标归一化、三段式自动定向
- ✅ Day 7: 版面分析，Y投影分行+列对齐检测表格，三版式验证通过
- ✅ Day 8-9: 字段提取，锚点法三级值定位+模糊匹配+正则清洗，97.9% 准确率
- ✅ Day 10-11: 动态 Schema 配置，config.yaml 驱动，配置与逻辑分离。**已重构为自包含版式结构**，每模板独立管理字段+锚点+输出列表
- ✅ Day 12: 表格结构恢复，列检测+行分类+多行合并，输出 {headers, rows} 结构化 JSON
- ✅ Day 13-14: Flask 后端 API，14+ REST 端点（含 ZIP/批量/Few-shot/版式管理/历史/历史删除）
- ✅ Day 15-18: Vue3 前端（Element Plus + Hero 首页 + 拖拽上传 + 批量处理 + Few-shot 批量文件配对 + 版式命名 + 历史删除 + 版式管理 + 模型设置面板）
- ✅ 联调测试：16/16 API 端点通过，3 版式准确率 97.9%
- ✅ Few-shot 版式自适应 + 内联标签提取 + GT值惩罚 + top 3 锚点 + 多行检测 + 一键应用到 config.yaml
- ✅ GPU 加速：PaddleOCR RTX 4060，0.28s/份，9x 提速
- ✅ Source-Label Schema：字段 key 使用文档显示名 + canonical_key 映射
- ✅ 视觉大模型兜底：低置信度时自动调用视觉模型，前端可配置
- ✅ 未识别版式处理：OCR 文本块预览 + Few-shot 引导
- ✅ 工程硬化：安全 ZIP、job_id/path 校验、磁盘恢复、校正回显/导出一致、单张/批量 pipeline 统一
- ⏳ Day 21: 收尾（README、课程设计报告），详见 `TASKS.md`
- 详细设计见 `.claude/plans/composed-conjuring-eich.md`

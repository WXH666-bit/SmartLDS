# SmartLDS 每日任务清单

## Day 1 — 环境搭建与项目骨架 ✅ 已完成

- [x] 创建项目目录结构
- [x] 创建所有后端空文件（app.py, ocr_engine.py, layout_parser.py, field_extractor.py, generate_data.py, preprocess.py, config.yaml）
- [x] 安装 Python 依赖（paddlepaddle, paddleocr, flask, opencv, playwright, faker, pymupdf 等）
- [x] 用 Playwright 替代 weasyprint（Windows 兼容性更好）

**产出**：项目骨架 + 所有依赖就绪

---

## Day 2 — 合成数据生成器 ✅ 已完成

- [x] 编写3种版式的 HTML 模板（Maersk / COSCO / 简易委托书）
- [x] Faker 随机生成14个字段的假数据
- [x] Playwright 渲染 HTML → PDF
- [x] 同步生成 Ground Truth JSON 标注
- [x] 路径修复：无论从哪里运行都输出到根目录 dataset/

**产出**：运行 `cd backend && python generate_data.py` 生成200份 PDF + JSON

---

## Day 3 — OCR 技术验证 ✅ 已完成

- [x] 验证 PaddleOCR 中英文模型能正常调用（PP-OCRv4，遇到 ONEDNN bug 降级到 PaddleOCR 2.x 解决）
- [x] 验证 PyMuPDF PDF → PIL Image 转换流程
- [x] 端到端验证：合成PDF → 转图片 → PaddleOCR → 输出带bbox的JSON，Maersk/COSCO/真实扫描三种均通过
- [x] 写 `ocr_engine.py` 基础封装（OCREngine 类，支持 image 和 PDF 两种输入）

**产出**：`ocr_engine.py` 完整可用，输出 `[{text, confidence, bbox, rect}]`

---

## Day 4 — 图像预处理 ✅ 已完成

- [x] `preprocess.py`：PDF→图片、灰度化、CLAHE增强、去噪、纠斜
- [x] 两种模式：light（手机照片，CLAHE+中值滤波）/ hard（扫描件，二值化+纠斜）
- [x] 实测：真实快递面单从 10 块提升到 13 块（+30%）

**产出**：预处理流水线可运行

---

## Day 5-6 — OCR 引擎完善 ✅ 已完成

- [x] 完善 `ocr_engine.py`：
  - 封装 PaddleOCR 调用
  - 标准化输出：`[{text, confidence, bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}]`
  - 文本块排序（从上到下、从左到右）
  - 坐标归一化（`normalize=True` → [0,1] 区间）
  - 支持多页 PDF
  - `detect_only(image)` — 仅检测文本框，0.26s，比完整 OCR 快 15x
  - `recognize_images([...])` — 批量识别接口
  - `detect_pdf(path)` — PDF 逐页仅检测
- [x] 三段式自动定向 `_auto_orient_full`：
  - Stage 1: 霍夫角度直方图 → 找文字行主峰，覆盖任意角度（~0.1s）
  - Stage 2: OCR 四方向兜底（用 detect_only，~1s），Stage 1 失败时触发
  - Stage 3: deskew 细调 ±15°（精度 ±0.5°）
  - 覆盖 0°~360° 任意旋转，实测块数 +8.8，置信度 +14pp

**产出**：完整 OCR 接口 + 全角度自动定向

---

## Day 7 — 版面分割 ✅ 已完成

- [x] 实现 `layout_parser.py`：
  - Y 投影法：同行块 Y 重叠合并，行间距 > 中位数 1.8x 切分
  - 列对齐检测表格：一行 3+ 块 + 相邻行 X 中心对齐 ≥2 列 → 表格
  - 区域分类：顶部 18% → header，表格行段 → table，其余 → body
- [x] 输出：`{"header": [...], "body": [...], "table": [...]}`
- [x] 三版式验证：Maersk (header 2 + body 21 + table 43)、COSCO（无表格）、FUNSD（检测到表格）

**产出**：版面分割模块

---

## Day 8-9 — 锚点法字段提取 ✅ 已完成

- [x] 实现 `field_extractor.py`：
  - 锚点关键词列表：16 个字段，中英文多变体（Shipper + 托运人、B/L No. + 提单号 + 订舱号 等）
  - 模糊匹配：SequenceMatcher (LCS) 容错 OCR 误识别（如 "SHlPPER" → "SHIPPER"）
  - 三级值定位：
    1. 锚点块内联提取（标签+值合并在同一 OCR 块，如 "Vessel: ONE HARBOUR"）
    2. 同行右侧（Y中心对齐 + X邻近加权评分）
    3. 紧邻下方（X左对齐 + Y间距合理）
  - 标签检测 `_looks_like_label()`：防止把标签误当值（冒号结尾、已知表头词、短标签黑名单、纯中文短词）
  - 锚点匹配评分：锚点占文本比例越高 → 越可能是真正的标签（防止 "托运人" 匹配到 "托运人信息" 标题块）
- [x] 正则清洗：B/L号、日期（dd/mm/yyyy）、重量（KGS 后缀）、体积（CBM 后缀）、签发地（分离 "地点, 日期" 合并文本）
- [x] 版式自动识别：关键词投票（MAERSK / COSCO / SHIPPING ORDER 等）
- [x] 表格提取：Y中心聚类分行 → 二维数组 `[[cell, ...], ...]`
- [x] 验证：15 样本三版式准确率 96.8%（Maersk 97.5%, COSCO 93.5%, Simple 100%）— COSCO 的 1 个错误是 OCR 误读（NINGBO→NINGB0）

**产出**：`field_extractor.py` 完整可用，锚点法提取准确率 > 95%

---

## Day 10-11 — 动态 Schema 配置 ✅ 已完成

- [x] 编写 `config.yaml`：
  - `templates`: 5 种版式关键词（maersk/cosco/simple/funsd/real_scan）
  - `fields`: 15 个字段定义（anchors + position + validator）
  - `validators`: 5 条正则规则（bl_no/date/weight/volume/place_date）
  - `template_overrides`: 版式特定字段覆盖（COSCO 收/发货地等）
- [x] 重构 `field_extractor.py` — 配置与逻辑分离：
  - `FieldExtractor(config_path)` 自动加载 YAML，不存在则回退内置默认值
  - `field_defs` / `template_keywords` / `validators_cfg` 属性从配置读取
  - `validate_and_clean()` 支持 YAML 配置驱动 + 内置回退双模式
  - `reload_config()` 支持运行时热更新配置
  - 向后兼容：旧的 `FIELD_ANCHORS` / `TEMPLATE_KEYWORDS` 模块常量仍可用
- [x] 验证：三版式准确率不变（100% / 92% / 100%），配置自动加载正确

**产出**：`config.yaml` + 配置驱动架构，新增版式只需编辑 YAML 不碰 Python

---

## Day 12 — 表格结构恢复 ✅ 已完成

- [x] 对 table 区域进行结构化提取：
  - **列检测** `_detect_columns()`：表头块 X 聚类 → 相邻列间距离子检测 → 多行标签合并（"Gross"+"Weight"→"Gross Weight"）
  - **块→列分配** `_assign_to_column()`：按 X 中心距离 + 列宽容差
  - **行分类**：header / data / continuation（块数<列数×0.4）/ summary（含 Total/Freight 关键词）
  - **多行合并**：连续 continuation 行拼入前一 data 行（货物描述跨行合并）
- [x] 表格验证：表头含字段标签（Shipper/Consignee）→ 跳过；不含货物列名（Container/Weight）→ 跳过
- [x] 输出格式：`{"headers": [...], "rows": [[...], ...]}`，每行按列顺序排列
- [x] 验证：6 个 Maersk 样本一致输出 8 列×2-3 行，描述跨行合并正确，汇总行排除正确

**产出**：结构化货物明细表格提取

---

## Day 13-14 — Flask 后端 API ✅ 已完成

- [x] `POST /api/upload` — 文件上传，支持 PDF/PNG/JPG，返回 job_id
- [x] `POST /api/recognize/<id>` — 触发完整流水线（预处理→OCR→版面分析→字段提取→表格恢复）
- [x] `GET /api/result/<id>` — 获取结构化结果（字段JSON + OCR块bbox + 表格数据）
- [x] `POST /api/correct/<id>` — 保存人工校正字段值
- [x] `GET /api/export/<id>` — 导出 Excel（openpyxl，3 Sheet：字段/货物明细/元信息）或 JSON
- [x] `GET /api/image/<id>` — 获取原始图片（PDF 转 PNG 返回，图片直返）
- [x] 跨域配置（flask-cors）、文件大小限制 32MB、upload/ 任务目录隔离
- [x] 验证：Flask test client 全流程通过，字段提取+表格恢复+校正导出均正确

**产出**：`app.py` 完整 Flask 服务，7 个端点 + 完整流水线集成

---

## Day 15-18 — Vue3 前端

- [x] 创建 Vue3 + Vite 项目 (`frontend/`)
- [x] 安装 Element Plus + Axios + Fabric.js 5.x
- [x] 上传页面（拖拽上传 + 文件选择）
- [x] 结果展示页（单页 SPA）：
  - 左侧 Fabric.js Canvas 彩色矩形框标注识别位置
  - 右侧 Element Plus 表格展示字段（双击可编辑）
- [x] 人工校正（保存到后端）+ 导出 JSON / Excel
- [x] 货物明细表格 + 原始 JSON 折叠面板
- [x] Vite 代理配置（`/api` → Flask 5000 端口）

**产出**：`frontend/` 完整 Vue3 SPA，`npm run dev` 启动

**启动方式**：
```bash
cd frontend && npm run dev       # 前端 http://localhost:5173
cd backend && python app.py      # 后端 http://localhost:5000
```

---

## Day 19-20 — 联调测试 ✅ 已完成

- [x] 端到端测试：上传 → 识别 → 展示 → 修正 → 导出（16/16 API 端点通过）
- [x] 3种版式各测10份，统计准确率（97.9%）
- [x] 错误处理完善（非法格式、无效 ID、空文件等）
- [x] GPU 加速：RTX 4060 + paddlepaddle-gpu 2.6.2，0.28s/份（9x 提速）

**产出**：全流程可演示

---

## Day 21 — 收尾

- [ ] 清理代码，添加注释
- [ ] 编写 README.md
- [ ] 编写课程设计报告（如需要）

**产出**：项目交付

---

## 未来优化方向（论文加分项，不必现在实现）

### 1. 任意角度倾斜文档的识别

当前方案覆盖了 ±15° 倾斜（preprocess 纠斜）和 180° 倒置（PaddleOCR `use_angle_cls=True`），但 45~90° 横竖颠倒无法处理。

**思路**：自适应旋转检测——将输入图旋转 0°/90°/180°/270° 四个方向各跑一次 OCR，哪个方向识别出的有效文字最多、置信度最高就用哪个，四行代码搞定。

### 2. 大数据模型方案对比

当前用 PaddleOCR + 规则匹配（Rule-based），如果未来有标注数据，可以对比训练 LayoutLMv3 / Donut 等深度学习方案，量化两种方案的精度差异，论文会更有深度。

### 3. 多页文档关联

当前只处理单页单证，如果有装订在一起的多页提单（正本+副本+附件），可以增加页码关联逻辑，把分散在多页的字段合并输出。

### 4. 手写体识别

FUNSD 数据集中包含手写体字段，当前 PaddleOCR 对手写体效果一般。可以单独训练手写识别模型作为补充通道。

### 5. Few-shot 版式自适应（论文进阶目标）✅ 已实现

当前版式识别使用关键词投票（纯规则），论文要求的进阶目标是：
> "通过少量样本适应新的单证模板（例如从 Maersk 模板切换到 COSCO 模板）"

**已实现方案**：`backend/fewshot.py`，核心思路是反向工程——已知 GT 值，在 OCR 块中定位→找最近的标签→提取锚点→推断位置。

1. **值定位** — 在所有 OCR 块中模糊匹配 GT 值，确定值块位置
2. **锚点发现** — 在值块左侧/上方找标签候选（短文本、含冒号、跨样本一致）
3. **位置推断** — 统计锚点→值的 X/Y 偏移，确定 right / below
4. **规则提取** — 从多个样本的值中推断正则模式（bl_no/date/weight）
5. **自动生成配置** — 输出新版式的 YAML 配置块，合并到 config.yaml

**验证结果**：
- Maersk（2 样本）：11/11 核心锚点与手动配置一致
- COSCO（2 样本）：14 字段，中英混合锚点（"装货港POL"、"卸货港POD"）全部正确发现

本质上还是规则生成器，不需要 GPU 训练。API: `POST /api/fewshot/learn`

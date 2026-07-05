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

## Day 8-9 — 锚点法字段提取

- [ ] 实现 `field_extractor.py`：
  - 锚点关键词列表（Shipper, Consignee, B/L No., POL, POD, Gross Weight, Container No. 等）
  - 模糊匹配（OCR误识别容错）
  - 值定位策略：同行右侧 / 紧邻下方
- [ ] 正则校验：日期、箱号、重量、提单号

**产出**：核心字段提取逻辑

---

## Day 10-11 — 动态 Schema 配置

- [ ] 编写 `config.yaml`：
  - 3种版式的字段映射定义
  - 关键词锚点 + 位置方向 + 正则规则
- [ ] 版式自动识别：统计关键词命中数 → 自动选择版式规则
- [ ] 新增版式只需改 YAML，不改 Python 代码

**产出**：版式自适应机制

---

## Day 12 — 表格结构恢复

- [ ] 对 table 区域进行网格分析
- [ ] 检测表头行 + 数据行
- [ ] 输出表格 JSON：`{"headers": [...], "rows": [[...], ...]}`
- [ ] 多行合并处理

**产出**：货物明细表格提取

---

## Day 13-14 — Flask 后端 API

- [ ] `POST /api/upload` — 文件上传
- [ ] `POST /api/recognize/<id>` — 触发完整流水线
- [ ] `GET /api/result/<id>` — 获取结构化结果
- [ ] `POST /api/correct/<id>` — 人工校正
- [ ] `GET /api/export/<id>` — 导出 Excel/JSON
- [ ] 跨域配置、文件大小限制

**产出**：后端 API 可用 Postman 测试

---

## Day 15-18 — Vue3 前端

- [ ] 创建 Vue3 + Vite 项目
- [ ] 安装 Element Plus + Axios + Fabric.js
- [ ] 上传页面（拖拽上传）
- [ ] 结果展示页：
  - 左侧 Fabric.js Canvas 标注识别位置
  - 右侧 Element Plus 表格展示字段（可编辑）
- [ ] 人工校正 + 导出功能

**产出**：完整前端界面

---

## Day 19-20 — 联调测试

- [ ] 端到端测试：上传 → 识别 → 展示 → 修正 → 导出
- [ ] 3种版式各测10份，统计准确率
- [ ] 错误处理完善

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

# SmartLDS 中期进展汇报

> 方括号里是屏幕共享操作提示。

---

## 1. 题目 & 总体进度（1 分钟）

**[切屏幕到 `temp_paper.docx`，翻到「2. 设计目标与要求」]**

课设题目：**基于 OCR 与版面分析的物流单证智能识别系统**。

论文要求分两层。基础目标四个：数据预处理、OCR 识别、关键信息提取、可视化展示。进阶目标三个：版式自适应、动态 Schema、表格恢复。

目前**基础目标 + 进阶目标全部完成**。后端 pipeline、API、Vue3 前端、Few-shot 自适应、GPU 加速均已就绪。联调测试 16/16 端点通过，全流程可演示。

**[切屏幕到 `TASKS.md`，快速滚一遍让大家看到打勾情况]**

---

## 2. 数据构建（30 秒）

**[切屏幕到 `backend/generate_data.py`，翻到三个 TEMPLATE 定义处]**

论文要求 200 份数据集，覆盖 80% 合成 + 10% 公开 + 10% 真实扫描。

用 Playwright 渲染 HTML 模板生成 PDF，Faker 随机生成公司名、提单号、船名等字段。设计了 **3 种版式**（Maersk 英文提单、COSCO 中英委托书、Simple 简易委托书），各 ~53 份。同步输出 Ground Truth JSON 标注。加上 FUNSD 公开数据集和同学拍的真实快递面单，共 200 份。

---

## 3. OCR & 版面分析

**[切屏幕到 `backend/preprocess.py`，翻到 `_auto_orient_full` 方法]**

OCR 引擎选 PaddleOCR 2.x，封装了单图识别、仅检测（快 15 倍）、批量接口和 PDF 逐页识别。

预处理做了**三段式自动定向**——霍夫角度直方图找主方向（~0.1 秒），失败则 OCR 四方向兜底（~1 秒），最后纠斜细调到 ±0.5°。覆盖 0°~360° 任意旋转。刻意不做二值化——实测发现 PaddleOCR 检测器依赖灰度图梯度信息，二值化反而破坏检测。

**[切屏幕到 `backend/layout_parser.py`，翻到 `_group_into_rows` 和 `_detect_table_rows` 方法]**

### 版面分割原理

OCR 输出的 66 个文本块是散乱的，每个块只有 `(text, x1, y1, x2, y2)`。版面分析要做的就是把它们组织成结构化区域。

**Y 投影法分行**：计算每两个相邻块之间的 Y 间距，取中位数 × 1.8 作为切分阈值。间距超过阈值的就切一刀，分成不同行。同一行内的块 Y 范围有重叠就合并。

比如 "Shipper:" 在 y=287、"Johnson PLC" 在 y=293，Y 差很小 → 同一行。"Port of Loading:" 在 y=397，离上一行间距很大 → 新行开始。

**列对齐检测表格**：一行有 3+ 个块，且连续多行的块在 X 方向对齐（同一列位误差 < 30px）→ 判定为表格区域。比如表头 "Container No."(x=177) 和数据 "MSKU1903064"(x=170) 的 X 中心差 7px < 30 → 同列。

**区域分类**：顶部 18% 高度内的行 → header（Logo、标题）。表格行段 → table。其余 → body。输出 `{header: 2块, body: 21块, table: 43块}`。

---

## 4. 关键信息抽取 KIE（核心部分）

**[切屏幕到 `backend/field_extractor.py`，翻到 `_extract_field` 方法]**

### 4.1 锚点法原理

论文要求"Anchor-based Extraction——定义关键词作为锚点，利用相对位置寻找对应的值"。我把这个过程拆成三步：

**第一步：找锚点。** 遍历所有 OCR 块，检查文本是否包含锚点关键词。比如 `"Shipper"` 这个锚点匹配到 OCR 块 `"Shipper:"` ——子串匹配得分 0.98。同时做模糊匹配——LCS 最长公共子序列算法，容错 OCR 把 "SHIPPER" 误读成 "SHlPPER"。

为了防止误匹配，锚点占文本比例越高分越高。"托运人" 在 "托运人" 里（比例 100%）得分 1.0，在 "托运人信息 / Shipper Information" 里（比例 10%）得分 0.88——优先选短的、精准的标签块。

**标签检测防线 `_looks_like_label()`**：7 条规则防止把标签文本误当值——
1. 冒号结尾（含全角：）+ 较短 → 标签
2. 纯字母+冒号模式 → 标签
3. 已知表头词黑名单 → 标签
4. 纯中文 1-4 字 → 标签
5. 极短缩写（≤5字符）→ 标签
6. 含中文锚点关键词的短文本 → 标签（防 `"订舱号 B/L"` 等 OCR 拆出的中英混合残片）
7. 精确匹配 40+ 已知英文字段标签 → 标签（防 `"SHIPPER"`、`"PORT OF LOADING"` 等无冒号英文标签）

**单位感知校验**：weight 字段拒绝含 "CBM" 的值，volume 字段拒绝含 "KGS" 的值——解决 `total_gross_weight` 抢走 `total_measurement` 值的经典冲突。

**第二步：定位值。** 三级策略依次尝试：

1. **内联提取**：OCR 经常把标签和值合并成一个块，比如 "Vessel: ONE HARBOUR"。找到锚点 "Vessel" 在文本中的位置，取后面的文本，去掉冒号→得到 "ONE HARBOUR"。
2. **同行右侧**：标签和值在不同块但同一行。评分公式 = Y 中心对齐分 × 0.6 + X 邻近分 × 0.4。Y 对齐保证同行，X 邻近保证选最近的右侧块。
3. **紧邻下方**：X 左边界对齐 + Y 间距合理，处理标签在上值在下的布局。

**第三步：正则清洗。** 提单号提取 `[A-Z]{2,4}\d{6,10}` 模式；日期提取 `dd/mm/yyyy`；重量去 KGS 后缀；签发地分离 "地点, 日期" 合并文本。

一个具体例子——提取 `shipper` 字段：

```
输入 OCR 块：
  " Shipper:"      rect=( 86, 287, 218, 337)    ← 锚点匹配！
  "Johnson PLC"    rect=(360, 293, 535, 327)    ← 同行右侧，Y 差 7px
  "BL10398483"     rect=(1101, 290, 1270, 332)   ← 也在右侧但 X 距离 906px

评分：
  "Johnson PLC": Y分 0.86 × 0.6 = 0.52  +  X分 0.55 × 0.4 = 0.22  = 总分 0.74
  "BL10398483":   Y分 0.84 × 0.6 = 0.50  +  X分 0    × 0.4 = 0     = 总分 0.50

→ "Johnson PLC" 胜出 ✓
```

**[切屏幕到 `backend/config.yaml`，翻到 `output_schema` 段]**

### 4.2 动态 Schema（自包含版式结构）

论文要求"通过配置文件定义不同的字段提取规则，而不需要修改核心代码"。**最新架构已重构为每个版式自包含**——keywords、fields、output 全部定义在模板内部，不再用分离的全局 `fields`/`field_labels`/`output_schema` section：

```yaml
templates:
  maersk_style:
    keywords: [MAERSK, BILL OF LADING, ...]
    has_table: true
    fields:
      shipper:
        label: 托运人
        anchors: [Shipper, SHIPPER, 托运人]
        position: right
      bl_no:
        label: 提单号
        anchors: [B/L No., 提单号, B/L]
        position: either
        validator: bl_no
      ...
    output: [shipper, consignee, ..., issue_date]  # 15 字段

  customs_declaration:
    keywords: [海关进口货物报关单, 数量及单位]
    has_table: false
    fields:
      customs_no: {label: 海关编号, anchors: [海关编号], position: right}
      declare_date: {label: 申报日期, anchors: [申报日期], position: right}
      ...
    output: [customs_no, declare_date, ...]  # 7 字段
```

只有 `validators`（正则规则）和 `field_defaults` 是全局的。每个版式独立管理自己的字段定义，不互相污染。unknown 模板不会列出其他版式的无关字段。旧格式配置文件首次加载时自动内存迁移。

**[切屏幕到 `backend/field_extractor.py`，翻到 `_extract_table` 和 `_detect_columns` 方法]**

### 4.3 表格结构恢复

论文要求"能够识别货物明细表格，按行列输出结构化 JSON"。这里的表格指的是提单上的**货物明细表**——列出每件货物的箱号、封号、数量、包装、描述、重量、体积。

**输入**：版面分析输出的 43 个散乱 OCR 块，每个只有坐标+文本：

```
y=665 x=583  "Qty"              ← 表头
y=676 x= 94  "No."              ← 表头
y=668 x=1236 "Gross"            ← 表头（Gross Weight 的上半行）
y=700 x=1231 "Weight"           ← 表头（Gross Weight 的下半行）
y=764 x=116  "1"                ← 货物 1 的序号
y=759 x=170  "MSKU1903064"      ← 货物 1 的箱号
y=756 x=441  "SL-"              ← 货物 1 的封号（上半截）
y=788 x=389  "KH9TLMZB"         ← 货物 1 的封号（下半截）
y=754 x=843  "ADAPTIVE SCALABLE"← 货物 1 的描述（第 1 行）
y=790 x=853  "ENCRYPTION /"     ← 货物 1 的描述（第 2 行）
y=820 x=850  "PROGRAM"          ← 货物 1 的描述（第 3 行）
...还有货物的第二行、汇总行...
```

这些块的位置乱序，数据跨行拆分。算法分四步处理：

1. **Y 聚类分行**：把 Y 坐标接近的块归到同一物理行 → 共 9 行
2. **列检测**：表头行 9 个块按 X 排序，间距大的分列。"Gross"(y=668) 和 "Weight"(y=700) 的 X 中心差 5px < 列宽一半 → 合并为 "Gross Weight" 列 → 最终 8 列
3. **块→列分配**：每个数据块按 X 中心距离归入最近的列。"SL-"(x=441) 和 "KH9TLMZB"(x=389) 都归入 "Seal No." 列
4. **行分类+合并**：header 行 → data 行(满列) → continuation 行(列数不足，拼到上行) → summary 行(含 Total/Freight，过滤)

**输出**：`{headers: [8列], rows: [2行]}`

```
headers: ["No.","Container No.","Seal No.","Qty","Package",
          "Description of Goods","Gross Weight","Measurement"]

Row 1: ["1","MSKU1903064","SL- KH9TLMZB","129","CARTONS",
        "ADAPTIVE SCALABLE ENCRYPTION / PROGRAM","25224 KGS","47.03 CBM"]
Row 2: ["2","OOLU9449966","SL- 1UNWVZCF","19","DRUMS",
        "MULTI-LAYERED USER- FACING CUSTOMER LOYALTY","15840 KGS","44.44 CBM"]
```

封号 "SL-" + "KH9TLMZB" 跨两行拼成了一个值；描述 "ADAPTIVE SCALABLE" + "ENCRYPTION /" + "PROGRAM" 跨三行拼成了一段完整文本。

---

### 4.4 Few-shot 版式自适应

**[切屏幕到 `backend/fewshot.py`，翻到 `learn` 方法]**

论文进阶要求"通过少量样本适应新模板"。实现思路是**反向工程**：

```
现有流程: 锚点 → 找值
Few-shot:  已知 GT 值 → OCR 块中定位 → 找最近的标签 → 提取锚点 → 推断位置
```

算法分五步：
1. **值定位** — 在所有 OCR 块中模糊匹配 GT 值
2. **锚点发现** — 在值块左侧/上方找标签候选（短文本、含冒号、跨样本一致）。**新增内联标签提取**：当 OCR 把标签+值合并为一块（如 `申报日期：2024/11/04`），直接从内部提取标签。**新增 GT 值惩罚**：候选块若包含其他字段的 GT 值（如 `海关编号：CUS29603543` 含 customs_no 的值），扣分排除
3. **位置推断** — 统计锚点→值的 X/Y 偏移，确定 right / below
4. **规则提取** — 从 2~5 个样本值中自动归纳正则
5. **生成 YAML** — 输出自包含版式配置（模板关键词 + 嵌套字段定义 + 输出列表）

前端支持批量拖入 PDF+JSON 文件按文件名自动配对、自定义版式命名。

**验证结果**：

| 版式 | 样本数 | 锚点准确率 | 说明 |
|------|:------:|:------:|------|
| Maersk | 2 | 11/11 | bl_no, date 自动归纳 |
| COSCO | 2 | 14/14 | bl_no, date 自动归纳 |
| 报关单 | 3 | 8/8 | 含内联标签修复后的结果 |

本质是规则生成器，不需要训练。API: `POST /api/fewshot/learn` + `POST /api/config/apply`。

---

## 5. 后端 API（30 秒）

**[切屏幕到 `backend/app.py`，翻到路由定义处]**

Flask 后端，**14 个端点**串联完整流水线：

```
单文件: 上传 → 预处理 → OCR → 版面 → KIE → JSON
批量:   ZIP/多文件 → 并行识别（GPU 0.28s/份）
高级:   Few-shot 学习 / 版式配置查询 / 历史记录
```

支持人工校正回传、Excel/JSON 导出。CORS 已开。

---

## 6. 批量测试结果（1 分钟）

**[切屏幕到 `batch_output/report.pdf`，翻页展示]**

70 份样本的批量测试（50 合成 + 10 FUNSD + 10 真实扫描）：

| 版式 | 样本 | 总字段 | 准确率 |
|------|:----:|:------:|--------|
| Maersk | 17 | 243 | **97.5%** |
| COSCO | 17 | 243 | **97.5%** |
| Simple | 16 | 132 | **99.2%** |
| **合成总计** | **50** | **618** | **97.9%** |

FUNSD（10 份）和真实扫描件（10 份）已配置独立字段 Schema（收件人/运单号/订单号等），用于验证 OCR 和预处理的跨领域适应能力。

**[演示 Vue3 前端：上传文件 → 拖拽批量 → 新标签页查看结果]**

Vue3 + Element Plus SPA：拖拽上传 + ZIP/多文件批量处理 + 字段编辑 + 货物表格 + 识别历史 + 版式管理 + 未识别版式引导 Few-shot 学习。

---

## 7. 不足之处 & 改进方向（30 秒）

- **剩余 2% 错误全部是 OCR 字面误读**：中文字符偏差、O/0 混淆（`NINGB0` → `NINGBO`）、尾字符杂音。三版式锚点匹配和值定位本身工作正常，97.9% 已是纯规则方案的天花板。再提升需要更好的 OCR 模型或 LLM 后处理纠正。

- ✅ **版式自适应目前是关键词投票**，现已实现 Few-shot 版式自适应模块（`fewshot.py`）。论文进阶要求"通过少量样本适应新模板"：给 2~5 份标注好的新版式 PDF → 自动发现锚点关键词、位置规律、**校验规则（含正则自动归纳）** → 生成完整 YAML 配置块。实测用 2 份 Maersk 样本，11/11 核心锚点与手动配置一致；用 2 份报关单样本，自动归纳出 `[A-Z]{2}[0-9]{12}` 等正则。本质上是规则生成器，不需要训练。

- **真实拍照 OCR 质量差**：手机实拍的中文识别乱码严重，锚点法难以奏效。这是 PaddleOCR 的固有限制，不是提取逻辑问题。

- ✅ **GPU 加速已实现**：RTX 4060 + paddlepaddle-gpu 2.6.2，OCR 从 2.5s/份 → 0.28s/份，9x 提速。

---

## 8. 后续计划（15 秒）

- **Day 21 收尾**：清理代码、编写 README.md、课程设计报告
- **论文加分项**：SROIE 公开数据集对比实验、多页文档关联、任意角度倾斜处理

---

## 9. 最新工程修复与风险认知（答辩补充）

本轮对项目做了一次工程体检，并优先完成了两类修复：**安全/数据一致性** 和 **识别流程收敛**。

### 9.1 已完成的稳定性修复

- **ZIP 上传安全**：原先直接使用 `extractall()` 解压，存在路径穿越和压缩炸弹风险。现在改为逐个成员校验，只释放允许的 PDF/图片文件，并限制 ZIP 成员数量和解压后总大小。
- **任务 ID 与路径安全**：新增 `job_id` 格式校验，所有任务目录都通过统一 `job_dir()` 解析，防止异常 ID 写入或删除非预期目录。
- **结果持久化恢复**：新增从磁盘恢复 job 的逻辑。服务重启后，仍可通过 `result.json`、`blocks.json`、`corrections.json`、`original.*` 恢复结果、图片、导出和人工校正能力。
- **人工校正一致性**：校正值现在会合并回字段结果，前端重新加载后不会“看起来又变回旧值”；Excel/JSON 导出也会带上校正结果。
- **单张/批量识别统一流程**：批量识别现在复用单张识别的 pipeline，统一保存 `result.json` 和 `blocks.json`，避免两套逻辑长期分叉。
- **多页 PDF 明示限制**：目前仍只处理第一页，但会在 `meta` 中记录 `page_count`、`processed_page` 和 warning，避免静默丢页。
- **前端部署配置**：前端 API 地址从硬编码 `http://localhost:5000/api` 改为默认相对 `/api`，并支持 `VITE_API_BASE_URL`。

### 9.2 FUNSD 与手写识别效果差的原因

FUNSD 和真实手写样本效果差，并不是单纯因为 PaddleOCR “不行”，而是数据域和系统假设不一致：

- 当前主流程是**物流单证固定字段抽取**：先找 `Shipper / Consignee / B/L No.` 这类锚点，再取右侧或下方的值。
- FUNSD 是**通用表单理解数据集**，每张表的字段名和布局差异很大，核心任务更接近 `question-answer linking`，不是固定字段 Schema。
- 手写样本属于另一个识别域。PaddleOCR 默认通用印刷体模型对清晰打印件较好，但对连笔、倾斜、压线、低清扫描的手写内容不稳定。

因此后续若要提升 FUNSD，应单独实现 **FUNSD 模式**：输出动态 question-answer pairs，而不是强行套物流字段。若要提升手写，应考虑接入专门的手写 OCR/HTR 模型，或将手写样本作为 OCR 展示能力而非结构化字段准确率评估对象。

### 9.3 最新验证

- Python 编译检查通过：`python -m compileall -q backend run.py test.py`
- 前端生产构建通过：`npm.cmd run build`
- 安全接口轻测通过：非法 `job_id` 返回 400；包含 `../evil.pdf` 的恶意 ZIP 返回 400
- 前端仍有 Vite 大包警告，JS 约 1MB，属于后续性能优化项

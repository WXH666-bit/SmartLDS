# SmartLDS - 物流单证智能识别系统

SmartLDS 是一个基于 OCR、版面分析和锚点规则的物流单证识别系统。它可以把 PDF、图片或批量 ZIP 中的单证转换成结构化字段和表格数据，并支持人工校正、导出、Few-shot 学习、结果反哺和可选 AI 增强。

项目定位很明确：**本地 OCR + 规则抽取是主流程，AI 只做增强或兜底**。Few-shot 新模板和反哺模板不使用关键词识别，必须保持 `keywords: []`，并使用 `detection.mode: anchor_layout` 的页面锚点布局签名。

## 项目亮点

- **本地规则主识别**：PaddleOCR 输出文本和坐标，后续由版面分析、锚点匹配和值定位完成结构化抽取。
- **Few-shot 版式学习**：用户提供少量 PDF+JSON 样本即可生成新模板，不依赖预设业务关键词。
- **反哺学习闭环**：用户校正字段或表格后，系统可学习锚点偏移、表头、表格区域和版式布局。
- **表格恢复**：支持物流货物明细表抽取，也支持手动新增、编辑、清空和反哺。
- **JSON 结构优化**：Few-shot 训练时可在内存中优化真实扫描 JSON，不修改原始 JSON 文件。
- **作用域锚点**：对 `发货方 SHIPPER 名称`、`收货方 CONSIGNEE 名称` 这类重复小锚点，用 `scope_anchors` 区分归属区域。
- **AI 增强可选**：支持通义千问、OpenAI、自定义 OpenAI-compatible 和 Ollama；超时或失败时保留普通识别结果。
- **工程硬化**：安全 ZIP 解压、`job_id` 校验、磁盘恢复、单文件/批量 pipeline 统一、前端相对 API 路径。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+ 与 npm
- Windows 已验证；Linux/macOS 理论可用但未作为主要环境测试
- GPU 可选：NVIDIA GPU + CUDA/cuDNN，可显著提升 PaddleOCR 速度

### 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install -r backend\requirements.txt

cd frontend
npm install
cd ..
```

PaddleOCR 建议继续使用 2.x 系列。当前项目在 PaddleOCR 2.x + PaddlePaddle 2.x 路线下验证较多。

### 启动

```powershell
python run.py
```

或者分开启动：

```powershell
cd backend
python app.py
```

```powershell
cd frontend
npm.cmd run dev
```

默认前端访问地址为 `http://localhost:8080`，后端健康检查为 `http://localhost:5000/api/health`。

## 功能概览

| 功能 | 状态 |
|------|------|
| PDF/图片上传 | 已支持 |
| ZIP/多文件批量识别 | 已支持，包含安全解压限制 |
| OCR 识别 | 已支持 PaddleOCR |
| 版面分析 | 已支持 header/body/table 区域划分 |
| 字段抽取 | 已支持锚点法、多策略值定位、正则清洗 |
| 表格抽取 | 已支持物流货物明细表恢复 |
| 人工校正 | 已支持字段名、字段值、手动字段、表格编辑 |
| JSON/Excel 导出 | 已支持 |
| 识别历史 | 已支持，服务重启后可恢复 |
| Few-shot 学习 | 已支持 PDF+JSON 样本学习 |
| 结果反哺模板 | 已支持字段、表头、布局和表格反哺 |
| AI 增强 | 已支持，可选、失败安全 |
| 模型设置 | 已支持 provider/API key/model/timeout |
| 日志/警告反馈 | 已支持轻量用户可见提示 |

## 当前识别流程

```text
PDF / 图片 / ZIP
    |
    v
preprocess.py
    自动方向判断、纠斜、CLAHE
    |
    v
ocr_engine.py
    PaddleOCR 文本块、坐标、置信度
    |
    v
layout_parser.py
    行分组、区域划分、表格候选
    |
    v
field_extractor.py
    模板识别、字段抽取、表格恢复
    |
    v
vision_fallback.py
    可选 AI 兜底或增强
    |
    v
app.py
    保存结果、校正、导出、反哺
    |
    v
Vue3 前端
```

## 核心模块

| 文件 | 说明 |
|------|------|
| `backend/app.py` | Flask API、上传、识别、校正、导出、历史、配置应用、模型设置 |
| `backend/ocr_engine.py` | PaddleOCR 封装 |
| `backend/preprocess.py` | 方向检测、纠斜、图像增强 |
| `backend/layout_parser.py` | OCR 块分行、区域划分、表格候选 |
| `backend/field_extractor.py` | 锚点抽取、表格恢复、模板检测、作用域锚点 |
| `backend/fewshot.py` | Few-shot 学习、JSON 优化、YAML 生成 |
| `backend/template_signature.py` | `anchor_layout` 版式签名生成与匹配 |
| `backend/vision_fallback.py` | 视觉模型兜底、AI 增强 |
| `backend/config.yaml` | 自包含模板配置 |
| `frontend/src/App.vue` | 主前端界面 |
| `frontend/src/resultState.js` | 结果页字段、表格、JSON 预览状态辅助 |
| `frontend/src/api/index.js` | 前端 API wrapper |

## Few-shot 与反哺原则

Few-shot 和反哺是当前项目的重点能力。这里有一条硬规则：

```yaml
keywords: []
detection:
  mode: "anchor_layout"
```

新增模板、反哺模板和 AI 增强模板都不能退回关键词识别。模板识别应依赖样本中稳定出现的 OCR 文本、锚点坐标、字段锚点和页面布局结构。

Few-shot 学习过程：

1. 用户提供 PDF/图片和对应 JSON。
2. 系统 OCR 出文本块和坐标。
3. 在 OCR blocks 中定位 GT 值。
4. 从值块附近反推字段锚点。
5. 统计锚点和值的相对位置。
6. 生成字段配置、表格配置和页面布局签名。
7. 应用到 `backend/config.yaml`。

反哺流程：

1. 用户在结果页修正字段或表格。
2. 系统保存最终结果。
3. 如果字段值能在 OCR blocks 中找到，则学习 `learned_value_offset`。
4. 如果包含表格，则学习表头、列坐标、表格区域和噪声过滤规则。
5. 更新已有模板或创建新模板。

## JSON 结构优化

Few-shot 面板默认开启 JSON 结构优化。它只改变训练时传入学习器的数据形态，不修改用户原始 JSON 文件。

优化目标：

- 去掉 `source_scan`、`filled_fields` 等元数据干扰。
- 从真实扫描 JSON 中提取有效字段和表格。
- 去掉空列、占位列和无效表格值。
- 对重复小锚点字段加入作用域。

例子：

```json
{
  "发货方 SHIPPER 名称": "张三",
  "收货方 CONSIGNEE 名称": "李四"
}
```

训练时会转换成：

```json
{
  "发货方 SHIPPER 名称": {
    "value": "张三",
    "anchor": "名称",
    "scope_anchor": "发货方 SHIPPER"
  },
  "收货方 CONSIGNEE 名称": {
    "value": "李四",
    "anchor": "名称",
    "scope_anchor": "收货方 CONSIGNEE"
  }
}
```

这样前端和导出仍保留完整字段名，抽取时则能区分两个 `名称`。

## 表格能力

当前表格抽取主要面向物流货物明细表。系统会根据表头、列坐标、行坐标和连续区域恢复结构。

表格人工编辑支持：

- 新增表格
- 新增列
- 新增行
- 修改单元格
- 从 OCR 块复制/填入文本
- 清空表格
- 保存表格校正
- 反哺学习表格布局

表格反哺不只是保存用户输入的单元格文本，还会尽量学习坐标区域和列结构。真实快递面单场景中，系统会过滤表格区域外的 `备注NOTES`、`支付方式:到付` 等页脚噪声。

## AI 增强与模型设置

AI 增强是可选能力。系统默认先跑本地规则，只有用户启用或低置信度场景才使用模型。

支持 provider：

| Provider | 协议 | API Key |
|----------|------|---------|
| 通义千问 | OpenAI-compatible | 需要 |
| OpenAI | OpenAI API | 需要 |
| Custom | OpenAI-compatible | 按服务配置 |
| Ollama | 原生 `/api/chat` | 不需要 |

前端可配置：

- provider
- base URL
- API key
- model
- response timeout

AI 失败策略：

- 超时不终止识别。
- 返回非法 JSON 不终止识别。
- 未配置 key 不终止识别。
- AI 不得删除本地规则已有可靠字段。
- AI 不得把 Few-shot 模板改回关键词识别。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传单文件 |
| `POST` | `/api/upload/zip` | 上传 ZIP 批量文件 |
| `POST` | `/api/recognize/<job_id>` | 触发识别 |
| `POST` | `/api/recognize/batch` | 批量识别 |
| `GET` | `/api/result/<job_id>` | 获取识别结果 |
| `POST` | `/api/correct/<job_id>` | 保存人工校正 |
| `GET` | `/api/export/<job_id>` | 导出 JSON/XLSX |
| `GET` | `/api/image/<job_id>` | 获取原图或渲染图 |
| `GET` | `/api/config` | 获取模板配置 |
| `POST` | `/api/config/apply` | 应用 Few-shot 模板 |
| `DELETE` | `/api/config/<name>` | 删除模板 |
| `POST` | `/api/fewshot/learn` | Few-shot 学习 |
| `POST` | `/api/fewshot/from-result` | 从当前结果反哺模板 |
| `GET` | `/api/history` | 获取识别历史 |
| `DELETE` | `/api/history/<job_id>` | 删除单条历史 |
| `DELETE` | `/api/history` | 清空历史 |
| `GET/POST/DELETE` | `/api/vision-settings` | 模型设置 |
| `POST` | `/api/vision-settings/probe` | 探测可用模型 |
| `GET` | `/api/health` | 健康检查 |

## 数据集

项目数据位于 `dataset/`，包含合成单证、公开数据、真实扫描和 Few-shot 样本。根目录 `dataset/manifest.json` 记录索引。

```text
dataset/
  synthetic_bol/
  public_funsd/
  real_scans/
    express/
    food_delivery/
  fewshot_samples/
    customs_declaration/
    warehouse_receipt/
  manifest.json
```

近期真实样本回放：

- `dataset/real_scans/express/bol_188.pdf` 到 `bol_192.pdf` 可学习真实快递面单字段。
- JSON 优化后可区分发货方/收货方的名称、电话、地址。
- 表头可保持为 `序号 / 品名名称 / 数量`。

## 测试与验证

常用后端检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\fewshot.py backend\field_extractor.py backend\app.py
```

Few-shot 相关测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_field_extractor_enhanced.py -k fewshot
```

表格布局学习测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_field_extractor_enhanced.py -k learned_table_layout
```

人工校正与反哺测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_manual_result_feedback.py
```

前端状态检查：

```powershell
node tests\frontend_result_state_check.mjs
```

前端构建：

```powershell
npm.cmd --prefix .\frontend run build
```

注意：完整 `test_field_extractor_enhanced.py` 可能依赖本地 `backend/config.yaml` 中是否存在可选 learned template，例如 `bol_201_learned`。如果缺少 fixture 模板，可能出现配置缺失类失败，不一定代表核心代码回归。

## 目录结构

```text
SmartLDS/
  backend/
    app.py
    ocr_engine.py
    preprocess.py
    layout_parser.py
    field_extractor.py
    fewshot.py
    template_signature.py
    vision_fallback.py
    config.yaml
  frontend/
    src/
      App.vue
      resultState.js
      api/index.js
  dataset/
  tests/
  uploads/
  run.py
  README.md
  final_report.md
```

## 已知限制

- 多页 PDF 当前只处理第一页，但会在 `meta` 中记录页数和 warning。
- PaddleOCR 对手写、低清、严重倾斜或压线扫描件仍不稳定。
- FUNSD 更接近通用表单 question-answer linking，不完全适合物流固定字段 Schema。
- 前端生产构建存在 Vite 大 chunk warning，属于性能优化项。
- 本地 Ollama 模型速度和质量取决于用户电脑或服务器算力。
- 通用网格表仍更适合 AI 兜底或后续 generic form 模式，当前本地表格算法主要面向物流货物明细。

## 当前结论

SmartLDS 当前已经具备完整演示和工程闭环能力：能上传识别、能校正导出、能学习新模板、能反哺字段和表格、能配置 AI 增强，也能在 AI 失败时保持本地规则结果稳定。

最重要的维护边界：

- Few-shot 和反哺永远不要使用关键词模板。
- 新模板必须保持 `keywords: []` 和 `anchor_layout`。
- AI 只能增强，不能破坏本地规则结果。
- 原始 JSON 不应被训练优化过程修改。
- 用户校正结果必须进入展示、保存、导出和反哺闭环。

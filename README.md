# SmartLDS — 物流单证智能识别系统

> 基于 OCR + 版面分析 + 锚点法 KIE 的物流单证关键信息抽取系统。
> 上传 PDF / 图片 → 自动版式识别 → 字段提取 → 人工校正 → 导出 JSON / Excel。

**课程设计项目** ｜ Python · PaddleOCR · Flask · Vue3

---

## 项目亮点

- **不依赖大模型做主识别**：PaddleOCR + 规则匹配，离线可跑，单份 0.28s（GPU）/ 2.5s（CPU）。
- **几何驱动的版式自适应**：Few-shot 学习产出 anchor-layout 签名（归一化坐标 + 文本相似度），新文档靠几何匹配定位字段，不依赖预设关键词词表。
- **三级值定位 + 统一候选评分**：内联 / 右侧 / 下方 / 学习偏移四种策略统一打分（锚点分 + 几何分 + OCR 置信度 + 校验分 - 冲突惩罚），选最优而非第一个可用。
- **反馈学习闭环**：用户校正字段后，自动反查 OCR 块坐标，学习锚点→值偏移量写回模板，下次识别优先使用。
- **视觉大模型兜底（可选）**：本地规则识别低置信度时，自动调用通义千问 / OpenAI / 自定义 OpenAI-compatible / Ollama 原生协议做兜底，不污染主流程。
- **工程硬化**：安全 ZIP 解压、`job_id` 路径校验、磁盘恢复、单文件/批量 pipeline 统一、per-provider 视觉设置持久化。

---

## 快速开始

### 前置要求

- Python 3.10+（在 Windows 上验证；Linux/macOS 理论可用但未测）
- Node.js 18+ 与 npm
- GPU 可选：NVIDIA GPU + CUDA 11.8 + cuDNN 8.9（CPU 也能跑，慢约 9 倍）

### 安装

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
source .venv/Scripts/activate     # Windows Git Bash
# .venv\Scripts\activate           # Windows CMD / PowerShell

# 2. 安装后端依赖
pip install -r backend/requirements.txt

# 3. 安装前端依赖
cd frontend && npm install && cd ..

# 4. （可选）GPU 加速：安装 paddlepaddle-gpu 后，
#    手动拷贝 NVIDIA DLL 到 .venv/Lib/site-packages/paddle/libs/
```

> **关于 PaddleOCR 版本**：锁定 `paddleocr<3` + `paddlepaddle<3`。PaddleOCR 3.x 在 Windows 上有 ONEDNN/PIR 推理 bug，2.10 + Paddle 2.6 已验证稳定。

### 启动

```bash
# 一键启动（后端 :5000 + 前端 :8080）
python run.py

# 或分开启动
cd backend && python app.py          # 后端
cd frontend && npm run dev           # 前端
```

打开浏览器访问 **http://localhost:8080**，后端健康检查 **http://localhost:5000/api/health**。

---

## 功能

### 核心流程

| 环节 | 说明 |
|------|------|
| 上传 | PDF / PNG / JPG 单文件，或 ZIP 批量上传（安全解压：路径校验 + 300 文件上限 + 256MB 上限） |
| 识别 | 版式检测 → OCR → 版面分析 → 字段提取 → 质量评分 → 低置信度时视觉兜底 |
| 校正 | 人工改字段值、新增字段、排除字段、覆盖标签、替换表格 |
| 导出 | JSON / XLSX，三种预设：`values`（简洁键值）/ `details`（完整明细）/ `combined`（默认） |

### 版式支持

| 版式 | 字段数 | 表格 | 来源 | 状态 |
|------|------|------|------|------|
| Maersk 英文提单 | 14 | ✅ 货物明细表 | 合成数据 | 启用 |
| COSCO 中英委托书 | 12 | — | 合成数据 | 启用 |
| Simple 简易委托书 | 11 | — | 合成数据 | 启用 |
| 报关单 | 7 | — | Few-shot 学习 | 按需学习 |
| 入库单 | 6 | — | Few-shot 学习 | 按需学习 |
| FUNSD 通用表单 | 5 | — | 公开数据集 | 隐藏（仅跨域验证） |
| 真实扫描面单 | 10 | — | 真实扫描 | 隐藏（仅跨域验证） |

> FUNSD 与真实扫描模板默认 `enabled: false, hidden: true`，不作为活跃提取目标。未知版式通过 Few-shot 学习动态接入。

### 进阶特性

- **Few-shot 版式学习** — 拖入 2~5 份 PDF + 标注 JSON，自动发现锚点、位置策略、校验规则，生成 anchor-layout 签名 + YAML 配置，一键应用到 `config.yaml`。
- **视觉大模型兜底** — 4 个 provider 独立配置：通义千问（阿里云百炼）/ OpenAI / 自定义 OpenAI-compatible / Ollama 原生 `/api/chat`。Ollama 走原生协议（`images` + `format:json` + `num_ctx`），无需 API Key。
- **OCR 反馈学习** — 校正字段值后自动学习锚点中心→值块中心偏移量 `(dx, dy)`，持久化进模板。
- **AI 版式增强** — Few-shot 学习 / 结果反哺时可选调用视觉模型，建议更优锚点、`value_pattern`、表头配置。
- **识别历史** — 列出所有完成任务，支持逐条删除 / 一键清空，重启后可从磁盘恢复。

---

## 系统架构

```
PDF/图片
    │
    ▼
preprocess.py        三段式自动定向 (0°~360°) → 纠斜 ±0.5° → CLAHE（不二值化）
    │
    ▼
ocr_engine.py        PaddleOCR 2.x  detect_only(15x) + 归一化坐标 + 批量接口
    │                 GPU 0.28s/份 | CPU 2.5s/份
    ▼
layout_parser.py     Y 投影分行 + 列对齐检测表格 → header/body/table
    │
    ▼
field_extractor.py   锚点法 KIE：内联/右侧/下方/学习偏移 四策略
    │                 统一候选评分 + 多行合并 + 正则清洗 + 版式识别
    │                       ↑
    │                 config.yaml (自包含版式配置)
    │                 template_signature.py (anchor-layout 签名)
    ▼
vision_fallback.py   低置信度时视觉大模型兜底（可选，失败不回退）
    │
    ▼
Flask API  →  Vue3 前端 (Element Plus)
```

### Pipeline 模块职责

| 模块 | 职责 |
|------|------|
| `preprocess.py` | 三段式自动定向 → 纠斜 → CLAHE；不做二值化/去噪（保留梯度信息） |
| `ocr_engine.py` | 封装 PaddleOCR，`detect_only` 15x 加速、归一化坐标、批量接口 |
| `layout_parser.py` | Y 投影分行 + 列对齐检测表格，分割 header/body/table |
| `field_extractor.py` | 锚点法字段提取：三级值定位 + 统一候选评分 + 多行合并 + 正则清洗 |
| `template_signature.py` | Few-shot 产出的几何签名：归一化坐标 + 文本相似度匹配 |
| `fewshot.py` | 从 1~5 份标注样本自动发现锚点 + 位置 + 校验规则，生成 YAML |
| `vision_fallback.py` | 多供应商视觉兜底 + 模型探测 + AI 版式增强 |
| `config.yaml` | 每版式自包含（keywords/detection + fields + output），仅 validators 全局共享 |

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传单文件 |
| POST | `/api/upload/zip` | ZIP 批量上传（安全解压） |
| POST | `/api/recognize/<id>` | 触发识别 |
| POST | `/api/recognize/batch` | 批量识别 |
| GET | `/api/result/<id>` | 获取结果（含校正） |
| POST | `/api/correct/<id>` | 人工校正（fields / manual_fields / excluded_fields / table_patch） |
| GET | `/api/export/<id>` | 导出 JSON/XLSX（`preset=values\|details\|combined`） |
| GET | `/api/image/<id>` | 获取原始图片（PDF→PNG 渲染） |
| GET | `/api/config` | 版式列表（可视化友好） |
| DELETE | `/api/config/<name>` | 删除版式 |
| POST | `/api/config/apply` | 应用 Few-shot 学习产出的配置 |
| POST | `/api/fewshot/learn` | Few-shot 模板学习（1~5 份 PDF+GT） |
| POST | `/api/fewshot/from-result` | 当前结果反哺为新模板 |
| GET | `/api/history` | 识别历史列表 |
| DELETE | `/api/history/<id>` | 删除单条历史 |
| DELETE | `/api/history` | 清空全部历史 |
| GET / POST / DELETE | `/api/vision-settings` | 视觉模型设置（GET 掩码 key） |
| POST | `/api/vision-settings/probe` | 探测可用模型列表 |
| GET | `/api/vision-settings/api-key` | 按供应商+模型查看已保存 key 明文 |
| GET | `/api/jobs` | 内存中任务列表 |
| GET | `/api/health` | 健康检查 |

---

## 配置

### 视觉模型设置

在前端「模型设置」面板配置，持久化到 `backend/vision_settings.json`（per-provider profiles）：

| Provider | 协议 | 默认端点 | API Key |
|----------|------|---------|---------|
| `qwen` | OpenAI-compatible | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 必需 |
| `openai` | Responses API | `https://api.openai.com` | 必需 |
| `custom` | OpenAI-compatible | `http://localhost:9000/v1` | 必需 |
| `ollama` | 原生 `/api/chat` + `/api/tags` | `http://localhost:11434` | 不需要 |

切换 provider 不丢配置；每个 provider 的不同模型可各自保存 API Key。旧版扁平配置文件首次加载时自动迁移到 profiles 结构。

### 版式配置（`backend/config.yaml`）

每个模板自包含：`keywords` / `detection`（anchor_layout 签名）+ `fields` + `output`。字段 key 用文档原始显示名（如 `"B/L No."`），`canonical_key` 保留内部标识。新增字段属性（`multi_line` / `value_pattern` / `allow_shared` / `search_in`）需同步贯穿：config.yaml → `field_extractor.py` → `fewshot.py` → `app.py`。

---

## 测试

```bash
source .venv/Scripts/activate

# 批量测试（200 份数据集，生成报告 PDF/HTML）
cd tests && python batch_test.py

# 字段提取增强测试
cd tests && python test_field_extractor_enhanced.py

# 视觉兜底 + 设置测试
cd tests && python test_vision_fallback.py
cd tests && python test_vision_settings.py

# 前端状态机测试（Node）
cd tests && node frontend_result_state_check.mjs

# 后端编译检查
.venv/Scripts/python.exe -m compileall -q backend run.py

# 前端生产构建
cd frontend && npm run build
```

---

## 数据集

`dataset/` 按版式 + 来源组织，共 210 份，根 `manifest.json` 记录全量索引：

```
dataset/
├── synthetic_bol/            # 合成数据 (160 份)
│   ├── maersk_style/         #   Maersk 英文提单
│   ├── cosco_style/          #   COSCO 中英委托书
│   └── simple_style/         #   Simple 简易委托书
├── public_funsd/             # FUNSD 公开数据 (20 份)
│   ├── coupon_registration/
│   ├── retail_progress_report/
│   └── challenge_singletons/
├── real_scans/               # 真实扫描 (20 份)
│   ├── food_delivery/        #   外卖配送单
│   └── express/              #   快递面单
├── fewshot_samples/          # Few-shot 样本 (10 份)
│   ├── customs_declaration/  #   报关单
│   └── warehouse_receipt/    #   入库单
└── manifest.json
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| OCR | PaddleOCR 2.10 + PaddlePaddle GPU 2.6.2（CUDA 11.8 + cuDNN 8.9） |
| 后端 | Python 3.10+ · Flask · Flask-CORS · PyYAML · openpyxl · PyMuPDF |
| 前端 | Vue 3 · Element Plus · Axios · Vite 8 |
| 视觉模型 | 通义千问 / OpenAI / 自定义 / Ollama（可选，兜底用） |
| 数据生成 | Playwright（Chromium 渲染合成 PDF）· Faker |
| PDF | PyMuPDF (fitz) 解析 · Playwright 生成 |

---

## 目录结构

```
SmartLDS/
├── backend/                   # Python 后端
│   ├── app.py                 #   Flask API（路由、校正、导出、视觉设置、pipeline）
│   ├── ocr_engine.py          #   PaddleOCR 封装
│   ├── preprocess.py          #   图像预处理
│   ├── layout_parser.py       #   版面分析
│   ├── field_extractor.py     #   锚点法字段提取
│   ├── fewshot.py             #   Few-shot 版式学习
│   ├── template_signature.py  #   Anchor-layout 版式签名
│   ├── vision_fallback.py     #   视觉大模型兜底
│   ├── config.yaml            #   版式配置（自包含结构）
│   ├── vision_settings.json   #   视觉模型设置（per-provider profiles）
│   ├── generate_data.py       #   合成数据生成
│   └── gen_new_templates.py   #   未知版式生成
├── frontend/                  # Vue3 前端
│   └── src/
│       ├── App.vue            #   主组件（上传/识别/校正/导出/设置）
│       └── api/index.js       #   API 客户端
├── dataset/                   # 测试数据集（210 份）
├── tests/                     # 测试脚本
├── run.py                     # 一键启动
└── README.md
```

---

## 设计决策摘要

- **不用大模型做主识别**：PaddleOCR + 规则匹配，不训练 Donut/LayoutLMv3。视觉大模型仅在低置信度时兜底。
- **坐标优先**：所有提取基于 bbox 坐标，不依赖文本顺序。
- **预处理不二值化**：PaddleOCR 检测器需要自然灰度图的梯度信息，二值化反而破坏检测。CLAHE 提升置信度约 5pp。
- **先硬后软**：先死磕一种版式 100%，再通过 YAML 适配多版式。
- **Playwright 替代 weasyprint**：Windows 兼容，不需要 GTK3，输出质量更好。

---

## 已知限制

- **多页 PDF 仅处理第 1 页**：`meta.page_count` / `meta.processed_page` / warnings 会显式标注此限制。
- **手写识别不是强项**：PaddleOCR 默认通用印刷体模型适合清晰打印件；手写、连笔、低清扫描属于不同 OCR/HTR 任务。
- **前端 chunk 较大**：生产构建有 ~1MB JS chunk 警告，性能优化待跟进，非正确性问题。

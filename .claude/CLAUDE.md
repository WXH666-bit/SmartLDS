# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

物流单证智能识别系统 — 基于 OCR 与版面分析，从 PDF/图片中提取物流单证的关键字段（Shipper、B/L No.、Gross Weight 等），输出结构化 JSON。Python + PaddleOCR + Flask 后端，Vue3 前端（待建），课程设计项目。

## Common Commands

```bash
# 激活虚拟环境
source .venv/Scripts/activate

# 运行 OCR 测试（当前进度验证点）
python test.py

# 生成合成数据（160份，bol_001~160）
cd backend && python generate_data.py

# 转换 FUNSD 公开数据（20份，bol_161~180）
cd public_data && python convert_funsd.py

# 转换真实扫描数据（20份，bol_181~200）
cd real_data && python convert_real.py

# 运行 Flask 后端
cd backend && python app.py
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
| 字段提取 | `field_extractor.py` | 锚点法：匹配标签→定位值，正则校验（待实现） |
| 配置 | `config.yaml` | 每种版式独立定义锚点、位置方向、正则规则（待实现） |

### OCR Engine API

| 方法 | 作用 | 速度 |
|------|------|------|
| `recognize_image(img, normalize=False)` | 检测+识别 | ~3.8s |
| `detect_only(img)` | 仅检测出文本框坐标 | ~0.26s |
| `recognize_images([img1, img2])` | 批量识别 | N×3.8s |
| `recognize_pdf(path)` | PDF 逐页识别 | 同上 |
| `detect_pdf(path)` | PDF 逐页检测 | 逐页 0.26s |

### Preprocessing Pipeline

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

KIE 模块根据 `template` 字段自动选择对应的 anchor 配置。

## Key Design Decisions

- **不用大模型**：PaddleOCR + 规则匹配，不训练 Donut/LayoutLMv3
- **坐标优先**：所有提取基于 bbox 坐标 (x1,y1,x2,y2)，不依赖文本顺序
- **先硬后软**：先死磕一种版式 100%，再通过 YAML 适配多版式
- **Playwright 替代 weasyprint**：Windows 兼容，不需要 GTK3，输出质量更好
- **PaddleOCR 2.x**：PaddleOCR 3.x 在 Windows 上有 ONEDNN/PIR 推理 bug，已降到 2.10 + Paddle 2.6 解决。`requirements.txt` 约束 `<3`
- **预处理不做二值化/去噪**：PaddleOCR 检测器需要自然灰度图的梯度信息，二值化反而破坏检测。实测 CLAHE 提升置信度 ~5pp
- Playwright Chromium 已安装在 `C:\Users\18246\AppData\Local\ms-playwright\`

## Progress

- ✅ Day 1-2: 环境搭建、合成数据生成器、200份数据集
- ✅ Day 3: OCR 引擎封装，合成+真实三版式验证通过
- ✅ Day 4: 图像预处理，纠斜+CLAHE，移除二值化/去噪，批量验证通过
- ✅ Day 5-6: OCR 引擎完善，detect_only(15x加速)、坐标归一化、三段式自动定向
- ✅ Day 7: 版面分析，Y投影分行+列对齐检测表格，三版式验证通过
- ⏳ Day 8-21: 待实现，详见 `TASKS.md`
- 详细设计见 `.claude/plans/composed-conjuring-eich.md`

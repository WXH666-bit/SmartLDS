# Few-shot Anchor Layout Signature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 2-5 份任意陌生版式样本自动学习字段锚点和版式特征，彻底取消 Few-shot 对预设关键词/标签白名单的依赖，并修复双栏字段串位。

**Architecture:** 保留 `temp_paper.docx` 中 OCR 坐标、Anchor-based Extraction、相对位置、规则引擎和动态 Schema 作为本地识别主干；在其上增加“锚点布局签名”，由样本自身的稳定文本和归一化坐标生成。视觉兜底、AI 增强、反哺、自定义模型和多表格能力继续作为增强层，不参与本地 Few-shot 版式识别的硬依赖。

**Tech Stack:** Python、PaddleOCR 现有封装、Flask、YAML、Vue 3、Element Plus、Python `unittest`。

## Global Constraints

- 新学习型版式不得读取任何预设物流关键词、中文标签白名单或品牌词表。
- 版式判断必须以 OCR 文本、bbox 坐标和 2-5 份样本的跨样本稳定性为依据。
- AI 增强可以补充字段建议，但 AI 失败或关闭时本地 Few-shot 必须完整可用。
- 旧内置 Maersk/COSCO 等模板暂时保留原关键词匹配，避免破坏已验证行为。
- Few-shot 和反哺“新建版式”统一使用新签名；反哺“合并已有版式”保持兼容。
- 不改 PaddleOCR 表格算法、视觉兜底表格输出、自定义模型和导出逻辑。

---

## Root Cause

- `FewShotLearner._extract_template_keywords()` 依赖硬编码物流词表；陌生文档无法命中时返回文档中不存在的 `DOCUMENT`。
- `FewShotLearner._discover_anchor()` 调用了 `_looks_like_label()`，而其中预设列表包含“毛重”却没有“净重”。真实 `bol_201` 中，算法因此把 `net_weight` 错绑到较远的“毛重”。
- 学习结果只保存 `keywords[]`，没有保存锚点坐标关系；运行时只能按文本命中版式，无法利用 Few-shot 已经拥有的布局信息。
- AI 增强还能向 Few-shot 结果追加 `template_keywords`，会再次把学习型版式带回关键词依赖。

## Target Schema

学习型模板新增 `detection`，保留空的 `keywords: []` 仅用于旧接口兼容：

```yaml
source: fewshot
keywords: []
detection:
  mode: anchor_layout
  min_score: 0.55
  min_matches: 2
  features:
    - text: 净重
      x: 0.525
      y: 0.186
      weight: 1.0
      role: field_anchor
    - text: 中华人民共和国海关进口货物报关单
      x: 0.500
      y: 0.032
      weight: 1.4
      role: stable_text
```

- `x/y` 为 OCR 块中心点除以页面宽高后的归一化坐标。
- `field_anchor` 来自字段值附近、跨样本一致的标签。
- `stable_text` 来自全部样本共有的固定文本；GT 值块、动态值及其组合必须排除。
- 签名匹配同时计算文本相似度和坐标距离，并保证一个 OCR 块不能重复匹配多个特征。

---

### Task 1: Geometry-only Anchor Learning

**Files:**
- Modify: `backend/fewshot.py`
- Test: `tests/test_field_extractor_enhanced.py`

**Interfaces:**
- Produce: `_discover_anchor_candidates(blocks, value_block, excluded_block_ids, image_size) -> list[dict]`
- Produce: `_select_consistent_anchor(observations, required_samples) -> dict | None`

- [ ] 写失败测试，使用与真实 `bol_201` 相同的双栏坐标，断言 `net_weight -> 净重`、`receiver -> 收货单位`。
- [ ] 运行定向测试，确认当前实现分别错误绑定到“毛重”和“经营单位”。
- [ ] 候选锚点评分仅使用同行重叠、水平距离、上下关系和跨样本支持度，不调用 `_looks_like_label()`。
- [ ] 显式排除所有已定位 GT 值块，避免公司名、金额、重量成为锚点。
- [ ] 2 份样本要求 2/2 支持；3-5 份样本允许一个 OCR 漏检，但主锚点支持率必须不低于 75%。
- [ ] 同一主锚点默认只能分配给一个字段；只有多个 GT 值在所有样本中确实位于同一 OCR 块时才允许共享。
- [ ] 运行定向测试并确认 12 个字段都使用原文标签，`net_weight` 不再作为显示字段名。

### Task 2: Sample-derived Anchor Layout Signature

**Files:**
- Create: `backend/template_signature.py`
- Modify: `backend/fewshot.py`
- Test: `tests/test_field_extractor_enhanced.py`

**Interfaces:**
- Produce: `build_anchor_layout_signature(sample_blocks, field_observations, image_sizes) -> dict`
- Produce: `score_anchor_layout_signature(detection, blocks, image_size) -> dict`

- [ ] 写失败测试：标题和字段名全部使用系统从未见过的文本，学习结果必须为 `keywords == []`，且生成 `detection.mode == anchor_layout`。
- [ ] 从已选字段锚点生成 `field_anchor` 特征，聚合同一锚点在各样本中的中位数归一化坐标。
- [ ] 从样本 OCR 交集生成少量 `stable_text`，排除 GT 值、组合值、纯数字、过短文本和位置漂移文本。
- [ ] 删除 Few-shot 的硬编码 `candidate_words` 和 `DOCUMENT` 回退；模板名优先使用样本 JSON 中一致的 `template` 值，否则返回 `new_template`。
- [ ] 签名评分使用文本相似度、坐标接近度、匹配覆盖率和唯一块约束；错误布局即使文本相同也不能通过。
- [ ] 运行陌生版式测试，确认不调用 AI、不命中任何预设词也能识别模板。

### Task 3: Runtime Detection and Legacy Compatibility

**Files:**
- Modify: `backend/field_extractor.py`
- Test: `tests/test_field_extractor_enhanced.py`

**Interfaces:**
- Change: `_detect_template(blocks, image_size=None) -> str`
- Preserve: 无 `detection` 的旧模板继续使用 `keywords[]`。

- [ ] 写失败测试：空关键词 + 有签名的学习模板可识别；同文本错误布局返回 `unknown`。
- [ ] 在 `_detect_template()` 中优先评估 `detection.mode == anchor_layout` 的模板，并在 debug 中记录匹配特征、签名得分和布局得分。
- [ ] 对旧模板保留现有关键词评分和阈值，不修改内置版式提取结果。
- [ ] 学习模板与旧模板同时命中时按归一化总分和分差选择；分差不足继续返回 `unknown`，不强行套版式。
- [ ] 回归 Maersk、FUNSD、物流表格及未知模板测试。

### Task 4: Persist Signature Through Few-shot, Feedback and AI Enhancement

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/vision_fallback.py`
- Test: `tests/test_manual_result_feedback.py`

**Interfaces:**
- `/api/fewshot/learn` result adds `detection` and returns `keywords: []` for learned templates.
- `/api/config/apply` accepts and persists `source` and `detection`.
- `/api/config` returns `source` and `detection` summary.

- [ ] 写失败测试，确认 Few-shot 应用后 YAML 完整保留 `detection.features`。
- [ ] `_generate_yaml()`、`_regenerate_fewshot_yaml()` 和 `/api/config/apply` 透传签名结构并校验字段类型、坐标范围和最少特征数。
- [ ] AI Few-shot 增强不再接收或合并 `template_keywords`；AI 仅可补充已选字段锚点、位置、正则和表头建议。
- [ ] 反哺“新建版式”从当前 OCR 块、字段锚点和坐标生成单样本初始签名，并标记低样本置信度；后续反哺继续累计特征。
- [ ] 反哺“合并已有版式”不覆盖已有正确签名，只在新证据与当前布局一致时更新位置中位数。
- [ ] 保留旧 API 的 `keywords` 字段，避免前后端和历史配置直接报错。

### Task 5: UI Terminology and Current Template Migration

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `backend/config.yaml`
- Test: `tests/frontend_result_state_check.mjs`

**Interfaces:**
- Few-shot 结果由“X 个关键词”改为“X 个版式特征”。
- 版式管理对学习模板展示“锚点布局识别”，旧模板仍展示“兼容关键词”。

- [ ] 写前端静态检查，确认 Few-shot 应用请求包含 `detection`，学习结果不再展示关键词计数。
- [ ] 更新 Few-shot 结果和版式管理文案，不增加新的复杂配置操作。
- [ ] 将当前 `bol_201_learned` 修正为 12 个原文字段：`净重 -> 3853 KG`、`收货单位 -> 中商国际贸易公司`，并写入从真实 OCR 坐标生成的签名。
- [ ] 不修改视觉兜底、JSON 高亮、模型设置、多表格和导出界面。
- [ ] 构建前端并检查结果页字段标签和值。

### Task 6: End-to-end Verification

**Files:**
- Test: `tests/test_field_extractor_enhanced.py`
- Test: `tests/test_manual_result_feedback.py`
- Test: `tests/frontend_result_state_check.mjs`

- [ ] 使用真实 `uploads/d7d7fea7480c/blocks.json` 回放 `bol_201`，断言模板识别不依赖关键词。
- [ ] 断言 12 个字段全部提取，`毛重=4292 KG`、`净重=3853 KG`、经营/收货单位不串位。
- [ ] 构造完全陌生中文、英文及混合语言版式，验证 2-5 样本均可学习。
- [ ] 构造文本相同但布局不同的负样本，确认不会误套模板。
- [ ] 运行 `.venv\Scripts\python.exe -m unittest discover tests -p "test*.py"`。
- [ ] 运行 `node tests\frontend_result_state_check.mjs` 和 `npm.cmd run build`。

## Acceptance Criteria

- Few-shot 代码中不存在物流品牌、单证名称或中文字段标签候选词表。
- 任意陌生版式只要 2-5 份样本的标签与布局稳定，就能生成并匹配模板。
- 当前截图中的 `net_weight=4292 KG` 和“收货单位=经营单位”两个错误消失。
- AI 关闭、API 不可用和 Ollama 未安装时，本地 Few-shot 仍正常工作。
- 现有内置模板、视觉兜底、反哺、JSON/Excel 导出和多表格行为无回归。

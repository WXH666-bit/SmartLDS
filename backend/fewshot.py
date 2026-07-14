"""
Few-shot 版式自适应 — 给定 1~5 份新版式 PDF + GT JSON，自动生成 config.yaml 配置片段

核心思路：已知 GT 值 → 在 OCR 块中定位 → 找最近的标签块 → 提取锚点关键词 → 推断位置策略

用法:
    learner = FewShotLearner()
    yaml_text = learner.learn(pdf_paths, gt_jsons)
    # → 输出可直接合并到 config.yaml 的 YAML 文本
"""

import re
import os
from difflib import SequenceMatcher
from collections import Counter

from ocr_engine import OCREngine
from field_extractor import FieldExtractor, _looks_like_label
from layout_parser import LayoutParser


class FewShotLearner:
    """Few-shot 版式学习器 — 从少量样本中自动提取 KIE 规则"""

    def __init__(self):
        self.engine = OCREngine()
        self.parser = LayoutParser()
        self.extractor = FieldExtractor()

    # ================================================================
    # 主入口
    # ================================================================

    def learn(self, samples):
        """
        从样本中学习版式配置

        :param samples: [(pdf_path, gt_dict), ...]  1~5 份样本
        :return: dict {
            "template_name": "xxx_style",
            "keywords": ["KEY1", "KEY2", ...],
            "fields": { field_name: {anchors, position, validator, ...}, ... },
            "yaml_text": "...",
        }
        """
        if not samples:
            return {"error": "至少需要 1 份样本"}

        # Step 0: 对每份样本跑 OCR
        all_data = []
        for pdf_path, gt in samples:
            ocr_result = self.engine.recognize_pdf(pdf_path)[0]
            blocks = ocr_result["blocks"]
            all_data.append({
                "blocks": blocks,
                "gt": gt,
                "img_size": ocr_result["image_size"],
            })

        # Step 1: 收集所有 GT 字段名（仅顶层标量字段，排除表格数据/货物明细）
        _CARGO_FIELDS = {
            "container", "seal", "qty", "pkg", "package", "description", "desc",
            "gross", "weight", "measurement", "cbm", "marks", "no", "item",
        }
        all_field_names = set()
        for d in all_data:
            for key, val in d["gt"].items():
                if key in ("template", "source", "category", "platform", "items", "field_details", "ocr_blocks"):
                    continue
                if isinstance(val, (list, dict)):
                    continue
                # 跳过货物明细字段（命名带数字如 container1, seal2, qty1）
                base_name = key.rstrip("0123456789_")
                if base_name in _CARGO_FIELDS:
                    continue
                if isinstance(val, str) and len(val) >= 2:
                    all_field_names.add(key)

        # Step 2: 对每个字段，在每份样本中定位值 → 发现锚点
        fields_config = {}
        for fname in all_field_names:
            anchors_per_sample = []
            positions_per_sample = []

            for d in all_data:
                gt_val = str(d["gt"].get(fname, "")).strip()
                if not gt_val:
                    continue

                # 定位值块
                value_block = self._locate_value(d["blocks"], gt_val)
                if not value_block:
                    continue

                # 发现锚点（传入 GT 用于排除其他字段的值块）
                anchor_result = self._discover_anchor(d["blocks"], value_block, fname, d.get("gt", {}))
                if anchor_result:
                    anchors_per_sample.append(anchor_result["anchor_text"])
                    positions_per_sample.append(anchor_result["position"])

            if not anchors_per_sample:
                continue  # 所有样本中都没找到该字段

            # 选最频繁的锚点文本
            anchor_counter = Counter(anchors_per_sample)
            best_anchor = anchor_counter.most_common(1)[0][0]

            # 选最频繁的位置策略
            pos_counter = Counter(positions_per_sample)
            best_position = pos_counter.most_common(1)[0][0]

            # 收集所有样本的值用于推断 validator
            values = []
            for d in all_data:
                v = str(d["gt"].get(fname, "")).strip()
                if v:
                    values.append(v)
            v_result = self._infer_validator(fname, values)

            fields_config[fname] = {
                "anchors": [best_anchor],
                "position": best_position,
            }
            if v_result:
                v_name, v_pattern = v_result
                fields_config[fname]["validator"] = v_name
                fields_config[fname]["validator_pattern"] = v_pattern

        # Step 3: 提取版式关键词
        all_text = " ".join(b["text"] for d in all_data for b in d["blocks"])
        keywords = self._extract_template_keywords(all_text)

        # Step 4: 生成版式名
        template_name = self._generate_template_name(keywords, all_text)

        # Step 5: 生成 YAML
        yaml_text = self._generate_yaml(template_name, keywords, fields_config)

        return {
            "template_name": template_name,
            "keywords": keywords,
            "fields": fields_config,
            "yaml_text": yaml_text,
        }

    # ================================================================
    # 值定位
    # ================================================================

    def _locate_value(self, blocks, gt_value):
        """在所有 OCR 块中定位 GT 值"""
        gt_upper = gt_value.upper().strip().replace(",", "")

        best_block = None
        best_score = 0.0

        for block in blocks:
            text_upper = block["text"].upper().strip().replace(",", "")
            if not text_upper:
                continue

            # 完全匹配
            if text_upper == gt_upper:
                return block

            # 包含匹配
            if gt_upper in text_upper or text_upper in gt_upper:
                score = min(len(text_upper), len(gt_upper)) / max(len(text_upper), len(gt_upper))
                if score > best_score:
                    best_score = score
                    best_block = block

            # 模糊匹配（OCR 偏差）
            sim = SequenceMatcher(None, text_upper, gt_upper).ratio()
            if sim > 0.75 and sim > best_score:
                best_score = sim
                best_block = block

        return best_block if best_score > 0.6 else None

    # ================================================================
    # 锚点发现
    # ================================================================

    def _discover_anchor(self, blocks, value_block, field_name, gt=None):
        """在值块附近找最可能的标签块"""
        vx1, vy1, vx2, vy2 = value_block["rect"]
        value_cy = (vy1 + vy2) / 2

        # 收集其他字段的 GT 值（用于排除值块伪装成锚点）
        other_values = set()
        if gt:
            for k, v in gt.items():
                if k != field_name and isinstance(v, str) and len(v) >= 2:
                    other_values.add(v.strip())

        # 优先从值块内部提取标签（处理 标签+值 合并块，如 "申报日期：2024/11/04"）
        inline_anchor = self._extract_inline_label(value_block["text"].strip())
        if inline_anchor:
            return {
                "anchor_text": self._normalize_anchor(inline_anchor),
                "position": "right",
                "score": 0.95,
            }

        candidates = []

        for block in blocks:
            if id(block) == id(value_block):
                continue

            text = block["text"].strip()
            if not text or len(text) > 40:
                continue

            # 拒绝纯数字、纯箱号（像值不像标签）
            if re.match(r'^[\d\s.,]+$', text):
                continue
            if re.match(r'^[A-Z]{4}\d{6,10}$', text.upper()):
                continue  # 集装箱号
            if re.match(r'^SL-', text.upper()):
                continue  # 封号前缀

            bx1, by1, bx2, by2 = block["rect"]

            # 必须在值块的左侧
            if bx2 > vx1 + 10:
                continue

            # Y 必须与值块有重叠（同行）或在紧邻上方
            if not (by1 <= vy2 + 20 and by2 >= vy1 - 20):
                continue

            # 评分
            y_overlap = min(by2, vy2) - max(by1, vy1)
            y_score = max(0, y_overlap / max(by2 - by1, vy2 - vy1, 1))

            x_gap = vx1 - bx2
            x_score = max(0, 1 - x_gap / 300)

            label_score = 0.2 if _looks_like_label(text) else 0
            # 惩罚纯数字、超短文本（可能是值而非标签）
            if re.match(r'^\d+$', text):
                label_score -= 0.15
            # 惩罚包含其他字段 GT 值的块（防止 "海关编号：CUS29603543" 被当锚点）
            if other_values:
                for ov in other_values:
                    if len(ov) >= 3 and ov in text:
                        label_score -= 0.3
                        break

            score = y_score * 0.45 + x_score * 0.35 + label_score
            if score > 0.35:
                candidates.append((block, score))

        if not candidates:
            # 没找到同行左侧的，试试上方
            for block in blocks:
                if id(block) == id(value_block):
                    continue
                text = block["text"].strip()
                if not text or len(text) > 40:
                    continue
                bx1, by1, bx2, by2 = block["rect"]
                if by2 > vy1 + 5:
                    continue
                if abs(bx1 - vx1) > 150:
                    continue
                score = 0.3 + (0.3 if _looks_like_label(text) else 0)
                if score > 0.35:
                    candidates.append((block, score))

        if not candidates:
            return None

        best = max(candidates, key=lambda x: x[1])
        anchor_block = best[0]
        anchor_text = self._normalize_anchor(anchor_block["text"].strip())

        # 判断位置策略
        anchor_cy = (anchor_block["rect"][1] + anchor_block["rect"][3]) / 2
        if abs(anchor_cy - value_cy) < max(
            anchor_block["rect"][3] - anchor_block["rect"][1],
            value_block["rect"][3] - value_block["rect"][1]
        ):
            position = "right"
        else:
            position = "below"

        return {
            "anchor_text": anchor_text,
            "position": position,
            "score": best[1],
        }

    @staticmethod
    def _extract_inline_label(text):
        """
        从 标签+值 合并块中提取标签部分

        例如: "申报日期：2024/11/04" → "申报日期"
              "海关编号：CUS29603543" → "海关编号"
              "Shipping Date: 2024/11/04" → "Shipping Date"
        """
        text = text.strip()
        # 找冒号位置（半角或全角）
        for sep in ('：', ':'):
            idx = text.find(sep)
            if idx > 0:
                prefix = text[:idx].strip()
                suffix = text[idx + 1:].strip()
                # 前缀像标签（较短、不全是值格式）
                if prefix and suffix and len(prefix) < 25:
                    # 前缀不能是纯数字或看起来像值
                    if not re.match(r'^[\d\s.,/-]+$', prefix):
                        # 后缀应该像值（含数字、字母、或中文公司名等实际内容）
                        if len(suffix) >= 2:
                            return prefix
                break
        return None

    @staticmethod
    def _normalize_anchor(text):
        """标准化锚点文本 — 去掉冒号、保留核心关键词"""
        text = text.strip()
        # 去掉末尾冒号
        if text.endswith(":") or text.endswith("："):
            text = text[:-1].strip()
        return text

    # ================================================================
    # Validator 推断
    # ================================================================

    def _infer_validator(self, field_name, values):
        """
        从样本值中自动推断校验规则 + 提取正则模式
        返回 (validator_name, pattern_str) 或 None
        """
        if not values or len(values) < 1:
            return None

        # B/L 号格式
        if all(re.match(r'^[A-Z]{2,4}\d{6,10}$', v.upper().replace(" ", ""))
               for v in values):
            return ("bl_no", r"[A-Z]{2,4}\d{6,10}")

        # 日期格式
        if all(re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', v.strip())
               for v in values):
            return ("date", r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")

        # 重量（含 KGS/KG）
        if field_name in ("total_gross_weight", "gross_weight", "weight", "gw"):
            if any("KGS" in v.upper() or "KG" in v.upper() for v in values):
                return ("weight", r"[\d,]+\\.?\\d*")

        # 体积（含 CBM）
        if field_name in ("total_measurement", "measurement", "cbm", "volume"):
            if any("CBM" in v.upper() for v in values):
                return ("volume", r"[\d,]+\\.?\\d*")

        # 从样本值自动归纳正则模式
        pattern = self._extract_pattern(values)
        if pattern:
            vname = f"auto_{field_name}"
            return (vname, pattern)

        return None

    def _extract_pattern(self, values):
        """从 2~5 个样本值自动归纳正则表达式"""
        if len(values) < 2:
            return None

        purified = [v.strip() for v in values if v.strip()]
        if len(purified) < 2:
            return None

        # 找到所有值的共同结构
        sets = [list(v) for v in purified]
        min_len = min(len(s) for s in sets)

        pattern_parts = []
        for i in range(min_len):
            chars_at_i = {s[i] for s in sets}
            if len(chars_at_i) == 1:
                # 所有值在同一位置相同 → 字面量
                ch = chars_at_i.pop()
                pattern_parts.append(re.escape(ch))
            else:
                if all(c.isalpha() and c.isupper() for c in chars_at_i):
                    pattern_parts.append("[A-Z]")
                elif all(c.isalpha() and c.islower() for c in chars_at_i):
                    pattern_parts.append("[a-z]")
                elif all(c.isalpha() for c in chars_at_i):
                    pattern_parts.append("[A-Za-z]")
                elif all(c.isdigit() for c in chars_at_i):
                    pattern_parts.append("\\d")
                elif all(c in "-/" for c in chars_at_i):
                    pattern_parts.append("[/-]")
                else:
                    pattern_parts.append("[A-Za-z\\d]")

        # 处理长度差异：尾部加通配
        if any(len(s) > min_len for s in sets):
            pattern_parts.append(".*")

        if len(pattern_parts) >= 4:  # 至少 4 个 pattern 元素才有意义
            return "^" + "".join(pattern_parts) + "$"
        return None

    # ================================================================
    # 版式关键词提取
    # ================================================================

    def _extract_template_keywords(self, all_text):
        """从 OCR 文本中提取版式识别关键词"""
        text_upper = all_text.upper()
        keywords = []

        # 常见物流单证关键词（按优先级）
        candidate_words = [
            "MAERSK", "COSCO", "BILL OF LADING", "SHIPPING ORDER",
            "BOOKING NOTE", "SEA WAYBILL", "DHL", "FEDEX", "UPS",
            "EXPRESS", "出口货物", "委托书", "海运提单",
            "装货单", "快递单", "面单", "WAYBILL",
        ]

        for kw in candidate_words:
            if kw.upper() in text_upper:
                keywords.append(kw)

        # 找独有公司名/品牌名（大号字体块）
        # 这里取 top 5 最长的大写词作为候选
        words = [w for w in text_upper.split() if len(w) > 3 and w.isalpha()]
        word_counts = Counter(words)
        for word, count in word_counts.most_common(10):
            if count >= 2 and word not in [k.upper() for k in keywords]:
                if len(word) >= 5:
                    keywords.append(word)
                    if len(keywords) >= 5:
                        break

        return keywords[:5] if keywords else ["DOCUMENT"]

    # ================================================================
    # 生成
    # ================================================================

    def _generate_template_name(self, keywords, all_text):
        """根据关键词生成版式名"""
        name_hints = {
            "MAERSK": "maersk", "COSCO": "cosco",
            "DHL": "dhl", "FEDEX": "fedex", "UPS": "ups",
            "BILL OF LADING": "bol", "SHIPPING ORDER": "shipping_order",
            "BOOKING NOTE": "booking_note", "EXPRESS": "express",
        }
        for kw, hint in sorted(name_hints.items(), key=lambda x: -len(x[0])):
            if kw.upper() in all_text.upper():
                return f"{hint}_learned"
        return "new_template"

    def _generate_yaml(self, template_name, keywords, fields_config):
        """生成自包含版式 YAML 配置片段（新格式：字段定义嵌套在模板内）"""
        lines = []
        lines.append(f"    {template_name}:")
        kw_str = ", ".join(f'"{k}"' for k in keywords)
        lines.append(f"      keywords: [{kw_str}]")
        lines.append(f"      has_table: false")
        lines.append(f"      fields:")

        # 收集自动生成的 validator 规则
        auto_validators = {}

        for fname, cfg in fields_config.items():
            lines.append(f"        {fname}:")
            lines.append(f'          label: {fname}')
            anchors_str = ", ".join(f'"{a}"' for a in cfg.get("anchors", []))
            lines.append(f"          anchors: [{anchors_str}]")
            lines.append(f"          position: {cfg.get('position', 'right')}")
            validator = cfg.get("validator")
            if validator:
                lines.append(f"          validator: {validator}")
                vpattern = cfg.get("validator_pattern")
                if vpattern and validator.startswith("auto_"):
                    auto_validators[validator] = {
                        "description": f"{fname} auto-generated",
                        "pattern": vpattern,
                    }

        # Output list
        field_names = list(fields_config.keys())
        output_str = ", ".join(field_names)
        lines.append(f"      output: [{output_str}]")
        lines.append("")

        # 自动生成的 validators（需手动复制到全局 validators 节）
        if auto_validators:
            lines.append("# === Auto-generated validators (copy to global validators: section) ===")
            lines.append("validators:")
            for vname, vcfg in auto_validators.items():
                lines.append(f"  {vname}:")
                lines.append(f'    description: "{vcfg["description"]}"')
                lines.append(f'    pattern: "{vcfg["pattern"]}"')

        return "\n".join(lines)


# ================================================================
# 便捷函数
# ================================================================

def learn_from_samples(pdf_paths, gt_jsons):
    """便捷接口：从 PDF 路径 + GT JSON 路径列表学习"""
    samples = []
    for pdf_path, gt_path in zip(pdf_paths, gt_jsons):
        import json
        with open(gt_path, "r", encoding="utf-8") as f:
            gt = json.load(f)
        samples.append((pdf_path, gt))
    learner = FewShotLearner()
    return learner.learn(samples)

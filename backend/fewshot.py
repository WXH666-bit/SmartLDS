"""
Few-shot 版式自适应 — 给定 1~5 份新版式 PDF + GT JSON，自动生成 config.yaml 配置片段

核心思路：已知 GT 值 → 在 OCR 块中定位 → 学习字段锚点与归一化坐标 → 形成样本布局签名

用法:
    learner = FewShotLearner()
    yaml_text = learner.learn(pdf_paths, gt_jsons)
    # → 输出可直接合并到 config.yaml 的 YAML 文本
"""

import re
import os
import json
from difflib import SequenceMatcher
from collections import Counter

from ocr_engine import OCREngine
from field_extractor import FieldExtractor
from layout_parser import LayoutParser
from template_signature import build_anchor_layout_signature, normalized_center


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
            "keywords": [],
            "detection": {"mode": "anchor_layout", "features": [...]},
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

        # Step 1: Prepare page-level fields. This keeps ordinary fields on the
        # original path, while explicitly modelling the two common page-level
        # composites that otherwise resemble cargo detail columns.
        all_field_names = []
        field_specs = {}
        for d in all_data:
            d["prepared_fields"] = self._prepare_sample_fields(d["gt"])
            for field_name, spec in d["prepared_fields"].items():
                if field_name not in field_specs:
                    all_field_names.append(field_name)
                    field_specs[field_name] = spec

        located_by_sample = []
        for d in all_data:
            located = {}
            used_located_ids = set()
            for fname, spec in d["prepared_fields"].items():
                block = self._locate_value(
                    d["blocks"],
                    spec["value"],
                    allow_suffix=spec.get("allow_suffix"),
                    used_block_ids=used_located_ids,
                )
                if block:
                    located[fname] = block
                    used_located_ids.add(id(block))
            located_by_sample.append(located)

        excluded_value_ids = [
            {id(block) for block in located.values()}
            for located in located_by_sample
        ]

        # Step 2: 对每个字段，在每份样本中定位值 → 发现锚点
        fields_config = {}
        validators = {}
        used_schema_keys = set()
        used_primary_anchors = set()
        field_anchor_observations = {}
        for fname in all_field_names:
            field_spec = field_specs[fname]
            anchor_observations = []
            positions_per_sample = []
            multiline_hits = 0
            shared_hits = 0
            required_observations = 0

            for sample_idx, d in enumerate(all_data):
                sample_spec = d["prepared_fields"].get(fname)
                if not sample_spec:
                    continue
                gt_val = sample_spec["value"]
                required_observations += 1

                # 定位值块
                value_block = located_by_sample[sample_idx].get(fname)
                if not value_block:
                    continue

                same_block_fields = [
                    other for other, block in located_by_sample[sample_idx].items()
                    if other != fname and id(block) == id(value_block)
                ]
                if same_block_fields:
                    shared_hits += 1
                if self._looks_multiline_value(gt_val, value_block):
                    multiline_hits += 1

                # 发现锚点（传入 GT 用于排除其他字段的值块）
                anchor_result = self._discover_anchor(
                    d["blocks"],
                    value_block,
                    excluded_block_ids=excluded_value_ids[sample_idx],
                    image_size=d["img_size"],
                )
                if anchor_result:
                    anchor_result["sample_idx"] = sample_idx
                    anchor_observations.append(anchor_result)
                    positions_per_sample.append(anchor_result["position"])

            if required_observations != len(all_data):
                continue

            # Composite and suffix-aware fields are intentionally conservative:
            # a single partial sample must never create a new extraction rule.
            if field_spec.get("requires_complete_learning") and len(anchor_observations) != required_observations:
                continue
            if not anchor_observations:
                continue  # 所有样本中都没找到该字段

            selected_observations = self._select_consistent_anchor(
                anchor_observations,
                required_observations,
                used_primary_anchors,
            )
            if not selected_observations:
                continue
            top_anchors = []
            for obs in selected_observations:
                anchor = obs["anchor_text"]
                if anchor not in top_anchors:
                    top_anchors.append(anchor)
            top_anchors = top_anchors[:3]
            used_primary_anchors.add(top_anchors[0])
            field_label = self._display_label_from_anchors(
                top_anchors,
                fname,
                used_labels=used_schema_keys,
            )
            schema_key = self._make_unique_schema_key(field_label, used_schema_keys)
            used_schema_keys.add(schema_key)

            # 选最频繁的位置策略
            pos_counter = Counter(positions_per_sample)
            best_position = pos_counter.most_common(1)[0][0]

            # 收集所有样本的值用于推断 validator
            values = []
            for d in all_data:
                sample_spec = d["prepared_fields"].get(fname)
                if sample_spec:
                    values.append(sample_spec["value"])
            v_result = None if field_spec.get("skip_validator") else self._infer_validator(
                field_spec["canonical_key"], values
            )

            fields_config[schema_key] = {
                "label": field_label,
                "canonical_key": field_spec["canonical_key"],
                "anchors": top_anchors,
                "position": best_position,
            }
            if v_result:
                v_name, v_pattern = v_result
                fields_config[schema_key]["validator"] = v_name
                fields_config[schema_key]["validator_pattern"] = v_pattern
                fields_config[schema_key]["value_pattern"] = v_pattern
                if v_name.startswith("auto_"):
                    validators[v_name] = {
                        "description": f"{field_spec['canonical_key']} auto-generated",
                        "pattern": v_pattern,
                    }
            if multiline_hits:
                fields_config[schema_key]["multi_line"] = True
            if shared_hits and self._should_allow_shared(field_spec["canonical_key"], top_anchors):
                fields_config[schema_key]["allow_shared"] = True

            field_anchor_observations[schema_key] = selected_observations

        # Learned templates are selected by their sample-derived anchor/layout
        # signature, not by a preset logistics vocabulary.
        keywords = []
        detection = build_anchor_layout_signature(
            [d["blocks"] for d in all_data],
            field_anchor_observations,
            [d["img_size"] for d in all_data],
            excluded_block_ids=excluded_value_ids,
        )

        # Step 4: 生成版式名
        template_name = self._generate_template_name(all_data)

        # Step 5: 生成 YAML
        yaml_text = self._generate_yaml(
            template_name,
            keywords,
            fields_config,
            detection=detection,
            source="fewshot",
        )

        return {
            "template_name": template_name,
            "keywords": keywords,
            "fields": fields_config,
            "validators": validators,
            "source": "fewshot",
            "detection": detection,
            "yaml_text": yaml_text,
        }

    @staticmethod
    def _prepare_sample_fields(gt):
        """Return the safe page-level field candidates for one GT payload."""
        # 兼容嵌套 GT（real_scans 风格：{"template":..., "fields":{...}, "tables":[...]}）。
        # 仅把 fields 子 dict 摊到顶层，不改动任何下游 OCR / 锚点 / 评分逻辑；
        # 扁平 GT（无 fields key）走原路径，零影响。
        if isinstance(gt.get("fields"), dict):
            gt = {**gt, **gt["fields"]}
        cargo_fields = {
            "container", "seal", "qty", "pkg", "package", "description", "desc",
            "gross", "weight", "measurement", "cbm", "marks", "no", "item",
        }
        ignored_fields = {"template", "source", "category", "platform", "items", "field_details", "ocr_blocks"}
        prepared = {}

        def as_text(value):
            return str(value).strip() if isinstance(value, str) else ""

        def add(name, value, canonical_key=None, allow_suffix=None, composite=False):
            value = as_text(value)
            if len(value) < 2:
                return
            prepared[name] = {
                "value": value,
                "canonical_key": canonical_key or name,
                "allow_suffix": allow_suffix,
                "requires_complete_learning": bool(composite or allow_suffix),
                # Keep format-specific sample strings from creating a validator
                # that blocks otherwise valid future values.
                "skip_validator": bool(composite or allow_suffix),
            }

        quantity = as_text(gt.get("qty"))
        unit = as_text(gt.get("unit"))
        total_price = as_text(gt.get("total_price"))
        currency = as_text(gt.get("currency"))

        for key, value in gt.items():
            if key in ignored_fields or isinstance(value, (list, dict)):
                continue

            base_name = key.rstrip("0123456789_")
            if key == "qty":
                if quantity and unit:
                    add("quantity_unit", f"{quantity} {unit}", canonical_key="quantity_unit", composite=True)
                continue
            if key == "unit":
                continue
            if key == "total_price":
                if total_price and currency:
                    add("total_price", f"{total_price} {currency}", canonical_key="total_price", composite=True)
                else:
                    add("total_price", total_price, canonical_key="total_price", allow_suffix="currency")
                continue
            if key == "currency" and total_price:
                continue
            if base_name in cargo_fields:
                continue

            suffix_kind = "weight" if key in ("gross_weight", "net_weight") else None
            add(key, value, allow_suffix=suffix_kind)

        return prepared

    @staticmethod
    def _select_consistent_anchor(observations, required_observations, used_anchors=None):
        """Choose one geometrically stable label across every learning sample."""
        if required_observations <= 0 or len(observations) < required_observations:
            return []

        used = {FewShotLearner._normalize_anchor(text) for text in (used_anchors or set())}
        clusters = []
        for observation in observations:
            text = FewShotLearner._normalize_anchor(observation.get("anchor_text", ""))
            center = observation.get("anchor_center")
            if not text or not center or text in used:
                continue
            target = None
            for cluster in clusters:
                text_score = SequenceMatcher(None, text, cluster[0]["anchor_text"]).ratio()
                cx = sum(item["anchor_center"][0] for item in cluster) / len(cluster)
                cy = sum(item["anchor_center"][1] for item in cluster) / len(cluster)
                distance = ((center[0] - cx) ** 2 + (center[1] - cy) ** 2) ** 0.5
                if text_score >= 0.82 and distance <= 0.08:
                    target = cluster
                    break
            if target is None:
                target = []
                clusters.append(target)
            normalized = dict(observation)
            normalized["anchor_text"] = text
            target.append(normalized)

        complete = [
            cluster for cluster in clusters
            if len({item.get("sample_idx") for item in cluster}) == required_observations
        ]
        if not complete:
            return []
        return max(
            complete,
            key=lambda cluster: (
                sum(item.get("score", 0.0) for item in cluster) / len(cluster),
                -len(cluster[0]["anchor_text"]),
            ),
        )

    @staticmethod
    def _display_label_from_anchors(anchors, fallback, used_labels=None):
        """Prefer an unused source-document label discovered near the value."""
        used_labels = {str(label).strip() for label in (used_labels or set())}
        for anchor in anchors or []:
            label = FewShotLearner._normalize_anchor(str(anchor))
            if label and label not in used_labels:
                return label
        fallback = str(fallback).strip()
        if fallback and fallback not in used_labels:
            return fallback
        for anchor in anchors or []:
            label = FewShotLearner._normalize_anchor(str(anchor))
            if label:
                return label
        return fallback

    @staticmethod
    def _make_unique_schema_key(label, used_keys):
        """Use the document label as the per-template field key, with stable de-duping."""
        base = str(label).strip() or "field"
        key = base
        idx = 2
        while key in used_keys:
            key = f"{base}__{idx}"
            idx += 1
        return key

    @staticmethod
    def _should_allow_shared(canonical_key, anchors):
        """Only auto-enable sharing for fields that are commonly printed in one value block."""
        text = " ".join([str(canonical_key)] + [str(a) for a in (anchors or [])]).lower()
        shared_hints = ("date", "place", "issue", "签发", "日期", "地点", "place & date")
        return any(hint in text for hint in shared_hints)

    # ================================================================
    # 值定位
    # ================================================================

    def _locate_value(self, blocks, gt_value, allow_suffix=None, used_block_ids=None):
        """在所有 OCR 块中定位 GT 值"""
        gt_upper = gt_value.upper().strip().replace(",", "")
        used_block_ids = set(used_block_ids or set())

        if allow_suffix:
            suffixes = {
                "weight": ("KG", "KGS", "TON", "TONS"),
                "currency": ("USD", "EUR", "RMB", "CNY", "JPY", "HKD"),
            }.get(allow_suffix, ())
            if not suffixes:
                return None
            suffix_pattern = "|".join(re.escape(suffix) for suffix in suffixes)
            strict_pattern = re.compile(rf"^{re.escape(gt_upper)}\s*(?:{suffix_pattern})$", re.IGNORECASE)
            matches = []
            for block in blocks:
                text_upper = block["text"].upper().strip().replace(",", "")
                if text_upper == gt_upper or strict_pattern.fullmatch(text_upper):
                    matches.append(block)
            return next((block for block in matches if id(block) not in used_block_ids), matches[0] if matches else None)

        best_block = None
        best_score = 0.0

        exact_matches = []
        for block in blocks:
            text_upper = block["text"].upper().strip().replace(",", "")
            if not text_upper:
                continue

            # 完全匹配
            if text_upper == gt_upper:
                exact_matches.append(block)
                continue

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

        if exact_matches:
            return next(
                (block for block in exact_matches if id(block) not in used_block_ids),
                exact_matches[0],
            )
        return best_block if best_score > 0.6 else None

    @staticmethod
    def _looks_multiline_value(gt_value, value_block):
        """粗略判断 GT 值是否可能跨多个 OCR 块/多行。"""
        if "\n" in gt_value:
            return True
        gt_norm = gt_value.upper().replace(",", "").replace(" ", "")
        block_norm = value_block["text"].upper().replace(",", "").replace(" ", "")
        if gt_norm and block_norm and gt_norm not in block_norm and len(gt_norm) > len(block_norm) + 8:
            return True
        return False

    # ================================================================
    # 锚点发现
    # ================================================================

    def _discover_anchor(self, blocks, value_block, excluded_block_ids=None, image_size=None):
        """Find a nearby label using geometry only, without vocabulary priors."""
        vx1, vy1, vx2, vy2 = value_block["rect"]
        value_cy = (vy1 + vy2) / 2
        excluded_block_ids = set(excluded_block_ids or set())
        page_width = max(float((image_size or [vx2 + 1])[0]), 1.0)

        inline_anchor = self._extract_inline_label(value_block["text"].strip())
        if inline_anchor:
            center = normalized_center(value_block, image_size)
            return {
                "anchor_text": self._normalize_anchor(inline_anchor),
                "position": "right",
                "score": 0.95,
                "anchor_rect": value_block["rect"],
                "anchor_center": center,
            }

        candidates = []
        for block in blocks:
            if id(block) == id(value_block) or id(block) in excluded_block_ids:
                continue
            text = block["text"].strip()
            if not text or len(text) > 40:
                continue
            if re.match(r'^[\d\s.,]+$', text):
                continue
            if re.match(r'^[A-Z]{4}\d{6,10}$', text.upper()):
                continue
            if re.match(r'^SL-', text.upper()):
                continue

            bx1, by1, bx2, by2 = block["rect"]
            if bx2 > vx1 + 10:
                continue
            if not (by1 <= vy2 + 20 and by2 >= vy1 - 20):
                continue
            y_overlap = min(by2, vy2) - max(by1, vy1)
            y_score = max(0, y_overlap / max(by2 - by1, vy2 - vy1, 1))
            x_gap = vx1 - bx2
            x_score = max(0, 1 - x_gap / max(page_width * 0.45, 1.0))
            score = y_score * 0.7 + x_score * 0.3
            if score > 0.45:
                candidates.append((block, score))

        if not candidates:
            for block in blocks:
                if id(block) == id(value_block) or id(block) in excluded_block_ids:
                    continue
                text = block["text"].strip()
                if not text or len(text) > 40:
                    continue
                bx1, by1, bx2, by2 = block["rect"]
                if by2 > vy1 + 5:
                    continue
                x_distance = abs(((bx1 + bx2) / 2) - ((vx1 + vx2) / 2))
                y_gap = vy1 - by2
                if x_distance > page_width * 0.12 or y_gap > page_width * 0.12:
                    continue
                score = 0.55 * max(0, 1 - x_distance / max(page_width * 0.12, 1.0))
                score += 0.45 * max(0, 1 - y_gap / max(page_width * 0.12, 1.0))
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
            "anchor_rect": anchor_block["rect"],
            "anchor_center": normalized_center(anchor_block, image_size),
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
        """标准化锚点文本 — 去掉冒号、保留样本中的标签文本"""
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
        if all(re.match(r'^(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4})$', v.strip())
               for v in values):
            return ("date", r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}")

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

        # Text values such as Chinese company names are not a stable character-by-
        # character schema. A generated ASCII regex would reject valid future values.
        if any(any(ord(char) > 127 and char.isalpha() for char in value) for value in purified):
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
    # 生成
    # ================================================================

    def _generate_template_name(self, all_data):
        """Prefer a sample-provided name without inferring document semantics."""
        sample_names = [
            str(data.get("gt", {}).get("template") or "").strip()
            for data in all_data
        ]
        sample_names = [name for name in sample_names if name]
        if sample_names and len(set(sample_names)) == 1:
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", sample_names[0]).strip("_")
            if safe_name:
                return safe_name if safe_name.endswith("_learned") else f"{safe_name}_learned"
        return "new_template"

    def _generate_yaml(
        self,
        template_name,
        keywords,
        fields_config,
        has_table=False,
        table_headers=None,
        detection=None,
        source=None,
    ):
        """生成自包含版式 YAML 配置片段（新格式：字段定义嵌套在模板内）"""
        lines = []
        lines.append(f"    {template_name}:")
        kw_str = ", ".join(f'"{k}"' for k in keywords)
        lines.append(f"      keywords: [{kw_str}]")
        if source:
            lines.append(f"      source: {self._yaml_scalar(source)}")
        if detection:
            lines.append("      detection:")
            lines.append(f"        mode: {self._yaml_scalar(detection.get('mode', 'anchor_layout'))}")
            lines.append(f"        min_score: {float(detection.get('min_score', 0.55))}")
            lines.append(f"        min_matches: {int(detection.get('min_matches', 2))}")
            lines.append("        features:")
            for feature in detection.get("features", []):
                lines.append(f"          - text: {self._yaml_scalar(feature.get('text', ''))}")
                lines.append(f"            x: {float(feature.get('x', 0.0))}")
                lines.append(f"            y: {float(feature.get('y', 0.0))}")
                lines.append(f"            weight: {float(feature.get('weight', 1.0))}")
                lines.append(f"            role: {self._yaml_scalar(feature.get('role', 'field_anchor'))}")
        lines.append(f"      has_table: {'true' if has_table else 'false'}")
        if table_headers:
            headers_str = ", ".join(self._yaml_scalar(header) for header in table_headers)
            lines.append(f"      table_headers: [{headers_str}]")
        lines.append(f"      fields:")

        # 收集自动生成的 validator 规则
        auto_validators = {}

        for fname, cfg in fields_config.items():
            lines.append(f"        {self._yaml_scalar(fname)}:")
            lines.append(f"          label: {self._yaml_scalar(cfg.get('label', fname))}")
            if cfg.get("canonical_key"):
                lines.append(f"          canonical_key: {self._yaml_scalar(cfg['canonical_key'])}")
            anchors_str = ", ".join(self._yaml_scalar(a) for a in cfg.get("anchors", []))
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
            if cfg.get("value_pattern"):
                lines.append(f"          value_pattern: {self._yaml_scalar(cfg['value_pattern'])}")
            if cfg.get("multi_line"):
                lines.append("          multi_line: true")
            if cfg.get("allow_shared"):
                lines.append("          allow_shared: true")

        # Output list
        field_names = list(fields_config.keys())
        output_str = ", ".join(self._yaml_scalar(name) for name in field_names)
        lines.append(f"      output: [{output_str}]")
        lines.append("")

        # 自动生成的 validators；/api/config/apply 会自动合并到全局 validators 节
        if auto_validators:
            lines.append("# === Auto-generated validators (applied into global validators) ===")
            lines.append("validators:")
            for vname, vcfg in auto_validators.items():
                lines.append(f"  {vname}:")
                lines.append(f'    description: "{vcfg["description"]}"')
                lines.append(f'    pattern: "{vcfg["pattern"]}"')

        return "\n".join(lines)

    @staticmethod
    def _yaml_scalar(value):
        """Return a JSON-style quoted scalar, which is also valid YAML."""
        return json.dumps(str(value), ensure_ascii=False)


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

"""Sample-derived template signatures based on OCR text and layout coordinates."""

import math
import re
from difflib import SequenceMatcher
from statistics import median


def normalize_signature_text(text):
    text = str(text or "").strip().lower()
    return re.sub(r"[\s:：,，;；_\-./\\]+", "", text)


def block_rect(block):
    rect = (block or {}).get("rect")
    if isinstance(rect, (list, tuple)) and len(rect) == 4:
        try:
            return [float(value) for value in rect]
        except (TypeError, ValueError):
            return None
    return None


def normalized_center(block, image_size):
    rect = block_rect(block)
    if not rect or not image_size or len(image_size) < 2:
        return None
    width = max(float(image_size[0]), 1.0)
    height = max(float(image_size[1]), 1.0)
    return ((rect[0] + rect[2]) / 2.0 / width, (rect[1] + rect[3]) / 2.0 / height)


def _text_similarity(left, right):
    left_norm = normalize_signature_text(left)
    right_norm = normalize_signature_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    shorter, longer = sorted((left_norm, right_norm), key=len)
    if len(shorter) >= 4 and shorter in longer and len(shorter) / len(longer) >= 0.3:
        return 0.9 + 0.1 * (len(shorter) / len(longer))
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _stable_text_features(sample_blocks, image_sizes, excluded_block_ids, existing_texts):
    if not sample_blocks:
        return []
    first_excluded = excluded_block_ids[0] if excluded_block_ids else set()
    features = []
    seen = {normalize_signature_text(text) for text in existing_texts}

    for block in sample_blocks[0]:
        if id(block) in first_excluded:
            continue
        text = str(block.get("text") or "").strip()
        normalized = normalize_signature_text(text)
        if len(normalized) < 4 or normalized in seen or re.fullmatch(r"[\d.]+", normalized):
            continue
        center = normalized_center(block, image_sizes[0])
        if not center:
            continue

        centers = [center]
        matched = True
        for sample_idx in range(1, len(sample_blocks)):
            best = None
            for candidate in sample_blocks[sample_idx]:
                if id(candidate) in excluded_block_ids[sample_idx]:
                    continue
                candidate_center = normalized_center(candidate, image_sizes[sample_idx])
                if not candidate_center:
                    continue
                similarity = _text_similarity(text, candidate.get("text"))
                distance = math.dist(center, candidate_center)
                if similarity < 0.88 or distance > 0.08:
                    continue
                score = similarity - distance
                if best is None or score > best[0]:
                    best = (score, candidate_center)
            if best is None:
                matched = False
                break
            centers.append(best[1])

        if not matched:
            continue
        seen.add(normalized)
        features.append({
            "text": text,
            "x": round(median(point[0] for point in centers), 4),
            "y": round(median(point[1] for point in centers), 4),
            "weight": 1.4 if len(normalized) >= 8 else 1.0,
            "role": "stable_text",
        })

    features.sort(key=lambda item: (-item["weight"], -len(normalize_signature_text(item["text"]))))
    return features[:6]


def build_anchor_layout_signature(sample_blocks, field_observations, image_sizes, excluded_block_ids=None):
    excluded_block_ids = excluded_block_ids or [set() for _ in sample_blocks]
    features = []
    existing_texts = []

    for observations in field_observations.values():
        points = []
        texts = []
        for observation in observations:
            sample_idx = observation.get("sample_idx")
            rect = observation.get("anchor_rect")
            if sample_idx is None or rect is None or sample_idx >= len(image_sizes):
                continue
            point = normalized_center({"rect": rect}, image_sizes[sample_idx])
            if point:
                points.append(point)
                texts.append(str(observation.get("anchor_text") or "").strip())
        if not points or not texts:
            continue
        text = max(texts, key=lambda value: (texts.count(value), len(value)))
        normalized = normalize_signature_text(text)
        if not normalized or normalized in {normalize_signature_text(item) for item in existing_texts}:
            continue
        existing_texts.append(text)
        features.append({
            "text": text,
            "x": round(median(point[0] for point in points), 4),
            "y": round(median(point[1] for point in points), 4),
            "weight": 1.0,
            "role": "field_anchor",
        })

    features.extend(_stable_text_features(
        sample_blocks,
        image_sizes,
        excluded_block_ids,
        existing_texts,
    ))
    feature_count = len(features)
    return {
        "mode": "anchor_layout",
        "min_score": 0.55,
        "min_matches": max(2, math.ceil(feature_count * 0.35)) if feature_count else 2,
        "features": features,
    }


def score_anchor_layout_signature(detection, blocks, image_size):
    features = detection.get("features") if isinstance(detection, dict) else None
    if not isinstance(features, list) or not features:
        return {"score": 0.0, "matched_count": 0, "features_count": 0, "matched": []}

    used_blocks = set()
    matched = []
    matched_weight = 0.0
    total_weight = sum(max(float(feature.get("weight", 1.0)), 0.1) for feature in features if isinstance(feature, dict))
    quality_weighted = 0.0

    for feature in sorted(features, key=lambda item: float(item.get("weight", 1.0)), reverse=True):
        if not isinstance(feature, dict):
            continue
        text = str(feature.get("text") or "").strip()
        try:
            expected = (float(feature["x"]), float(feature["y"]))
        except (KeyError, TypeError, ValueError):
            continue
        best = None
        for block in blocks or []:
            if id(block) in used_blocks:
                continue
            point = normalized_center(block, image_size)
            if not point:
                continue
            similarity = _text_similarity(text, block.get("text"))
            distance = math.dist(expected, point)
            if similarity < 0.78 or distance > 0.22:
                continue
            position_score = max(0.0, 1.0 - distance / 0.22)
            quality = similarity * (0.55 + 0.45 * position_score)
            if best is None or quality > best[0]:
                best = (quality, block, similarity, distance)
        if best is None:
            continue
        quality, block, similarity, distance = best
        used_blocks.add(id(block))
        weight = max(float(feature.get("weight", 1.0)), 0.1)
        matched_weight += weight
        quality_weighted += quality * weight
        matched.append({
            "feature": text,
            "text": str(block.get("text") or ""),
            "role": feature.get("role", "field_anchor"),
            "similarity": round(similarity, 4),
            "distance": round(distance, 4),
        })

    coverage = matched_weight / max(total_weight, 0.1)
    quality = quality_weighted / max(matched_weight, 0.1) if matched else 0.0
    score = 0.7 * coverage + 0.3 * quality
    min_matches = max(int(detection.get("min_matches", 2)), 1)
    min_score = float(detection.get("min_score", 0.55))
    accepted = len(matched) >= min_matches and score >= min_score
    return {
        "score": round(score if accepted else 0.0, 4),
        "raw_score": round(score, 4),
        "coverage": round(coverage, 4),
        "matched_count": len(matched),
        "features_count": len(features),
        "matched": matched,
        "accepted": accepted,
        "mode": "anchor_layout",
    }

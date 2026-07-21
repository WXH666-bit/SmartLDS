"""
SmartLDS 混合识别兜底模块。

设计原则：先走本地 PaddleOCR + 版式规则，只有当本地结果明显不稳时，
才调用视觉大模型兜底。典型触发场景包括 unknown 版式、字段覆盖率过低、
FUNSD/真实扫描件这类固定模板规则难以覆盖的复杂表单。

运行开关：
- VISION_FALLBACK_ENABLED=true：允许调用视觉模型。
- OPENAI_API_KEY：存在时才会真正发起模型请求。
- VISION_FALLBACK_THRESHOLD：本地总置信度低于该阈值时触发兜底。
- VISION_FALLBACK_MODEL：指定视觉模型。

失败策略：视觉兜底没配置、超时、返回 JSON 不合法时，不能让识别任务失败；
系统会保留本地规则结果，并把原因写入 result.meta.warnings。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Any


COMPLEX_LOW_COVERAGE_TEMPLATES = {"funsd_public", "real_scan"}
DEFAULT_FALLBACK_THRESHOLD = 0.55
DEFAULT_VISION_PROVIDER = "qwen"
DEPRECATED_QWEN_MODELS = {"qwen-vl-plus"}
VISION_PROVIDER_OPTIONS = [
    {
        "key": "qwen",
        "label": "通义千问 / 阿里云百炼",
        "default_model": "qwen-3.6-flash",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_hint": "DashScope API Key",
        "requires_api_key": True,
        "transport": "chat_completions",
        "models": [
            {"value": "qwen-3.6-flash", "label": "qwen-3.6-flash（默认）"},
            {"value": "qwen3.6-plus", "label": "qwen3.6-plus"},
            {"value": "qwen-vl-max", "label": "qwen-vl-max"},
            {"value": "qwen2.5-vl-72b-instruct", "label": "qwen2.5-vl-72b-instruct"},
            {"value": "qwen2.5-vl-32b-instruct", "label": "qwen2.5-vl-32b-instruct"},
            {"value": "qwen2.5-vl-7b-instruct", "label": "qwen2.5-vl-7b-instruct"},
        ],
    },
    {
        "key": "openai",
        "label": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "default_base_url": "https://api.openai.com/v1",
        "api_key_hint": "OpenAI API Key",
        "requires_api_key": True,
        "transport": "responses",
        "models": [
            {"value": "gpt-4.1-mini", "label": "gpt-4.1-mini"},
            {"value": "gpt-4.1", "label": "gpt-4.1"},
            {"value": "gpt-4o-mini", "label": "gpt-4o-mini"},
        ],
    },
    {
        "key": "custom",
        "label": "自定义 OpenAI-compatible",
        "default_model": "custom-vision-model",
        "default_base_url": "http://localhost:9000/v1",
        "api_key_hint": "API Key",
        "requires_api_key": True,
        "transport": "chat_completions",
        "models": [
            {"value": "custom-vision-model", "label": "custom-vision-model"},
        ],
    },
    {
        "key": "ollama",
        "label": "Ollama 本地模型",
        "default_model": "qwen3-vl:8b",
        "default_base_url": "http://localhost:11434",
        "api_key_hint": "不需要 API Key",
        "requires_api_key": False,
        "transport": "ollama_chat",
        "models": [
            {"value": "qwen3-vl:8b", "label": "qwen3-vl:8b"},
            {"value": "llama3.2-vision", "label": "llama3.2-vision"},
            {"value": "llava", "label": "llava"},
        ],
    },
]


def provider_defaults(provider: str | None = None) -> dict[str, Any]:
    provider = provider or DEFAULT_VISION_PROVIDER
    for item in VISION_PROVIDER_OPTIONS:
        if item["key"] == provider:
            return item
    return VISION_PROVIDER_OPTIONS[0]


def default_vision_settings() -> dict[str, Any]:
    qwen = provider_defaults("qwen")
    return {
        "enabled": False,
        "provider": "qwen",
        "model": qwen["default_model"],
        "base_url": qwen["default_base_url"],
        "api_key": "",
        "threshold": DEFAULT_FALLBACK_THRESHOLD,
    }


def normalize_vision_model(provider: str | None, model: str | None) -> str:
    defaults = provider_defaults(provider)
    model = str(model or "").strip()
    if provider == "qwen" and model in DEPRECATED_QWEN_MODELS:
        return defaults["default_model"]
    return model or defaults["default_model"]


def mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * 8}{api_key[-4:]}"


def public_vision_settings(settings: dict[str, Any]) -> dict[str, Any]:
    public = dict(settings)
    api_key = str(public.pop("api_key", "") or "")
    public["has_api_key"] = bool(api_key)
    public["masked_api_key"] = mask_api_key(api_key)
    profiles = {}
    for key, profile in (settings.get("profiles") or {}).items():
        if not isinstance(profile, dict):
            continue
        profile_public = dict(profile)
        profile_api_key = str(profile_public.pop("api_key", "") or "")
        profile_public["has_api_key"] = bool(profile_api_key)
        profile_public["masked_api_key"] = mask_api_key(profile_api_key)
        model_keys_public = {}
        for model, model_api_key in (profile.get("model_api_keys") or {}).items():
            model_api_key = str(model_api_key or "")
            model_keys_public[model] = {
                "has_api_key": bool(model_api_key),
                "masked_api_key": mask_api_key(model_api_key),
            }
        if model_keys_public:
            profile_public["model_api_keys"] = model_keys_public
        profiles[key] = profile_public
    if profiles:
        public["profiles"] = profiles
    return public


def vision_settings_options() -> dict[str, Any]:
    return {
        "providers": VISION_PROVIDER_OPTIONS,
        "default_provider": DEFAULT_VISION_PROVIDER,
        "default_threshold": DEFAULT_FALLBACK_THRESHOLD,
    }


def _provider_requires_api_key(provider: str | None) -> bool:
    defaults = provider_defaults(provider)
    return bool(defaults.get("requires_api_key", True))


def _provider_env_api_key(provider: str | None) -> str:
    if provider == "qwen":
        return os.getenv("DASHSCOPE_API_KEY", "")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", "")
    if provider == "ollama":
        return os.getenv("OLLAMA_API_KEY", "")
    return os.getenv("CUSTOM_VISION_API_KEY", "")


def _provider_key_name(provider: str | None) -> str:
    if provider == "qwen":
        return "DASHSCOPE_API_KEY"
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "ollama":
        return "OLLAMA_API_KEY"
    return "CUSTOM_VISION_API_KEY"


def _default_api_key(provider: str | None) -> str:
    if not _provider_requires_api_key(provider):
        return "ollama"
    return ""


def _build_provider_endpoint(provider: str | None, base_url: str) -> str:
    base = str(base_url or provider_defaults(provider)["default_base_url"]).rstrip("/")
    if provider == "ollama":
        for suffix in ("/v1/chat/completions", "/chat/completions", "/v1", "/api/chat", "/api/tags"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}/api/chat"
    if base.endswith("/chat/completions") or base.endswith("/responses"):
        return base
    if provider == "openai":
        return os.getenv("OPENAI_RESPONSES_URL", f"{base}/responses")
    return f"{base}/chat/completions"


def _build_models_endpoint(provider: str | None, base_url: str) -> str:
    base = str(base_url or provider_defaults(provider)["default_base_url"]).rstrip("/")
    if provider == "ollama":
        for suffix in ("/v1/chat/completions", "/chat/completions", "/v1", "/api/chat", "/api/tags"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}/api/tags"
    for suffix in ("/chat/completions", "/responses", "/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/models"


def _model_has_vision_hint(model_id: str) -> bool:
    text = str(model_id or "").lower()
    vision_tokens = ("vision", "vl", "omni", "flash", "4o", "qwen")
    return any(token in text for token in vision_tokens)


def _normalize_probe_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_models = []
    if isinstance(payload.get("data"), list):
        raw_models = payload["data"]
    elif isinstance(payload.get("models"), list):
        raw_models = payload["models"]

    models = []
    seen = set()
    for item in raw_models:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
        else:
            continue
        model_id = str(model_id or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append({
            "value": model_id,
            "label": model_id,
            "vision_hint": _model_has_vision_hint(model_id),
        })

    return sorted(models, key=lambda item: not item["vision_hint"])


def probe_vision_models(data: dict[str, Any], saved_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(saved_settings or default_vision_settings())
    provider = str(data.get("provider") or settings.get("provider") or DEFAULT_VISION_PROVIDER)
    provider_cfg = provider_defaults(provider)
    saved_profile = {}
    if isinstance(settings.get("profiles"), dict):
        saved_profile = settings["profiles"].get(provider) or {}
    base_url = str(data.get("base_url") or saved_profile.get("base_url") or settings.get("base_url") or provider_cfg["default_base_url"]).strip()
    api_key = str(data.get("api_key") or saved_profile.get("api_key") or settings.get("api_key") or _provider_env_api_key(provider) or _default_api_key(provider)).strip()

    if _provider_requires_api_key(provider) and not api_key:
        return {
            "success": False,
            "models": [],
            "warning": f"缺少 {provider_cfg.get('api_key_hint') or _provider_key_name(provider)}",
            "endpoint": _build_models_endpoint(provider, base_url),
        }

    endpoint = _build_models_endpoint(provider, base_url)
    headers = {"Content-Type": "application/json"}
    if api_key and provider != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(endpoint, method="GET", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=45.0) as resp:
            body = resp.read().decode("utf-8")
        payload = json.loads(body)
        models = _normalize_probe_models(payload if isinstance(payload, dict) else {})
    except (json.JSONDecodeError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "models": [],
            "warning": f"模型检测失败：{exc}",
            "endpoint": endpoint,
        }

    if not models:
        return {
            "success": False,
            "models": [],
            "warning": "检测成功，但接口未返回可用模型",
            "endpoint": endpoint,
        }

    return {
        "success": True,
        "models": models,
        "endpoint": endpoint,
        "warnings": [] if any(item["vision_hint"] for item in models) else ["未能从模型名判断视觉能力，请选择支持图片输入的模型"],
    }


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _text_quality(blocks: list[dict[str, Any]] | None) -> dict[str, float]:
    blocks = blocks or []
    if not blocks:
        return {
            "ocr_text_quality": 0.0,
            "ocr_avg_confidence": 0.0,
            "ocr_block_density": 0.0,
            "ocr_fragment_score": 0.0,
            "ocr_charset_score": 0.0,
        }

    confidences = [_clamp01(_as_float(b.get("confidence"), 0.0)) for b in blocks]
    avg_conf = sum(confidences) / max(len(confidences), 1)

    texts = [str(b.get("text", "")).strip() for b in blocks]
    total_chars = sum(len(t) for t in texts)
    sensible_chars = sum(len(re.findall(r"[\w\u4e00-\u9fff:/.,%\u00a5$#&+\-() ]", t)) for t in texts)
    charset_score = sensible_chars / max(total_chars, 1)

    avg_len = total_chars / max(len(texts), 1)
    fragment_score = _clamp01(avg_len / 8.0)
    block_density = _clamp01(len(blocks) / 12.0)

    quality = _clamp01(
        avg_conf * 0.55
        + charset_score * 0.25
        + block_density * 0.12
        + fragment_score * 0.08
    )

    return {
        "ocr_text_quality": round(quality, 4),
        "ocr_avg_confidence": round(avg_conf, 4),
        "ocr_block_density": round(block_density, 4),
        "ocr_fragment_score": round(fragment_score, 4),
        "ocr_charset_score": round(charset_score, 4),
    }


def evaluate_recognition_quality(
    result: dict[str, Any],
    blocks: list[dict[str, Any]] | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """评估本地识别质量，并判断是否需要进入视觉兜底。"""

    threshold = DEFAULT_FALLBACK_THRESHOLD if threshold is None else threshold
    meta = result.get("meta", {}) if isinstance(result, dict) else {}
    template = result.get("template") or meta.get("template") or "unknown"
    fields = result.get("fields", {}) if isinstance(result.get("fields"), dict) else {}

    total = int(meta.get("fields_total") or len(fields) or 0)
    extracted = int(meta.get("fields_extracted") or sum(
        1 for f in fields.values()
        if isinstance(f, dict) and f.get("status") != "not_found"
    ))
    field_coverage = extracted / total if total else 0.0

    field_scores = [
        _clamp01(_as_float(info.get("confidence"), 0.0))
        for info in fields.values()
        if isinstance(info, dict) and info.get("status") != "not_found"
    ]
    avg_field_score = sum(field_scores) / max(len(field_scores), 1) if field_scores else 0.0

    debug = result.get("debug", {}).get("extraction", {}) if isinstance(result.get("debug"), dict) else {}
    template_scores = debug.get("template_scores", {}) if isinstance(debug, dict) else {}
    tpl_info = template_scores.get(template, {}) if isinstance(template_scores, dict) else {}
    template_score = _as_float(tpl_info.get("score"), 0.0)
    ranked_scores = sorted(
        [_as_float(v.get("score"), 0.0) for v in template_scores.values() if isinstance(v, dict)],
        reverse=True,
    )
    if ranked_scores:
        template_gap = ranked_scores[0] - (ranked_scores[1] if len(ranked_scores) > 1 else 0.0)
    else:
        template_gap = 0.0

    rejected_count = 0
    candidate_count = 0
    debug_fields = debug.get("fields", {}) if isinstance(debug, dict) else {}
    if isinstance(debug_fields, dict):
        for finfo in debug_fields.values():
            if not isinstance(finfo, dict):
                continue
            rejected_count += len(finfo.get("rejected", []) or [])
            candidate_count += len(finfo.get("candidates", []) or [])
    rejected_ratio = rejected_count / max(rejected_count + candidate_count, 1) if (rejected_count or candidate_count) else 0.0

    ocr_quality = _text_quality(blocks)
    if template == "unknown":
        template_component = 0.0
    else:
        template_component = template_score

    overall = _clamp01(
        template_component * 0.24
        + _clamp01(template_gap / 0.20) * 0.08
        + field_coverage * 0.28
        + avg_field_score * 0.24
        + (1.0 - rejected_ratio) * 0.06
        + ocr_quality["ocr_text_quality"] * 0.10
    )

    reasons: list[str] = []
    should_fallback = False
    if template == "unknown":
        should_fallback = True
        reasons.append("template_unknown")
    if overall < threshold:
        should_fallback = True
        reasons.append(f"overall_confidence_below_{threshold:.2f}")
    if template in COMPLEX_LOW_COVERAGE_TEMPLATES and field_coverage < 0.5:
        should_fallback = True
        reasons.append(f"{template}_low_field_coverage")

    return {
        "overall_confidence": round(overall, 4),
        "threshold": round(threshold, 4),
        "should_fallback": should_fallback,
        "fallback_reasons": reasons,
        "template_score": round(template_score, 4),
        "template_score_gap": round(template_gap, 4),
        "field_coverage": round(field_coverage, 4),
        "avg_field_score": round(avg_field_score, 4),
        "rejected_ratio": round(rejected_ratio, 4),
        **ocr_quality,
    }


def _field_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "document_type": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["label", "value", "confidence"],
                },
            },
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["title", "headers", "rows", "confidence"],
                },
            },
        },
        "required": ["document_type", "fields", "tables"],
    }


def _template_enhancement_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "template_keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"},
                        "label": {"type": "string"},
                        "anchors": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "position": {
                            "type": "string",
                            "enum": ["right", "below", "inline"],
                        },
                        "value_pattern": {"type": "string"},
                        "multi_line": {"type": "boolean"},
                        "allow_shared": {"type": "boolean"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "field",
                        "label",
                        "anchors",
                        "position",
                        "value_pattern",
                        "multi_line",
                        "allow_shared",
                        "confidence",
                        "notes",
                    ],
                },
            },
            "table_headers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["template_keywords", "fields", "table_headers", "warnings"],
    }


def _data_url(image_path: str) -> str:
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_output_text(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]

    message = response_json.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"].strip()

    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts).strip()

    texts: list[str] = []
    for item in response_json.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts).strip()


def _vision_field_entry(label: str, value: str, confidence: float) -> dict[str, Any]:
    confidence = _clamp01(confidence)
    return {
        "label": label,
        "value": value,
        "cleaned": value,
        "confidence": round(confidence, 4),
        "status": "extracted",
        "anchor": "",
        "rect": [0, 0, 0, 0],
        "canonical_key": None,
        "source": "vision_fallback",
    }


def _add_vision_field(
    fields: dict[str, dict[str, Any]],
    seen: dict[str, int],
    label: str,
    value: str,
    confidence: float,
) -> None:
    label = str(label or "").strip()
    value = str(value or "").strip()
    if not label or not value:
        return
    key = label
    if key in fields:
        seen[key] = seen.get(key, 1) + 1
        key = f"{label}_{seen[label]}"
    fields[key] = _vision_field_entry(label, value, confidence)


def _looks_like_form_label(text: str) -> bool:
    text = str(text or "").strip().strip(":\uff1a")
    if not text:
        return False
    if len(text) > 32:
        return False
    if len(text.split()) > 5:
        return False
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", text):
        return False

    compact = re.sub(r"\s+", "", text)
    digit_count = sum(ch.isdigit() for ch in compact)
    if digit_count and digit_count / max(len(compact), 1) > 0.15:
        return False
    if re.search(r"\d{2,4}[-/.]\d{1,2}[-/.]\d{1,4}", text):
        return False
    if re.search(r"\d", text) and re.search(r"[A-Z]{2,}|[A-Za-z]{1,4}\b", text):
        return False
    return True


def _table_to_key_value_fields(item: dict[str, Any], headers: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    column_count = len(headers)
    if column_count < 4 or column_count % 2 != 0:
        return []

    matrix = [headers] + rows
    pairs: list[tuple[str, str]] = []
    label_like = 0
    complete_rows = 0
    for row in matrix:
        normalized = [str(cell or "").strip() for cell in row[:column_count]]
        if len(normalized) < column_count:
            normalized.extend([""] * (column_count - len(normalized)))

        row_pairs: list[tuple[str, str]] = []
        for index in range(0, column_count, 2):
            label = normalized[index].strip()
            value = normalized[index + 1].strip()
            if not label and not value:
                continue
            if not label or not value:
                return []
            row_pairs.append((label, value))
            if _looks_like_form_label(label):
                label_like += 1

        if row_pairs:
            if len(row_pairs) < 2:
                return []
            complete_rows += 1
            pairs.extend(row_pairs)

    if complete_rows < 2 or len(pairs) < 4:
        return []
    if label_like / max(len(pairs), 1) < 0.85:
        return []

    confidence = round(_clamp01(_as_float(item.get("confidence"), 0.0)), 4)
    return [
        {"label": label, "value": value, "confidence": confidence}
        for label, value in pairs
    ]


def _normalized_field_label(label: str) -> str:
    return re.sub(r"\s+", "", str(label or "").strip().strip(":\uff1a")).lower()


def _block_rect(block: dict[str, Any]) -> list[float] | None:
    rect = block.get("rect")
    if isinstance(rect, list) and len(rect) == 4:
        try:
            return [float(v) for v in rect]
        except (TypeError, ValueError):
            return None

    bbox = block.get("bbox")
    if isinstance(bbox, list) and bbox:
        try:
            xs = [float(point[0]) for point in bbox if isinstance(point, list) and len(point) >= 2]
            ys = [float(point[1]) for point in bbox if isinstance(point, list) and len(point) >= 2]
        except (TypeError, ValueError):
            return None
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _ocr_rows(blocks: list[dict[str, Any]] | None) -> list[list[dict[str, Any]]]:
    cells = []
    heights = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        rect = _block_rect(block)
        if not text or not rect:
            continue
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            continue
        cell = {
            "text": text,
            "rect": rect,
            "center_y": (top + bottom) / 2,
            "left": left,
            "confidence": _clamp01(_as_float(block.get("confidence"), 0.85)),
        }
        cells.append(cell)
        heights.append(bottom - top)

    if not cells:
        return []

    heights.sort()
    median_height = heights[len(heights) // 2]
    row_tolerance = max(12.0, median_height * 0.65)
    rows: list[dict[str, Any]] = []
    for cell in sorted(cells, key=lambda item: item["center_y"]):
        for row in rows:
            if abs(cell["center_y"] - row["center_y"]) <= row_tolerance:
                row["cells"].append(cell)
                row["center_y"] = sum(c["center_y"] for c in row["cells"]) / len(row["cells"])
                break
        else:
            rows.append({"center_y": cell["center_y"], "cells": [cell]})

    return [
        sorted(row["cells"], key=lambda item: item["left"])
        for row in sorted(rows, key=lambda item: item["center_y"])
    ]


def _extract_key_value_grid_fields_from_blocks(blocks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    pairs = []
    candidate_rows = 0
    for row in _ocr_rows(blocks):
        if len(row) != 4:
            continue
        left_label, left_value, right_label, right_value = row
        if not (_looks_like_form_label(left_label["text"]) and _looks_like_form_label(right_label["text"])):
            continue
        if not left_value["text"].strip() or not right_value["text"].strip():
            continue
        candidate_rows += 1
        pairs.append((left_label, left_value))
        pairs.append((right_label, right_value))

    if candidate_rows < 2 or len(pairs) < 4:
        return []

    fields = []
    for label_cell, value_cell in pairs:
        confidence = (label_cell["confidence"] + value_cell["confidence"]) / 2
        fields.append({
            "label": label_cell["text"],
            "value": value_cell["text"],
            "confidence": confidence,
        })
    return fields


def supplement_vision_payload_from_ocr_blocks(
    normalized: dict[str, Any],
    blocks: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Fill obvious OCR key-value grids that the vision model omitted entirely."""
    if not isinstance(normalized, dict):
        return normalized
    fields = normalized.get("fields") if isinstance(normalized.get("fields"), dict) else {}
    tables = normalized.get("tables") if isinstance(normalized.get("tables"), list) else []
    if tables or len(fields) > 3:
        return normalized

    grid_fields = _extract_key_value_grid_fields_from_blocks(blocks)
    if not grid_fields:
        return normalized

    updated = deepcopy(normalized)
    updated_fields = dict(fields)
    seen: dict[str, int] = {}
    for key in updated_fields:
        seen[key] = max(seen.get(key, 0), 1)

    existing_labels = {
        _normalized_field_label(info.get("label") or key)
        for key, info in updated_fields.items()
        if isinstance(info, dict)
    }
    for item in grid_fields:
        label = str(item.get("label") or "").strip()
        normalized_label = _normalized_field_label(label)
        if not normalized_label or normalized_label in existing_labels:
            continue
        _add_vision_field(
            updated_fields,
            seen,
            label,
            item.get("value"),
            _as_float(item.get("confidence"), 0.85),
        )
        existing_labels.add(normalized_label)

    updated["fields"] = updated_fields
    return updated


def normalize_vision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把模型返回的 JSON 转成 SmartLDS 的字段 + 表格结构。"""
    fields: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}

    for item in payload.get("fields", []) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        confidence = _clamp01(_as_float(item.get("confidence"), 0.0))
        _add_vision_field(fields, seen, label, value, confidence)

    tables = []
    for item in payload.get("tables", []) or []:
        if not isinstance(item, dict):
            continue
        headers = [str(header).strip() for header in (item.get("headers") or []) if str(header).strip()]
        if not headers:
            continue
        rows = []
        for row in item.get("rows", []) or []:
            if not isinstance(row, list):
                continue
            normalized_row = [str(cell) for cell in row]
            if len(normalized_row) < len(headers):
                normalized_row.extend([""] * (len(headers) - len(normalized_row)))
            rows.append(normalized_row[:len(headers)])
        if not rows:
            continue
        key_value_fields = _table_to_key_value_fields(item, headers, rows)
        if key_value_fields:
            for field_item in key_value_fields:
                _add_vision_field(
                    fields,
                    seen,
                    field_item["label"],
                    field_item["value"],
                    field_item["confidence"],
                )
            continue
        tables.append({
            "title": str(item.get("title") or "").strip(),
            "headers": headers,
            "rows": rows,
            "confidence": round(_clamp01(_as_float(item.get("confidence"), 0.0)), 4),
            "source": "vision_fallback",
        })

    first_table = deepcopy(tables[0]) if tables else {}
    return {
        "template": "vision_generic",
        "source": "vision_fallback",
        "document_type": str(payload.get("document_type") or "generic_form"),
        "fields": fields,
        "table": first_table,
        "tables": tables,
    }


def merge_vision_fallback_result(
    local_result: dict[str, Any],
    vision_result: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    """视觉兜底成功时，用模型字段替换低置信度本地字段。"""
    merged = deepcopy(local_result)
    fields = vision_result.get("fields", {}) if isinstance(vision_result, dict) else {}
    tables = vision_result.get("tables", []) if isinstance(vision_result, dict) else []
    if not fields and not tables:
        return merged

    merged["template"] = vision_result.get("template", "vision_generic")
    merged["fields"] = fields
    if tables:
        merged["tables"] = tables
        merged["table"] = deepcopy(tables[0])
    else:
        merged.setdefault("table", local_result.get("table", {}))

    confidence_parts = [_as_float(f.get("confidence"), 0.0) for f in fields.values()]
    confidence_parts.extend(_as_float(t.get("confidence"), 0.0) for t in tables if isinstance(t, dict))
    table_rows = sum(len(t.get("rows", []) or []) for t in tables if isinstance(t, dict))
    meta = dict(merged.get("meta", {}))
    meta.update({
        "template": merged["template"],
        "extraction_source": "vision_fallback",
        "confidence": round(sum(confidence_parts) / max(len(confidence_parts), 1), 4),
        "local_rules_confidence": quality.get("overall_confidence", 0.0),
        "fallback_reason": ", ".join(quality.get("fallback_reasons", [])),
        "fields_total": len(fields),
        "fields_extracted": len(fields),
        "table_count": len(tables),
        "table_rows": table_rows,
        "vision_document_type": vision_result.get("document_type", ""),
    })
    merged["meta"] = meta
    return merged


def attach_quality_meta(result: dict[str, Any], quality: dict[str, Any], extraction_source: str = "local_rules") -> dict[str, Any]:
    updated = deepcopy(result)
    meta = dict(updated.get("meta", {}))
    meta.update({
        "confidence": quality.get("overall_confidence", 0.0),
        "extraction_source": extraction_source,
        "template_score": quality.get("template_score", 0.0),
        "template_score_gap": quality.get("template_score_gap", 0.0),
        "field_coverage": quality.get("field_coverage", 0.0),
        "avg_field_score": quality.get("avg_field_score", 0.0),
        "rejected_ratio": quality.get("rejected_ratio", 0.0),
        "ocr_text_quality": quality.get("ocr_text_quality", 0.0),
    })
    updated["meta"] = meta
    return updated


def add_meta_warning(result: dict[str, Any], warning: str) -> dict[str, Any]:
    updated = deepcopy(result)
    meta = dict(updated.get("meta", {}))
    warnings = list(meta.get("warnings", []) or [])
    if warning not in warnings:
        warnings.append(warning)
    meta["warnings"] = warnings
    updated["meta"] = meta
    return updated


class VisionFallbackClient:
    """轻量视觉兜底客户端；使用标准库 urllib，避免额外引入 HTTP 依赖。"""

    def __init__(
        self,
        api_key: str | None = None,
        enabled: bool | None = None,
        model: str | None = None,
        timeout: float | None = None,
        endpoint: str | None = None,
        settings: dict[str, Any] | None = None,
    ):
        merged = default_vision_settings()
        if settings:
            merged.update({k: v for k, v in settings.items() if v is not None})
        provider = str(merged.get("provider") or DEFAULT_VISION_PROVIDER)
        defaults = provider_defaults(provider)

        env_key = _provider_env_api_key(provider)
        self.provider = provider
        self.api_key = api_key if api_key is not None else (merged.get("api_key") or env_key or _default_api_key(provider))
        self.enabled = _env_bool("VISION_FALLBACK_ENABLED", bool(merged.get("enabled"))) if enabled is None else enabled
        self.model = model or os.getenv("VISION_FALLBACK_MODEL") or merged.get("model") or defaults["default_model"]
        self.base_url = str(merged.get("base_url") or defaults["default_base_url"]).rstrip("/")
        self.timeout = timeout or _env_float("VISION_FALLBACK_TIMEOUT", 90.0)
        self.endpoint_type = str(defaults.get("transport") or "chat_completions")
        self.ollama_num_ctx = int(_as_float(merged.get("num_ctx"), 8192) or 8192)
        self.endpoint = endpoint or os.getenv("VISION_FALLBACK_ENDPOINT", "")
        if not self.endpoint:
            self.endpoint = _build_provider_endpoint(self.provider, self.base_url)

    def unavailable_reason(self) -> str | None:
        if not self.enabled:
            return "视觉兜底未启用（VISION_FALLBACK_ENABLED 未设为 true）"
        if _provider_requires_api_key(self.provider) and not self.api_key:
            key_name = _provider_key_name(self.provider)
            return f"视觉兜底未启用（缺少 {key_name} 或前端保存的 API Key）"
        return None

    def extract(
        self,
        image_path: str,
        blocks: list[dict[str, Any]] | None,
        local_result: dict[str, Any],
        quality: dict[str, Any],
    ) -> dict[str, Any]:
        unavailable = self.unavailable_reason()
        if unavailable:
            return {"success": False, "warning": unavailable, "retryable": False}

        prompt = self._build_prompt(blocks, local_result, quality)
        payload = self._build_payload(prompt, image_path)

        last_error = ""
        for attempt in range(2):
            try:
                response_json = self._post_json(payload)
                text = _extract_output_text(response_json)
                parsed = json.loads(text)
                normalized = normalize_vision_payload(parsed)
                normalized = supplement_vision_payload_from_ocr_blocks(normalized, blocks)
                if normalized.get("fields") or normalized.get("tables"):
                    return {"success": True, "result": normalized, "attempts": attempt + 1}
                last_error = "模型未返回有效字段或表格"
            except (json.JSONDecodeError, ValueError, urllib.error.URLError, TimeoutError, OSError) as e:
                last_error = str(e)
                time.sleep(0.2)

        return {
            "success": False,
            "warning": f"视觉兜底失败，已回退本地规则结果：{last_error}",
            "retryable": True,
        }

    def enhance_template_config(
        self,
        image_path: str,
        blocks: list[dict[str, Any]] | None,
        final_result: dict[str, Any],
        template_name: str,
        target_template: dict[str, Any],
        selected_fields: list[str],
        include_table: bool,
    ) -> dict[str, Any]:
        """让视觉模型基于当前结果给出 Few-shot 版式配置增强建议。"""
        unavailable = self.unavailable_reason()
        if unavailable:
            return {"success": False, "warning": unavailable, "retryable": False}

        prompt = self._build_template_enhancement_prompt(
            blocks=blocks,
            final_result=final_result,
            template_name=template_name,
            target_template=target_template,
            selected_fields=selected_fields,
            include_table=include_table,
        )
        payload = self._build_template_enhancement_payload(prompt, image_path)

        last_error = ""
        for attempt in range(2):
            try:
                response_json = self._post_json(payload)
                text = _extract_output_text(response_json)
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return {"success": True, "result": parsed, "attempts": attempt + 1}
                last_error = "模型未返回 JSON 对象"
            except (json.JSONDecodeError, ValueError, urllib.error.URLError, TimeoutError, OSError) as e:
                last_error = str(e)
                time.sleep(0.2)

        return {
            "success": False,
            "warning": f"AI 增强失败，已保留普通反哺结果：{last_error}",
            "retryable": True,
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.provider != "ollama" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"HTTP Error {exc.code}: {body[:1000]}") from exc
        return json.loads(body)

    def _build_payload(self, prompt: str, image_path: str) -> dict[str, Any]:
        image_url = _data_url(image_path)
        if self.provider == "openai":
            return {
                "model": self.model,
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "smartlds_document_fields",
                        "schema": _field_schema(),
                        "strict": True,
                    }
                },
            }

        schema_hint = json.dumps(_field_schema(), ensure_ascii=False)
        if self.provider == "ollama":
            image_b64 = image_url.split(",", 1)[1] if "," in image_url else image_url
            return {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": (
                        prompt
                        + "\n\n请只返回合法 JSON，不要输出解释文字。JSON 必须满足这个结构："
                        + schema_hint
                    ),
                    "images": [image_b64],
                }],
                "format": "json",
                "stream": False,
                "options": {"num_ctx": self.ollama_num_ctx},
            }

        return {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            prompt
                            + "\n\n请只返回合法 JSON，不要输出解释文字。JSON 必须满足这个结构："
                            + schema_hint
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }

    def _build_template_enhancement_payload(self, prompt: str, image_path: str) -> dict[str, Any]:
        image_url = _data_url(image_path)
        schema = _template_enhancement_schema()
        if self.provider == "openai":
            return {
                "model": self.model,
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "smartlds_template_enhancement",
                        "schema": schema,
                        "strict": True,
                    }
                },
            }

        schema_hint = json.dumps(schema, ensure_ascii=False)
        if self.provider == "ollama":
            image_b64 = image_url.split(",", 1)[1] if "," in image_url else image_url
            return {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": (
                        prompt
                        + "\n\n请只返回合法 JSON，不要输出解释文字。JSON 必须满足这个结构："
                        + schema_hint
                    ),
                    "images": [image_b64],
                }],
                "format": "json",
                "stream": False,
                "options": {"num_ctx": self.ollama_num_ctx},
            }

        return {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            prompt
                            + "\n\n请只返回合法 JSON，不要输出解释文字。JSON 必须满足这个结构："
                            + schema_hint
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }

    @staticmethod
    def _build_prompt(
        blocks: list[dict[str, Any]] | None,
        local_result: dict[str, Any],
        quality: dict[str, Any],
    ) -> str:
        ocr_lines = []
        for b in (blocks or [])[:80]:
            text = str(b.get("text", "")).strip()
            if text:
                ocr_lines.append(text)

        local_fields = []
        for key, info in (local_result.get("fields", {}) or {}).items():
            if isinstance(info, dict) and info.get("status") != "not_found" and info.get("value"):
                local_fields.append({"label": info.get("label") or key, "value": info.get("value")})

        return (
            "You are extracting fields from a logistics, customs, delivery, or generic form image.\n"
            "Return visible key-value fields and structured tables. Use the original printed label text as the field label; "
            "do not map it to a preset schema. If a form has question-answer pairs, use the question text as the label. "
            "A bordered grid that alternates label/value/label/value is still key-value fields, not a table. "
            "If content is arranged in a grid with repeated headers and rows, put it in tables instead of repeating "
            "the column header as many fields; use tables only for repeated records under stable column headers. "
            "Preserve each table section title when visible. "
            "Ignore decorative titles unless they have a value or name a table section. Keep values concise but complete.\n\n"
            f"Local extractor template: {local_result.get('template')}\n"
            f"Local quality: {json.dumps(quality, ensure_ascii=False)}\n"
            f"Local extracted fields: {json.dumps(local_fields[:30], ensure_ascii=False)}\n"
            f"OCR text hints:\n" + "\n".join(ocr_lines)
        )

    @staticmethod
    def _build_template_enhancement_prompt(
        blocks: list[dict[str, Any]] | None,
        final_result: dict[str, Any],
        template_name: str,
        target_template: dict[str, Any],
        selected_fields: list[str],
        include_table: bool,
    ) -> str:
        ocr_lines = []
        for b in (blocks or [])[:120]:
            text = str(b.get("text", "")).strip()
            if text:
                ocr_lines.append(text)

        field_hints = []
        fields = final_result.get("fields", {}) if isinstance(final_result, dict) else {}
        for key in selected_fields:
            info = fields.get(key, {}) if isinstance(fields, dict) else {}
            if isinstance(info, dict):
                field_hints.append({
                    "field": key,
                    "label": info.get("label") or key,
                    "value": info.get("corrected") or info.get("cleaned") or info.get("value") or "",
                    "status": info.get("status", ""),
                    "anchors": info.get("anchors") or info.get("anchor") or info.get("anchor_text") or "",
                })

        table = final_result.get("table", {}) if isinstance(final_result, dict) else {}
        target_view = {
            "keywords": target_template.get("keywords", []),
            "has_table": target_template.get("has_table", False),
            "table_headers": target_template.get("table_headers", []),
            "fields": target_template.get("fields", {}),
            "output": target_template.get("output", []),
        }

        return (
            "You are helping improve a SmartLDS few-shot template configuration. "
            "Do not extract arbitrary new fields. Only suggest improvements for selected fields. "
            "Use visible text and OCR hints as evidence. Prefer original printed labels as anchors. "
            "Return multiple useful anchors per field when possible. "
            "Use position right/below/inline, set multi_line only for company/address-like long fields, "
            "and include value_pattern only when the value format is obvious. "
            "If a suggestion is uncertain, put it in warnings instead of inventing anchors.\n\n"
            f"Template name: {template_name}\n"
            f"Selected fields: {json.dumps(selected_fields, ensure_ascii=False)}\n"
            f"Include table headers: {include_table}\n"
            f"Current target template: {json.dumps(target_view, ensure_ascii=False)[:6000]}\n"
            f"Final result field hints: {json.dumps(field_hints, ensure_ascii=False)}\n"
            f"Current table headers: {json.dumps(table.get('headers', []), ensure_ascii=False)}\n"
            f"OCR text hints:\n" + "\n".join(ocr_lines)
        )

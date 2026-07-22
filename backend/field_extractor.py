"""
关键信息抽取 KIE (Key Information Extraction)
基于锚点法的字段提取：在 OCR 文本块中匹配标签关键词 → 定位对应的值 → 正则校验

核心算法:
  1. 锚点匹配 — 在 body/header 区域中模糊搜索字段标签
  2. 值定位 — 同行右侧优先（Y 对齐），辅以紧邻下方
  3. 正则校验 — 对 B/L号、日期、箱号、重量等字段做格式验证
  4. 表格提取 — 对 table 区域进行行列结构恢复

配置:
  字段定义从 config.yaml 读取；若文件不存在则使用内置默认值。
  新增版式只需修改 config.yaml，无需改动此文件。

用法:
    extractor = FieldExtractor()
    result = extractor.extract(regions, image_size)
    # → {"fields": {...}, "table": [[...], ...], "template": "maersk_style"}
"""

import os
import re
import math
from difflib import SequenceMatcher

from template_signature import score_anchor_layout_signature

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_SCOPE_ANCHOR_FAMILIES = (
    ("发货方 SHIPPER", "收货方 CONSIGNEE"),
)


def _is_short_ascii_anchor(anchor):
    """Return whether an anchor must match as a complete ASCII token."""
    return bool(re.fullmatch(r"[A-Z0-9]{1,4}", str(anchor or "").upper()))


def _contains_direct_anchor(text, anchor):
    if _is_short_ascii_anchor(anchor):
        return bool(re.search(
            rf"(?<![A-Z0-9]){re.escape(anchor)}(?![A-Z0-9])",
            text,
        ))
    return anchor in text


TABLE_LAYOUT_X_PADDING_RATIO = 0.03
TABLE_LAYOUT_Y_PADDING_RATIO = 0.025


# ================================================================
# 内置默认配置（config.yaml 不存在时的回退）
# ================================================================

_DEFAULT_VALIDATORS = {
    "bl_no":      {"description": "提单号", "pattern": "[A-Z]{2,4}\\d{6,10}"},
    "date":       {"description": "日期", "pattern": "\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}"},
    "weight":     {"description": "重量", "pattern": "[\\d,]+\\.?\\d*", "strip_suffix": "KGS,KG,TONS"},
    "volume":     {"description": "体积", "pattern": "[\\d,]+\\.?\\d*", "strip_suffix": "CBM"},
    "place_date": {"description": "签发地+日期合并"},
}

_DEFAULT_FIELD_DEFAULTS = {
    "value": "", "cleaned": "", "confidence": 0.0,
    "status": "not_found", "anchor_text": "", "rect": [0, 0, 0, 0],
}

_DEFAULT_TEMPLATES_CONFIG = {
    "maersk_style": {
        "keywords": ["MAERSK", "MAERSK LINE", "BILL OF LADING", "海运提单"],
        "has_table": True,
        "fields": {
            "shipper":    {"label": "托运人", "anchors": ["Shipper", "SHIPPER", "托运人"], "position": "right"},
            "consignee":  {"label": "收货人", "anchors": ["Consignee", "CONSIGNEE", "收货人", "收货方"], "position": "right"},
            "notify_party": {"label": "通知方", "anchors": ["Notify Party", "Notify", "NOTIFY", "通知方", "通知人"], "position": "right"},
            "bl_no":      {"label": "提单号", "anchors": ["B/L No.", "B/L No", "BL No.", "提单号", "订舱号", "B/L"], "position": "either", "validator": "bl_no"},
            "pol":        {"label": "装货港", "anchors": ["Port of Loading", "装货港", "POL"], "position": "right"},
            "pod":        {"label": "卸货港", "anchors": ["Port of Discharge", "卸货港", "POD"], "position": "right"},
            "por":        {"label": "收货地", "anchors": ["Place of Receipt", "收货地", "POR"], "position": "right"},
            "delivery":   {"label": "交货地", "anchors": ["Place of Delivery", "交货地", "Delivery"], "position": "right"},
            "vessel":     {"label": "船名", "anchors": ["Vessel", "VESSEL", "船名"], "position": "right"},
            "voyage":     {"label": "航次", "anchors": ["Voyage No.", "Voyage", "航次"], "position": "right"},
            "total_gross_weight": {"label": "总毛重", "anchors": ["Total Gross Weight", "TOTAL GROSS WEIGHT", "总毛重", "毛重", "G.W.(KGS)"], "position": "right", "validator": "weight", "search_in": "all"},
            "total_measurement":  {"label": "总体积", "anchors": ["Total Measurement", "TOTAL MEASUREMENT", "总体积", "CBM:"], "position": "right", "validator": "volume", "search_in": "all"},
            "freight":    {"label": "运费条款", "anchors": ["Freight & Charges", "Freight", "FREIGHT", "运费条款", "运费"], "position": "right", "search_in": "all"},
            "issue_place":{"label": "签发地", "anchors": ["Place of Issue", "Issue Place", "签发地", "Place & Date of Issue"], "position": "right", "validator": "place_date", "search_in": "all"},
            "issue_date": {"label": "签发日期", "anchors": ["Date of Issue", "签发日期", "Date", "日期"], "position": "either", "validator": "date", "search_in": "all"},
        },
        "output": ["shipper", "consignee", "notify_party", "bl_no", "pol", "pod", "por", "delivery", "vessel", "voyage", "total_gross_weight", "total_measurement", "freight", "issue_place", "issue_date"],
    },
    "cosco_style": {
        "keywords": ["COSCO", "COSCO SHIPPING", "订舱委托书", "Booking Note"],
        "has_table": False,
        "fields": {
            "shipper":    {"label": "托运人", "anchors": ["Shipper", "SHIPPER", "托运人"], "position": "right"},
            "consignee":  {"label": "收货人", "anchors": ["Consignee", "CONSIGNEE", "收货人", "收货方"], "position": "right"},
            "notify_party": {"label": "通知方", "anchors": ["Notify Party", "Notify", "NOTIFY", "通知方", "通知人"], "position": "right"},
            "bl_no":      {"label": "提单号", "anchors": ["B/L No.", "B/L No", "BL No.", "提单号", "订舱号", "B/L"], "position": "either", "validator": "bl_no"},
            "pol":        {"label": "装货港", "anchors": ["Port of Loading", "装货港", "POL"], "position": "right"},
            "pod":        {"label": "卸货港", "anchors": ["Port of Discharge", "卸货港", "POD"], "position": "right"},
            "por":        {"label": "收货地", "anchors": ["收货地 POR:", "收货地", "POR"], "position": "right"},
            "delivery":   {"label": "交货地", "anchors": ["交货地 Delivery:", "交货地", "Delivery"], "position": "right"},
            "vessel":     {"label": "船名", "anchors": ["Vessel", "VESSEL", "船名"], "position": "right"},
            "voyage":     {"label": "航次", "anchors": ["Voyage No.", "Voyage", "航次"], "position": "right"},
            "freight":   {"label": "运费条款", "anchors": ["Freight & Charges", "Freight", "FREIGHT", "运费条款", "运费"], "position": "right", "search_in": "all"},
            "issue_place":{"label": "签发地", "anchors": ["Place of Issue", "Issue Place", "签发地", "Place & Date of Issue"], "position": "right", "validator": "place_date", "search_in": "all"},
            "issue_date": {"label": "签发日期", "anchors": ["Date of Issue", "签发日期", "Date", "日期"], "position": "either", "validator": "date", "search_in": "all"},
        },
        "output": ["shipper", "consignee", "notify_party", "bl_no", "pol", "pod", "por", "delivery", "vessel", "voyage", "freight", "issue_place", "issue_date"],
    },
    "simple_style": {
        "keywords": ["SHIPPING ORDER", "货运委托书"],
        "has_table": False,
        "fields": {
            "shipper":    {"label": "托运人", "anchors": ["Shipper", "SHIPPER", "托运人"], "position": "right"},
            "consignee":  {"label": "收货人", "anchors": ["Consignee", "CONSIGNEE", "收货人", "收货方"], "position": "right"},
            "notify_party":{"label": "通知方", "anchors": ["Notify Party", "Notify", "NOTIFY", "通知方", "通知人"], "position": "right"},
            "bl_no":      {"label": "提单号", "anchors": ["B/L No.", "B/L No", "BL No.", "提单号", "订舱号", "B/L"], "position": "either", "validator": "bl_no"},
            "pol":        {"label": "装货港", "anchors": ["Port of Loading", "装货港", "POL"], "position": "right"},
            "pod":        {"label": "卸货港", "anchors": ["Port of Discharge", "卸货港", "POD"], "position": "right"},
            "vessel":     {"label": "船名", "anchors": ["Vessel", "VESSEL", "船名"], "position": "right"},
            "voyage":     {"label": "航次", "anchors": ["Voyage No.", "Voyage", "航次"], "position": "right"},
            "freight":    {"label": "运费条款", "anchors": ["Freight & Charges", "Freight", "FREIGHT", "运费条款", "运费"], "position": "right", "search_in": "all"},
            "issue_place":{"label": "签发地", "anchors": ["Place of Issue", "Issue Place", "签发地", "Place & Date of Issue"], "position": "right", "validator": "place_date", "search_in": "all"},
            "issue_date": {"label": "签发日期", "anchors": ["Date of Issue", "签发日期", "Date"], "position": "either", "validator": "date", "search_in": "all"},
        },
        "output": ["shipper", "consignee", "notify_party", "bl_no", "pol", "pod", "vessel", "voyage", "freight", "issue_place", "issue_date"],
    },
    "funsd_public": {
        "keywords": ["FROM:", "TO:", "SUBJECT:", "DIVISION:", "REGION:"],
        "has_table": False,
        "fields": {
            "sender":     {"label": "发件人", "anchors": ["FROM:", "FROM", "From"], "position": "right"},
            "recipient":  {"label": "收件人", "anchors": ["TO:", "TO", "To"], "position": "right"},
            "subject":    {"label": "主题",   "anchors": ["SUBJECT:", "SUBJECT", "Subject"], "position": "right"},
            "division":   {"label": "分区",   "anchors": ["DIVISION:", "DIVISION", "Division"], "position": "right"},
            "region":     {"label": "区域",   "anchors": ["REGION:", "REGION", "Region"], "position": "right"},
        },
        "output": ["sender", "recipient", "subject", "division", "region"],
    },
    "real_scan": {
        "keywords": ["运单", "快递", "订单", "外卖", "配送", "Track", "Express", "取餐", "骑手"],
        "has_table": False,
        "fields": {
            "tracking_no":    {"label": "运单号", "anchors": ["运单号", "运单", "快递单", "Tracking", "单号"], "position": "right"},
            "sender_name":    {"label": "寄件人", "anchors": ["寄件人", "寄件", "发件人", "发件", "Sender"], "position": "right"},
            "sender_phone":   {"label": "寄件电话", "anchors": ["寄件电话", "寄件人电话", "电话"], "position": "right"},
            "sender_addr":    {"label": "寄件地址", "anchors": ["寄件地址", "寄件人地址", "地址"], "position": "right"},
            "recipient_name": {"label": "收件人", "anchors": ["收件人", "收件", "收货人", "收货", "Recipient"], "position": "right"},
            "recipient_phone":{"label": "收件电话", "anchors": ["收件电话", "收件人电话", "电话"], "position": "right"},
            "recipient_addr": {"label": "收件地址", "anchors": ["收件地址", "收件人地址", "地址"], "position": "right"},
            "order_no":       {"label": "订单号", "anchors": ["订单号", "订单", "Order No", "订单编号", "编号"], "position": "right"},
            "total_amount":   {"label": "合计金额", "anchors": ["合计", "金额", "实付", "Total", "商品合计", "¥", "￥"], "position": "right"},
            "courier":        {"label": "快递公司", "anchors": ["快递公司", "快递", "Courier", "配送", "物流", "承运"], "position": "right"},
        },
        "output": ["tracking_no", "sender_name", "sender_phone", "sender_addr", "recipient_name", "recipient_phone", "recipient_addr", "order_no", "total_amount", "courier"],
    },
}


# ================================================================
# 正则校验 & 清洗
# ================================================================

def _clean_text(text):
    """基础文本清洗"""
    text = text.strip()
    # 去掉末尾的冒号（标签残留，含全角）
    if (text.endswith(':') or text.endswith('：')) and len(text) < 30:
        return None
    return text


def validate_and_clean(field_name, raw_value, validator_cfg=None, field_cfg=None):
    """
    对提取到的原始值做正则校验和清洗

    支持两种模式：
      1. 传入 validator_cfg (来自 config.yaml 的 validators 节) — 配置驱动
      2. 不传 — 使用内置硬编码规则（向后兼容）

    :param field_name: 字段名
    :param raw_value: OCR 提取的原始值
    :param validator_cfg: {pattern, strip_suffix, ...} 来自配置
    :param field_cfg: 字段的完整配置（含 validator 规则名）
    :return: (cleaned_value, is_valid)
    """
    text = raw_value.strip()
    text_upper = text.upper()

    # --- 配置驱动模式 ---
    if validator_cfg and isinstance(validator_cfg, dict):
        pattern = validator_cfg.get("pattern")
        strip = validator_cfg.get("strip_suffix", "")

        # 去掉单位后缀
        if strip:
            suffixes = [s.strip().upper() for s in strip.split(",")]
            for s in suffixes:
                text_upper = re.sub(r'\s*' + re.escape(s) + r'\s*$', '', text_upper).strip()

        # 应用正则
        if pattern:
            m = re.search(pattern, text_upper)
            if m:
                cleaned = m.group(0).replace(',', '').strip()
                return (cleaned, True)

        # 有 validator 配置但没有 pattern（如 place_date）→ 回退到内置规则
        if not pattern and not strip:
            pass  # fall through to built-in
        else:
            return (text_upper.replace(',', '').strip(), False)

    # --- 内置硬编码规则（向后兼容） ---
    if field_name == "bl_no":
        clean = text_upper.replace(' ', '')
        m = re.search(r'[A-Z]{2,4}\d{6,10}', clean)
        return (m.group(0), True) if m else (text, False)

    elif field_name in ("total_gross_weight",):
        clean = re.sub(r'\s*(KGS?|TONS?|KG)\s*$', '', text_upper).strip()
        m = re.search(r'[\d,]+\.?\d*', clean)
        return (m.group(0).replace(',', ''), True) if m else (text, False)

    elif field_name == "total_measurement":
        clean = re.sub(r'\s*CBM\s*$', '', text_upper).strip()
        m = re.search(r'[\d,]+\.?\d*', clean)
        return (m.group(0).replace(',', ''), True) if m else (text, False)

    elif field_name == "issue_date":
        m = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text)
        return (m.group(0), True) if m else (text, False)

    elif field_name == "issue_place":
        cleaned = re.sub(r',?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*$', '', text).strip()
        cleaned = cleaned.rstrip(',').strip()
        return (cleaned, True) if cleaned else (text, False)

    # 默认：返回原值
    return (text, True)


# ================================================================
# 标签检测
# ================================================================

# 短标签关键词（英文大写，通常是缩写标签而非实际数据）
_SHORT_LABELS = {'POL', 'POD', 'POR', 'NO', 'NOS', 'QTY', 'PKG', 'PKGS',
                  'CBM', 'KGS', 'SEAL', 'CNTR', 'CTNR', 'VGM',
                  'B/L', 'BL', 'G.W.', 'N.W.'}

# 表头关键词黑名单（表格列头等，不应作为字段值）
_TABLE_HEADER_WORDS = {
    'CONTAINER NO.', 'SEAL NO.', 'QTY', 'PACKAGE', 'PKG',
    'DESCRIPTION OF GOODS', 'GROSS WEIGHT', 'MEASUREMENT',
    'NO.', 'MARKS & NOS', 'G.W.(KGS)', 'MEASUREMENT(CBM)',
    'DESCRIPTION', 'CONTAINER', 'SEAL', 'WEIGHT',
    'TOTAL', 'TOTAL GROSS', 'TOTAL MEASUREMENT',
}

# 已知英文字段标签 — 独立出现时必定是标签（不区分大小写）
# 来源：所有版式的字段锚点，排除已有规则覆盖的项
_KNOWN_LABEL_TEXTS = {
    # 托运相关
    'SHIPPER', 'CONSIGNEE',
    # 通知相关
    'NOTIFY', 'NOTIFY PARTY',
    # 提单号
    'B/L NO', 'B/L NO.', 'BL NO', 'BL NO.',
    # 运输相关
    'VESSEL', 'VOYAGE', 'VOYAGE NO', 'VOYAGE NO.',
    'PORT OF LOADING', 'PORT OF DISCHARGE',
    'PLACE OF RECEIPT', 'PLACE OF DELIVERY', 'DELIVERY',
    # 汇总相关
    'TOTAL GROSS WEIGHT', 'TOTAL MEASUREMENT',
    'TOTAL GROSS', 'GROSS WEIGHT', 'MEASUREMENT',
    # 费用
    'FREIGHT', 'FREIGHT & CHARGES', 'FREIGHT AND CHARGES',
    # 签发
    'PLACE OF ISSUE', 'DATE OF ISSUE', 'ISSUE PLACE',
    'PLACE & DATE OF ISSUE', 'PLACE AND DATE OF ISSUE',
    # 货物表格
    'DESCRIPTION OF GOODS', 'MARKS & NOS', 'MARKS AND NOS',
    'CONTAINER NO', 'CONTAINER NO.', 'SEAL NO', 'SEAL NO.',
    'BILL OF LADING',
    # 通用
    'CARRIER', 'GROSS',
}

# 中文字段标签关键词 — 出现在短文本中则判定为标签
# 防止 "订舱号 B/L"、"托运人信息" 等被误当值
_CHINESE_LABEL_KW = [
    '托运人', '收货人', '收货方', '通知方', '通知人',
    '提单号', '订舱号', '装货港', '卸货港', '收货地', '交货地',
    '船名', '航次', '总毛重', '总体积', '运费条款', '运费',
    '签发地', '签发日期', '日期', '箱号', '封号', '件数', '包装', '货名',
    '毛重', '体积',
    # 报关单 / 入库单等
    '海关编号', '申报日期', '经营单位', '进口口岸', '原产国',
    '收货单位', '运输方式', '商品名称', '合同号', '外汇码',
    '报关单', '入库单', '批准文号', '成交方式', '起运国',
    '数量及单位', '征免', '备案号', '境内目的地',
]


def _is_label_residue(text):
    """检测文本是否像是标签残片而非实际值（如 "Place & Date of"）"""
    t = text.strip().upper()
    _ANCHOR_PATTERNS = [
        "PLACE OF", "DATE OF", "& DATE", "PORT OF", "BILL OF",
        "DESCRIPTION OF", "& CHARGES", "PLACE &", "DATE &",
    ]
    return any(kw in t for kw in _ANCHOR_PATTERNS)


def _looks_like_label(text):
    """
    判断 OCR 文本是否看起来像是标签/表头而非实际数据值

    设计原则：宁可漏过标签，也不能误杀数据。所以标签检测偏保守。
    """
    text = text.strip()
    text_upper = text.upper().strip()

    if not text or len(text) < 1:
        return True

    # 1) 以冒号结尾（半角 : 或全角 ：） + 较短 → 典型标签
    if (text.endswith(':') or text.endswith('：')) and len(text) < 30:
        return True

    # 2) 匹配纯字母+冒号模式 (e.g., "POL:", "P.O.D.:")
    if re.match(r'^[A-Za-z\s/&.]+[:：]\s*$', text):
        return True

    # 3) 已知表头关键词
    if text_upper in _TABLE_HEADER_WORDS:
        return True

    # 4) 纯中文短文本不再直接判为标签。
    #    报关单里“韩国”“海运”“纺织品”这类值也很短；是否标签交给
    #    后面的中文锚点关键词规则判断，避免误杀人工反哺后的真实值。

    # 5) 极短文本（≤5字符）且是已知缩写标签
    #    直接查 _SHORT_LABELS 集合，不依赖 isalpha()（因为 "B/L" 含斜杠）
    if len(text_upper) <= 5 and text_upper in _SHORT_LABELS:
        return True

    # 6) 包含中文锚点关键词的短文本（< 20 字）→ 标签
    #    如 "订舱号 B/L"、"托运人信息"、"装货港 POL" 等
    #    OCR 常把中英混合标签拆开导致冒号丢失，此规则兜底
    #    注意：阈值 20 字确保不会误杀长公司名
    if len(text) < 20:
        for kw in _CHINESE_LABEL_KW:
            if kw in text:
                return True

    # 7) 精确匹配已知英文字段标签 → 标签
    #    防止 "SHIPPER"、"VESSEL"、"PORT OF LOADING" 等
    #    独立出现时被误当值（OCR 漏掉冒号或标签-值拆分后的残片）
    if text_upper in _KNOWN_LABEL_TEXTS:
        return True

    return False


# ================================================================
# 字段提取器
# ================================================================

class FieldExtractor:
    """
    锚点法字段提取器

    配置来源（优先级从高到低）：
      1. 构造时传入的 config_path 指定的 YAML 文件
      2. 同目录下的 config.yaml
      3. 内置默认值 _DEFAULT_FIELDS + _DEFAULT_TEMPLATES

    用法:
        extractor = FieldExtractor()                # 自动加载 config.yaml
        extractor = FieldExtractor(config_path="custom.yaml")  # 指定配置
        result = extractor.extract(regions, image_size)
    """

    def __init__(self, config_path=None, fuzzy_threshold=0.55):
        """
        :param config_path: YAML 配置文件路径（可选，默认同目录 config.yaml）
        :param fuzzy_threshold: 模糊匹配阈值 (0~1)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.config = self._load_config(config_path)
        self._last_template_scores = {}
        self._last_extraction_debug = {}

    # ============================================================
    # 配置加载
    # ============================================================

    @staticmethod
    def _load_config(config_path=None):
        """加载 YAML 配置，失败则返回内置默认值"""
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")

        if _HAS_YAML and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if cfg and isinstance(cfg, dict):
                    # 检测旧格式：有顶层 "fields" key 则自动迁移
                    if "fields" in cfg:
                        cfg = FieldExtractor._migrate_config(cfg)
                    return cfg
            except Exception:
                pass

        return {
            "templates": FieldExtractor._migrate_default_templates_to_source_schema(
                dict(_DEFAULT_TEMPLATES_CONFIG)
            ),
            "validators": dict(_DEFAULT_VALIDATORS),
            "field_defaults": dict(_DEFAULT_FIELD_DEFAULTS),
        }

    @staticmethod
    def _migrate_default_templates_to_source_schema(templates):
        """Keep built-in fallback templates aligned with source-label schema."""
        mappings = {
            "maersk_style": {
                "shipper": ("Shipper", "Shipper"),
                "consignee": ("Consignee", "Consignee"),
                "notify_party": ("Notify Party", "Notify Party"),
                "bl_no": ("B/L No.", "B/L No."),
                "pol": ("Port of Loading", "Port of Loading"),
                "pod": ("Port of Discharge", "Port of Discharge"),
                "por": ("Place of Receipt", "Place of Receipt"),
                "delivery": ("Place of Delivery", "Place of Delivery"),
                "vessel": ("Vessel", "Vessel"),
                "voyage": ("Voyage No.", "Voyage No."),
                "total_gross_weight": ("Total Gross Weight", "Total Gross Weight"),
                "total_measurement": ("Total Measurement", "Total Measurement"),
                "freight": ("Freight & Charges", "Freight & Charges"),
                "issue_place": ("Place & Date of Issue", "Place & Date of Issue"),
            },
            "cosco_style": {
                "shipper": ("托运人 Shipper", "托运人 Shipper"),
                "bl_no": ("订舱号 B/L No.", "订舱号 B/L No."),
                "consignee": ("收货人 Consignee", "收货人 Consignee"),
                "notify_party": ("通知方 Notify", "通知方 Notify"),
                "pol": ("装货港 POL", "装货港 POL"),
                "pod": ("卸货港 POD", "卸货港 POD"),
                "vessel": ("船名 Vessel", "船名 Vessel"),
                "voyage": ("航次 Voyage", "航次 Voyage"),
                "por": ("收货地 POR", "收货地 POR"),
                "delivery": ("交货地 Delivery", "交货地 Delivery"),
                "freight": ("运费条款", "运费条款"),
                "issue_place": ("签发地 & 日期", "签发地 & 日期"),
            },
            "simple_style": {
                "shipper": ("Shipper", "Shipper"),
                "bl_no": ("B/L No.", "B/L No."),
                "consignee": ("Consignee", "Consignee"),
                "notify_party": ("Notify", "Notify"),
                "pol": ("POL", "POL"),
                "pod": ("POD", "POD"),
                "vessel": ("Vessel", "Vessel"),
                "voyage": ("Voyage", "Voyage"),
                "freight": ("Freight", "Freight"),
                "issue_place": ("Issue Place", "Issue Place"),
                "issue_date": ("Date", "Date"),
            },
            "funsd_public": {
                "sender": ("FROM", "FROM"),
                "recipient": ("TO", "TO"),
                "subject": ("SUBJECT", "SUBJECT"),
                "division": ("DIVISION", "DIVISION"),
                "region": ("REGION", "REGION"),
            },
            "real_scan": {
                "tracking_no": ("运单号", "运单号"),
                "sender_name": ("寄件人", "寄件人"),
                "sender_phone": ("寄件电话", "寄件电话"),
                "sender_addr": ("寄件地址", "寄件地址"),
                "recipient_name": ("收件人", "收件人"),
                "recipient_phone": ("收件电话", "收件电话"),
                "recipient_addr": ("收件地址", "收件地址"),
                "order_no": ("订单号", "订单号"),
                "total_amount": ("合计金额", "合计金额"),
                "courier": ("快递公司", "快递公司"),
            },
        }

        migrated = {}
        for template_name, template in templates.items():
            mapping = mappings.get(template_name)
            if not mapping:
                migrated[template_name] = template
                continue

            old_fields = template.get("fields", {})
            new_fields = {}
            new_output = []
            for old_key, (new_key, label) in mapping.items():
                field_cfg = old_fields.get(old_key)
                if not field_cfg:
                    continue
                field_cfg = dict(field_cfg)
                field_cfg["label"] = label
                field_cfg["canonical_key"] = old_key
                new_fields[new_key] = field_cfg
                new_output.append(new_key)
            new_template = dict(template)
            new_template["fields"] = new_fields
            new_template["output"] = new_output
            migrated[template_name] = new_template
        return migrated

    @staticmethod
    def _migrate_config(old_cfg):
        """将旧 4-section 格式转为新自包含模板格式（内存迁移，不改磁盘）"""
        old_labels = old_cfg.get("field_labels", {})
        old_fields = old_cfg.get("fields", {})
        old_templates = old_cfg.get("templates", {})
        output_templates = old_cfg.get("output_schema", {}).get("templates", {})
        overrides = old_cfg.get("template_overrides", {})

        new_templates = {}
        for tname, t_entry in old_templates.items():
            if isinstance(t_entry, dict):
                keywords = t_entry.get("keywords", [])
            else:
                keywords = []

            has_table = output_templates.get(tname, {}).get("table", False)
            output_fields = output_templates.get(tname, {}).get("fields", [])

            fields = {}
            for fname in output_fields:
                fdef = dict(old_fields.get(fname, {}))
                tpl_overrides = overrides.get(tname, {}).get("fields", {}).get(fname, {})
                fdef.update(tpl_overrides)
                fdef["label"] = old_labels.get(fname, fname)
                fields[fname] = fdef

            new_templates[tname] = {
                "keywords": keywords,
                "has_table": has_table,
                "fields": fields,
                "output": list(output_fields),
            }

        return {
            "templates": new_templates,
            "validators": old_cfg.get("validators", {}),
            "field_defaults": old_cfg.get("output_schema", {}).get("field_defaults", {
                "value": "", "cleaned": "", "confidence": 0.0,
                "status": "not_found", "anchor_text": "", "rect": [0, 0, 0, 0],
            }),
        }

    def reload_config(self, config_path=None):
        """重新加载配置（用于测试或动态更新）"""
        self.config = self._load_config(config_path)

    # ---- 从配置中提取的便捷属性 ----

    def get_template_fields(self, template_name):
        """获取指定版式的字段定义 {field_name: {label, anchors, position, ...}}"""
        tpl = self.config.get("templates", {}).get(template_name, {})
        return tpl.get("fields", {})

    @property
    def template_keywords(self):
        """版式关键词 {template_name: [keyword, ...]}"""
        templates = self.config.get("templates", {})
        return {
            name: t.get("keywords", [])
            for name, t in templates.items()
            if t.get("enabled", True) is not False
        }

    @property
    def validators_cfg(self):
        """正则校验规则 {name: {pattern, strip_suffix, ...}}"""
        return self.config.get("validators", {})

    def get_field_config(self, field_name, template_name=None):
        """获取单个字段的完整配置，可选限定版式"""
        if template_name:
            tpl_fields = self.get_template_fields(template_name)
            return dict(tpl_fields.get(field_name, {}))
        # 未指定版式时，搜索所有版式
        for tpl_cfg in self.config.get("templates", {}).values():
            fdef = tpl_cfg.get("fields", {}).get(field_name)
            if fdef:
                return dict(fdef)
        return {}

    # ================================================================
    # 主入口
    # ================================================================

    def extract(self, regions, image_size, blocks=None):
        """
        从版面分析结果中提取字段（只提取当前版式的字段）

        :param regions: {"header": [...], "body": [...], "table": [...]}
        :param image_size: [width, height]
        :param blocks: 可选，全部 OCR 块的平铺列表
        :return: {
            "fields": {field_name: {value, cleaned, confidence, anchor_text, rect}, ...},
            "table": [[cell, ...], ...],
            "template": "maersk_style" | "unknown"
        }
        """
        if blocks is None:
            blocks = regions.get("header", []) + regions.get("body", []) + regions.get("table", [])

        if not blocks:
            return {"fields": {}, "table": [], "template": "unknown"}

        # 版式识别
        template = self._detect_template(blocks, image_size)

        # 从当前模板读取字段定义（各版式独立，不再依赖全局 field_defs）
        tpl_config = self.config.get("templates", {}).get(template, {})
        tpl_fields = tpl_config.get("fields", {})
        output_list = tpl_config.get("output", list(tpl_fields.keys()))

        body_blocks = regions.get("header", []) + regions.get("body", [])
        table_blocks = regions.get("table", [])

        # 提取字段（只迭代当前版式定义的字段）
        fields = {}
        used_value_ids = set()
        self._last_extraction_debug = {
            "template_scores": self._last_template_scores,
            "fields": {},
        }

        for field_name, cfg in tpl_fields.items():
            if field_name not in output_list:
                continue
            search_in = cfg.get("search_in", "body")
            search_pool = blocks if search_in == "all" else body_blocks
            result = self._extract_field(
                field_name, cfg, search_pool, used_value_ids
            )
            if result:
                fields[field_name] = result
                for bid in result.get("_block_ids", [id(result["_block"])]):
                    used_value_ids.add(bid)

        # 提取表格
        table_data = self._extract_table(table_blocks)
        table_layout = tpl_config.get("table_layout")
        if self._should_use_learned_table_layout(table_data, table_layout):
            learned_table = self._extract_table_with_learned_layout(
                blocks,
                table_layout,
                image_size,
                table_headers=tpl_config.get("table_headers"),
            )
            if learned_table:
                table_data = learned_table

        # 清理内部字段
        for v in fields.values():
            v.pop("_block", None)

        result = {
            "fields": fields,
            "table": table_data,
            "template": template,
        }

        normalized = self.normalize(result, img_size=image_size, blocks=blocks)
        normalized["debug"] = {
            "extraction": self._last_extraction_debug,
            "note": "FUNSD is currently treated as fixed-schema compatibility data; a future generic form mode should output question-answer pairs.",
        }
        return normalized

    def normalize(self, raw_result, img_size=None, blocks=None):
        """
        按当前版式的 output 列表规范化输出

        保证:
          1. 版式要求的字段必定出现（未提取 → status: "not_found"）
          2. 每个字段格式统一: {label, value, cleaned, confidence, status, anchor, rect}
          3. 添加 meta 元信息块
        """
        template = raw_result.get("template", "unknown")
        raw_fields = raw_result.get("fields", {})
        table = raw_result.get("table", {})

        defaults = dict(self.config.get("field_defaults", {
            "value": "", "cleaned": "", "confidence": 0.0,
            "status": "not_found", "anchor_text": "", "rect": [0, 0, 0, 0],
        }))

        tpl_config = self.config.get("templates", {}).get(template, {})
        all_fields = tpl_config.get("fields", {})
        expected_fields = tpl_config.get("output", list(all_fields.keys()))

        normalized_fields = {}
        corrections = raw_fields.pop("_corrections", {}) if isinstance(raw_fields, dict) else {}

        for fname in expected_fields:
            info = raw_fields.get(fname)
            fdef = all_fields.get(fname, {})
            if info and isinstance(info, dict):
                normalized_fields[fname] = {
                    "label": fdef.get("label", fname),
                    "canonical_key": fdef.get("canonical_key", fname),
                    "value": info.get("value", defaults["value"]),
                    "cleaned": info.get("cleaned", defaults["cleaned"]),
                    "confidence": info.get("confidence", defaults["confidence"]),
                    "status": "extracted",
                    "anchor": info.get("anchor_text", defaults["anchor_text"]),
                    "rect": info.get("rect", defaults["rect"]),
                }
            else:
                entry = dict(defaults)
                entry["label"] = fdef.get("label", fname)
                entry["canonical_key"] = fdef.get("canonical_key", fname)
                normalized_fields[fname] = entry

        # 合并校正值
        for fname, corr_val in corrections.items():
            if fname in normalized_fields:
                normalized_fields[fname]["corrected"] = corr_val
                normalized_fields[fname]["status"] = "corrected"

        # 保留 Schema 外额外提取到的字段（如 OCR 从标签+值合并块额外解析出的字段）
        for fname, info in raw_fields.items():
            if fname not in normalized_fields and isinstance(info, dict):
                extra = dict(defaults)
                extra.update({k: info.get(k, defaults[k]) for k in defaults
                              if k in ("value", "cleaned", "confidence", "anchor_text", "rect")})
                extra["status"] = "extracted"
                fdef = all_fields.get(fname, {})
                extra["label"] = fdef.get("label", fname)
                extra["canonical_key"] = fdef.get("canonical_key", fname)
                normalized_fields[fname] = extra

        meta = {
            "template": template,
            "fields_total": len(normalized_fields),
            "fields_extracted": sum(
                1 for f in normalized_fields.values()
                if f["status"] != "not_found"
            ),
            "table_rows": len(table.get("rows", [])),
        }
        if img_size:
            meta["image_size"] = list(img_size)
        if blocks is not None:
            meta["ocr_blocks"] = len(blocks)

        return {
            "meta": meta,
            "fields": normalized_fields,
            "table": table,
            "template": template,
        }

    # ================================================================
    # 版式识别
    # ================================================================

    def _detect_template(self, blocks, image_size=None):
        """Select learned templates by layout signature and legacy ones by keywords."""
        all_text = " ".join(b["text"] for b in blocks).upper()

        scores = {}
        candidates = {}
        templates = self.config.get("templates", {})
        for tpl, template_cfg in templates.items():
            if template_cfg.get("enabled", True) is False:
                continue

            detection = template_cfg.get("detection")
            if isinstance(detection, dict) and detection.get("mode") == "anchor_layout":
                info = score_anchor_layout_signature(detection, blocks, image_size)
                scores[tpl] = info
                if info.get("accepted"):
                    candidates[tpl] = info

            keywords = template_cfg.get("keywords", [])
            if not keywords:
                continue
            total_weight = 0.0
            matched_weight = 0.0
            matched = []
            for kw in keywords:
                kw_upper = str(kw).upper().strip()
                if not kw_upper:
                    continue
                weight = min(3.0, 1.0 + len(kw_upper) / 14.0)
                total_weight += weight
                if kw_upper in all_text:
                    matched_weight += weight
                    matched.append(kw)

            if matched:
                confidence = matched_weight / max(total_weight, 1.0)
                keyword_info = {
                    "score": round(confidence, 4),
                    "matched": matched,
                    "matched_count": len(matched),
                    "keywords_count": len(keywords),
                    "mode": "keywords",
                }
                if tpl not in candidates:
                    scores[tpl] = keyword_info
                    candidates[tpl] = keyword_info

        self._last_template_scores = scores
        if not candidates:
            return "unknown"

        ranked = sorted(
            candidates.items(),
            key=lambda item: (
                item[1].get("mode") == "anchor_layout",
                item[1]["score"],
            ),
            reverse=True,
        )
        best_tpl, best_info = ranked[0]
        best_score = best_info["score"]
        second_score = ranked[1][1]["score"] if len(ranked) > 1 else 0.0
        gap = best_score - second_score

        if best_info.get("mode") == "anchor_layout":
            return best_tpl

        # One strong unique keyword is enough for known logistics templates, but
        # weak/conflicting evidence should stay unknown instead of forcing a template.
        if best_score < 0.18:
            return "unknown"
        if best_info["matched_count"] == 1 and gap < 0.03:
            return "unknown"
        if best_info["matched_count"] == 1 and best_score < 0.28 and gap < 0.08:
            return "unknown"
        return best_tpl

    # ================================================================
    # 单字段提取
    # ================================================================

    def _extract_field(self, field_name, cfg, search_pool, used_value_ids):
        """
        尝试从 search_pool 中提取指定字段

        策略:
          1. 生成 inline / right / below 候选
          2. 按锚点匹配、几何位置、OCR 置信度、校验、占用冲突统一打分
          3. 选择最高分候选，而不是第一个可用候选

        :return: dict 或 None
        """
        anchors = cfg.get("anchors", [])
        position = cfg.get("position", "right")
        validator_name = cfg.get("validator")
        validator_cfg = self.validators_cfg.get(validator_name) if validator_name else None
        allow_shared = bool(cfg.get("allow_shared"))
        field_debug = {
            "anchors": anchors,
            "candidates": [],
            "rejected": [],
            "selected": None,
        }
        self._last_extraction_debug["fields"][field_name] = field_debug

        # Step 1: 找锚点块（按匹配分数排序）
        anchor_matches = self._find_anchor_blocks(search_pool, anchors)
        scope_anchors = cfg.get("scope_anchors") or []
        if scope_anchors:
            anchor_matches = self._filter_anchor_matches_by_scope(
                search_pool,
                anchor_matches,
                scope_anchors,
            )
            field_debug["scope_anchors"] = scope_anchors
        if not anchor_matches:
            field_debug["rejected"].append({"reason": "no_anchor_match"})
            return None

        candidates = []
        for anchor_block, score, matched_anchor in anchor_matches:
            # --- 策略 1: 从锚点块内部提取（标签+值合并） ---
            inline_value = self._extract_inline_value(anchor_block, matched_anchor)
            if inline_value:
                cand = self._build_value_candidate(
                    field_name, cfg, anchor_block, score, matched_anchor,
                    anchor_block, inline_value.strip(), "inline", 1.0,
                    used_value_ids, allow_shared, validator_cfg, validator_name,
                    search_pool,
                )
                (candidates if cand.get("accepted") else field_debug["rejected"]).append(cand)

            for geom_score, value_block in self._find_learned_offset_candidates(
                anchor_block, search_pool, cfg.get("learned_value_offset")
            ):
                cand = self._build_value_candidate(
                    field_name, cfg, anchor_block, score, matched_anchor,
                    value_block, value_block["text"].strip(), "learned_offset", geom_score,
                    used_value_ids, allow_shared, validator_cfg, validator_name,
                    search_pool,
                )
                cand["reasons"].append("learned_offset")
                (candidates if cand.get("accepted") else field_debug["rejected"]).append(cand)

            # --- 策略 2/3: 外部值块 ---
            if position in ("right", "either"):
                for geom_score, value_block in self._find_value_right_candidates(
                    anchor_block, search_pool
                ):
                    cand = self._build_value_candidate(
                        field_name, cfg, anchor_block, score, matched_anchor,
                        value_block, value_block["text"].strip(), "right", geom_score,
                        used_value_ids, allow_shared, validator_cfg, validator_name,
                        search_pool,
                    )
                    (candidates if cand.get("accepted") else field_debug["rejected"]).append(cand)

            if position in ("below", "either"):
                for geom_score, value_block in self._find_value_below_candidates(
                    anchor_block, search_pool
                ):
                    cand = self._build_value_candidate(
                        field_name, cfg, anchor_block, score, matched_anchor,
                        value_block, value_block["text"].strip(), "below", geom_score,
                        used_value_ids, allow_shared, validator_cfg, validator_name,
                        search_pool,
                    )
                    (candidates if cand.get("accepted") else field_debug["rejected"]).append(cand)

        if not candidates:
            return None

        candidates.sort(key=lambda c: c["score"], reverse=True)
        field_debug["candidates"] = [self._candidate_debug(c) for c in candidates[:8]]
        best = candidates[0]
        field_debug["selected"] = self._candidate_debug(best)

        return {
            "value": best["raw_value"],
            "cleaned": best["cleaned"],
            "regex_valid": best["regex_valid"],
            "confidence": round(best["score"], 4),
            "anchor_text": best["anchor"],
            "rect": best["rect"],
            "bbox": best.get("bbox", []),
            "_block": best["candidate_block"],
            "_block_ids": best.get("block_ids", [id(best["candidate_block"])]),
        }

    def _build_value_candidate(
        self, field_name, cfg, anchor_block, anchor_score, matched_anchor,
        value_block, raw_value, strategy, geom_score, used_value_ids,
        allow_shared, validator_cfg, validator_name, search_pool,
    ):
        raw_value = (raw_value or "").strip()
        reasons = [f"strategy:{strategy}", f"anchor:{matched_anchor}"]
        reject_reasons = []

        if not raw_value:
            reject_reasons.append("empty_value")

        raw_upper = raw_value.upper()
        if validator_name == "weight" and "CBM" in raw_upper:
            reject_reasons.append("weight_candidate_contains_cbm")
        if validator_name == "volume" and ("KGS" in raw_upper or "KG" in raw_upper):
            reject_reasons.append("volume_candidate_contains_weight_unit")

        cleaned = _clean_text(raw_value)
        if cleaned is None:
            reject_reasons.append("looks_like_label_or_empty")
            cleaned = raw_value

        if _looks_like_label(raw_value):
            reject_reasons.append("candidate_looks_like_label")
        if _is_label_residue(raw_value):
            reject_reasons.append("candidate_label_residue")

        cleaned_value, regex_ok = validate_and_clean(
            field_name, cleaned,
            validator_cfg=validator_cfg, field_cfg=cfg
        )

        value_pattern = cfg.get("value_pattern")
        pattern_ok = None
        if value_pattern:
            pattern_ok = bool(re.search(str(value_pattern), raw_value, re.IGNORECASE))
            reasons.append("value_pattern_match" if pattern_ok else "value_pattern_miss")

        block_ids = [id(value_block)]
        merged_blocks = [value_block]
        rect = list(value_block["rect"])
        bbox = value_block.get("bbox", [])
        if cfg.get("multi_line") and strategy in ("right", "below"):
            merged_value, merged_blocks, rect = self._merge_multiline_value(
                value_block, search_pool
            )
            if merged_value != raw_value:
                raw_value = merged_value
                cleaned = _clean_text(raw_value) or raw_value
                cleaned_value, regex_ok = validate_and_clean(
                    field_name, cleaned,
                    validator_cfg=validator_cfg, field_cfg=cfg
                )
                block_ids = [id(b) for b in merged_blocks]
                reasons.append("multi_line_merge")

        used_conflict = any(bid in used_value_ids for bid in block_ids)
        if used_conflict and not allow_shared:
            reasons.append("used_value_penalty")
        elif used_conflict and allow_shared:
            reasons.append("shared_value_allowed")

        ocr_conf = value_block.get("confidence", 0.8)
        has_validator_constraint = bool(validator_name or validator_cfg or value_pattern)
        validation_score = 0.0
        if regex_ok and has_validator_constraint:
            validation_score += 0.12
            reasons.append("validator_ok")
        elif has_validator_constraint:
            validation_score -= 0.10
            reasons.append("validator_miss")
        if pattern_ok is True:
            validation_score += 0.10
        elif pattern_ok is False:
            validation_score -= 0.10

        strategy_bonus = 0.06 if strategy == "inline" else 0.0
        usage_penalty = 0.18 if used_conflict and not allow_shared else 0.0
        label_penalty = 0.10 if _looks_like_label(raw_value) else 0.0

        score = (
            anchor_score * 0.32
            + geom_score * 0.28
            + ocr_conf * 0.22
            + validation_score
            + strategy_bonus
            - usage_penalty
            - label_penalty
        )
        score = max(0.0, min(1.0, score))

        candidate = {
            "field": field_name,
            "anchor": matched_anchor,
            "anchor_block": anchor_block,
            "candidate_block": value_block,
            "strategy": strategy,
            "raw_value": raw_value,
            "cleaned": cleaned_value,
            "regex_valid": regex_ok,
            "score": round(score, 4),
            "reasons": reasons,
            "reject_reasons": reject_reasons,
            "rect": rect,
            "bbox": bbox,
            "block_ids": block_ids,
            "accepted": not reject_reasons and score >= 0.25,
        }
        return candidate

    @staticmethod
    def _candidate_debug(candidate):
        block = candidate.get("candidate_block", {})
        anchor_block = candidate.get("anchor_block", {})
        return {
            "field": candidate.get("field"),
            "anchor": candidate.get("anchor"),
            "anchor_text": anchor_block.get("text", ""),
            "strategy": candidate.get("strategy"),
            "value": candidate.get("raw_value"),
            "score": candidate.get("score"),
            "reasons": candidate.get("reasons", []),
            "reject_reasons": candidate.get("reject_reasons", []),
            "rect": block.get("rect", candidate.get("rect", [])),
        }

    def _merge_multiline_value(self, first_block, candidates):
        """向下合并同列连续文本块，用于地址/公司名等多行字段。"""
        x1, y1, x2, y2 = first_block["rect"]
        first_h = max(y2 - y1, 5)
        merged = [first_block]

        below = sorted(
            (b for b in candidates if id(b) != id(first_block) and b["rect"][1] >= y2 - 2),
            key=lambda b: (b["rect"][1], b["rect"][0]),
        )
        last_y2 = y2
        for block in below:
            bx1, by1, bx2, by2 = block["rect"]
            if _looks_like_label(block["text"]) or _is_label_residue(block["text"]):
                break
            if by1 - last_y2 > max(first_h * 1.6, 60):
                break
            if abs(bx1 - x1) > max((x2 - x1) * 0.8, 120):
                continue
            merged.append(block)
            last_y2 = max(last_y2, by2)
            if len(merged) >= 4:
                break

        text = " ".join(b["text"].strip() for b in merged if b["text"].strip())
        xs1 = [b["rect"][0] for b in merged]
        ys1 = [b["rect"][1] for b in merged]
        xs2 = [b["rect"][2] for b in merged]
        ys2 = [b["rect"][3] for b in merged]
        rect = [min(xs1), min(ys1), max(xs2), max(ys2)]
        return text, merged, rect

    @staticmethod
    def _extract_inline_value(anchor_block, matched_anchor):
        """
        从锚点 OCR 块内部提取值（处理标签+值合并在同一文本块的情况）

        例如: OCR 输出 "Vessel: ONE HARBOUR" 作为一整块，
              锚点 "Vessel" 匹配到这一块 → 提取 "ONE HARBOUR"

        :return: 提取的值字符串，或 None
        """
        full_text = anchor_block["text"].strip()
        text_upper = full_text.upper()
        anchor_upper = matched_anchor.upper().strip()

        # 找到锚点在文本中的位置
        idx = text_upper.find(anchor_upper)
        if idx < 0:
            return None

        # 取锚点之后的文本
        suffix = full_text[idx + len(matched_anchor):]
        ascii_label = bool(re.search(r"[A-Za-z]", matched_anchor)) and matched_anchor.isascii()
        has_separator = bool(re.match(r"^\s*[:：]", suffix)) or matched_anchor.rstrip().endswith((":", "："))
        if ascii_label and not has_separator:
            return None

        remainder = suffix.strip()

        # 去掉常见的分隔符（冒号、空格、破折号等）
        remainder = re.sub(r'^[\s:、：\-—―]+', '', remainder)

        # 去掉末尾的单位（KGS、CBM 等保留，不在这里处理）
        if not remainder or len(remainder) < 1:
            return None

        # 如果剩余文本看起来是另一个标签，跳过
        if _looks_like_label(remainder):
            return None

        # 拒绝标签延续：剩余文本以 & / 和 开头（e.g. "& 日期", "/ Shipper Information"）
        if re.match(r'^[&/和,，\s]+', remainder.strip()):
            return None

        # 剩余文本太短且是纯符号 → 不是值
        if len(remainder.strip()) <= 2 and not remainder.strip().isalnum():
            return None

        # 拒绝纯介词/冠词等无意义短词（"of", "the", "a", "&" 等）
        _STOPWORDS = {"OF", "THE", "A", "AN", "IN", "ON", "AT", "TO", "BY", "FOR",
                       "AND", "OR", "IS", "IT", "AS", "NO", "BE", "WE", "HE", "&"}
        if remainder.strip().upper() in _STOPWORDS:
            return None

        # 拒绝像标签残片的文本：含 "of Issue" / "of Loading" / "& Date" 等
        _LABEL_RESIDUE = {"OF ISSUE", "OF LOADING", "OF DISCHARGE", "OF RECEIPT",
                           "OF DELIVERY", "& DATE", "DATE OF", "OF GOODS",
                           "& CHARGES", "NO.", "& DATE OF", "PLACE &"}
        if remainder.strip().upper() in _LABEL_RESIDUE:
            return None

        return remainder

    # ================================================================
    # 锚点匹配
    # ================================================================

    def _find_anchor_blocks(self, blocks, anchors):
        """
        在所有 OCR 块中搜索匹配锚点关键词的块

        :return: [(block, score, matched_anchor), ...]  按分数降序
        """
        candidates = []

        for block in blocks:
            text = block["text"].strip()
            if not text:
                continue

            text_upper = text.upper()

            for anchor in anchors:
                anchor_upper = anchor.upper().strip()

                # 1) 直接子串匹配（高优先级）
                if _contains_direct_anchor(text_upper, anchor_upper):
                    # 锚点占文本比例越高 → 越可能是真正的标签块
                    # 防止 "托运人" 匹配到 "托运人信息" 这类标题块
                    len_ratio = len(anchor) / max(len(text), 1)
                    ratio_bonus = 0.15 * min(len_ratio * 1.5, 1.0)
                    score = 0.85 + ratio_bonus
                    candidates.append((block, score, anchor))
                    break

                # 2) 模糊匹配：OCR 容错
                if _is_short_ascii_anchor(anchor_upper):
                    continue
                sim = self._text_similarity(text_upper, anchor_upper)
                threshold = self.fuzzy_threshold
                if anchor_upper.isascii() and re.search(r"[A-Z]", anchor_upper):
                    threshold = max(threshold, 0.78)
                if sim >= threshold:
                    candidates.append((block, sim, anchor))
                    break

        # 去重：每个 block 只保留最高分
        best = {}
        for block, score, anchor in candidates:
            idx = id(block)
            if idx not in best or score > best[idx][0]:
                best[idx] = (score, block, anchor)

        result = [(b, s, a) for _, (s, b, a) in
                  sorted(best.items(), key=lambda x: x[1][0], reverse=True)]
        return result

    def _filter_anchor_matches_by_scope(self, blocks, anchor_matches, scope_anchors):
        """Keep repeated child anchors only when their nearest preceding section matches."""
        if not anchor_matches or not scope_anchors:
            return anchor_matches

        desired_scopes = {self._normalize_scope_anchor(scope) for scope in scope_anchors}
        family_scopes = self._scope_anchor_family(scope_anchors)
        scope_matches = self._find_anchor_blocks(blocks, family_scopes)
        if not scope_matches:
            return []

        filtered = []
        for anchor_block, score, matched_anchor in anchor_matches:
            best_scope = self._nearest_preceding_scope(anchor_block, scope_matches)
            if not best_scope:
                continue
            _, scope_score, matched_scope = best_scope
            if self._normalize_scope_anchor(matched_scope) not in desired_scopes:
                continue
            filtered.append((anchor_block, min(1.0, score * 0.88 + scope_score * 0.12), matched_anchor))
        return filtered

    @staticmethod
    def _scope_anchor_family(scope_anchors):
        wanted = {FieldExtractor._normalize_scope_anchor(scope) for scope in scope_anchors}
        expanded = list(scope_anchors)
        for family in _SCOPE_ANCHOR_FAMILIES:
            normalized_family = {FieldExtractor._normalize_scope_anchor(scope) for scope in family}
            if wanted & normalized_family:
                for scope in family:
                    if scope not in expanded:
                        expanded.append(scope)
        return expanded

    @staticmethod
    def _normalize_scope_anchor(scope):
        return re.sub(r"\s+", "", str(scope or "")).upper()

    @staticmethod
    def _nearest_preceding_scope(anchor_block, scope_matches):
        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        anchor_cx = (ax1 + ax2) / 2.0
        anchor_cy = (ay1 + ay2) / 2.0
        best = None
        best_distance = None
        for scope_block, score, matched_scope in scope_matches:
            sx1, sy1, sx2, sy2 = scope_block["rect"]
            scope_cx = (sx1 + sx2) / 2.0
            scope_cy = (sy1 + sy2) / 2.0
            if scope_cy > anchor_cy + 4:
                continue
            vertical_gap = max(0.0, ay1 - sy2)
            if vertical_gap > max(320.0, (ay2 - ay1) * 12.0):
                continue
            horizontal_gap = abs(anchor_cx - scope_cx)
            distance = vertical_gap + horizontal_gap * 0.45
            if best_distance is None or distance < best_distance:
                best = (scope_block, score, matched_scope)
                best_distance = distance
        return best

    @staticmethod
    def _text_similarity(text, anchor):
        """
        文本相似度计算

        混合策略：子串匹配优先，LCS 兜底。
        适配 OCR 典型错误：
          - "SHlPPER" vs "SHIPPER" (l→I)
          - "Sh ipper" vs "Shipper" (多余空格)
          - "托运人" vs "托运 人"
        """
        if not text or not anchor:
            return 0.0

        # 去空格后的子串匹配
        text_ns = text.replace(' ', '')
        anchor_ns = anchor.replace(' ', '')
        if (
            not _is_short_ascii_anchor(anchor_ns)
            and (anchor_ns in text_ns or text_ns in anchor_ns)
        ):
            return 0.85

        # SequenceMatcher 基于最长公共子序列
        return SequenceMatcher(None, text, anchor).ratio()

    # ================================================================
    # 值定位 — 同行右侧
    # ================================================================

    def _find_value_right(self, anchor_block, candidates, used_ids=None):
        """兼容旧调用：返回右侧最高分候选块。"""
        found = self._find_value_right_candidates(anchor_block, candidates)
        return found[0][1] if found else None

    def _find_learned_offset_candidates(self, anchor_block, candidates, learned_offset):
        """按反哺学习到的锚点→值块中心偏移优先找候选。"""
        if not isinstance(learned_offset, dict):
            return []
        try:
            dx = float(learned_offset.get("dx", 0.0))
            dy = float(learned_offset.get("dy", 0.0))
            tol_x = max(float(learned_offset.get("tolerance_x", 80.0)), 20.0)
            tol_y = max(float(learned_offset.get("tolerance_y", 45.0)), 15.0)
        except (TypeError, ValueError):
            return []

        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        expected_cx = (ax1 + ax2) / 2.0 + dx
        expected_cy = (ay1 + ay2) / 2.0 + dy

        scored = []
        for block in candidates:
            if id(block) == id(anchor_block):
                continue
            if _looks_like_label(block["text"]) or _is_label_residue(block["text"]):
                continue
            bx1, by1, bx2, by2 = block["rect"]
            block_cx = (bx1 + bx2) / 2.0
            block_cy = (by1 + by2) / 2.0
            nx = abs(block_cx - expected_cx) / tol_x
            ny = abs(block_cy - expected_cy) / tol_y
            distance = (nx * nx + ny * ny) ** 0.5
            if distance > 1.8:
                continue
            score = max(0.0, 1.0 - distance / 1.8)
            if score >= 0.20:
                scored.append((score, block))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _find_value_right_candidates(self, anchor_block, candidates):
        """
        在锚点同行右侧找值块候选

        评分策略 (0~1):
          - Y 中心对齐  权重 0.6  （同行为王）
          - X 邻近      权重 0.3  （越近越好）
          - 非标签      权重 0.1  （不是另一个锚点）

        :return: [(score, block), ...]
        """
        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        anchor_h = max(ay2 - ay1, 5)
        anchor_cy = (ay1 + ay2) / 2.0
        # Relative window: scale with line height and page layout rather than a
        # fixed pixel value, but keep a sane minimum for low-resolution images.
        max_x_gap = max(anchor_h * 14.0, 260.0)

        scored = []

        for block in candidates:
            bid = id(block)
            if bid == id(anchor_block):
                continue

            bx1, by1, bx2, by2 = block["rect"]

            # 必须在锚点右侧（允许微小重叠）
            if bx1 < ax1 - 5:
                continue

            # 排除标签
            if _looks_like_label(block["text"]):
                continue
            # 排除包含锚点关键词的标签残片（"Place & Date of" 等）
            if _is_label_residue(block["text"]):
                continue

            block_h = max(by2 - by1, 5)
            block_cy = (by1 + by2) / 2.0

            # ---- Y 对齐分 (0~1) ----
            # 计算 Y 中心偏差，以锚点高度为单位
            y_diff = abs(block_cy - anchor_cy)
            y_score = max(0.0, 1.0 - y_diff / max(anchor_h, block_h))

            # 至少要有基本的 Y 重叠才能候选
            if y_score < 0.2:
                continue

            # ---- X 邻近分 (0~1) ----
            x_gap = max(0, bx1 - ax2)  # 锚点右边界到值块左边界的距离
            if x_gap > max_x_gap:
                continue
            x_score = max(0.0, 1.0 - x_gap / max_x_gap)

            # ---- 综合分 ----
            score = y_score * 0.6 + x_score * 0.4

            if score > 0.25:  # 最低阈值
                scored.append((score, block))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # ================================================================
    # 值定位 — 紧邻下方
    # ================================================================

    def _find_value_below(self, anchor_block, candidates, used_ids=None):
        """兼容旧调用：返回下方最高分候选块。"""
        found = self._find_value_below_candidates(anchor_block, candidates)
        return found[0][1] if found else None

    def _find_value_below_candidates(self, anchor_block, candidates):
        """
        在锚点紧邻下方找值块候选

        条件:
          1. X 左边界与锚点左边界接近
          2. Y 在锚点下方且间距不太大
          3. 不是另一个标签

        :return: [(score, block), ...]
        """
        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        anchor_h = max(ay2 - ay1, 5)
        anchor_w = ax2 - ax1
        max_y_gap = max(anchor_h * 3.0, 80.0)
        scored = []

        for block in candidates:
            bid = id(block)
            if bid == id(anchor_block):
                continue

            bx1, by1, bx2, by2 = block["rect"]

            # 在锚点下方
            if by1 < ay2 - 2:
                continue

            # 排除标签
            if _looks_like_label(block["text"]):
                continue
            # 排除包含锚点关键词的标签残片（"Place & Date of" 等）
            if _is_label_residue(block["text"]):
                continue

            # X 左对齐（放宽到 2x 宽度或 200px，适应 COSCO 等宽版式）
            x_diff = abs(bx1 - ax1)
            if x_diff > max(anchor_w * 2.0, 200):
                continue

            # Y 间距合理 (< 3x 行高)
            y_gap = by1 - ay2
            if y_gap > max_y_gap:
                continue

            y_score = max(0.0, 1.0 - y_gap / max_y_gap)
            x_score = max(0.0, 1.0 - x_diff / max(max(anchor_w * 2.0, 200), 1))
            score = y_score * 0.65 + x_score * 0.35
            if score > 0.25:
                scored.append((score, block))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # ================================================================
    # 表格提取
    # ================================================================

    def _extract_table(self, table_blocks):
        """
        从 table 区域提取结构化表格

        算法:
          1. Y 中心聚类 → 物理行
          2. 列检测 → 表头块 X 聚类确定列边界
          3. 块→列分配 → 每行每个块归入最近列
          4. 行分类 → header / data / continuation / summary
          5. 多行合并 → 连续 continuation 行合并到前一 data 行
          6. 输出 → {"headers": [...], "rows": [[...], ...]}

        :return: dict {"headers": [...], "rows": [[...], ...]} 或空 dict {}
        """
        if not table_blocks or len(table_blocks) < 2:
            return {}

        # Step 1: Y 聚类 → 物理行
        physical_rows = self._group_table_rows(table_blocks)
        if len(physical_rows) < 2:
            return {}

        # Step 2: 列检测 → 收集表头行（可能跨多行，如 "Gross" + "Weight"）
        #    扫描物理行直到遇到数据行（包含数字+KGS/CBM等）
        header_blocks = []
        data_start = 0
        for i, row_blocks in enumerate(physical_rows):
            row_text = " ".join(b["text"] for b in row_blocks).upper()
            has_numbers = bool(re.search(r'\d{2,}', row_text))
            has_units = any(u in row_text for u in ["KGS", "CBM", "PKG", "PCS"])
            # 表头行：第1行、或前3行中不包含数字+单位的行
            if i == 0 or (i < 3 and not (has_numbers and has_units)):
                header_blocks.extend(row_blocks)
                data_start = i + 1
            else:
                break

        columns = self._detect_columns(header_blocks)
        if len(columns) < 2:
            return {}

        # 验证：表头不能像字段标签（如 "Shipper:", "B/L No.:"）
        header_labels = " ".join(c["label"] for c in columns).upper()
        field_keywords = ["SHIPPER", "CONSIGNEE", "NOTIFY", "B/L NO",
                           "PORT OF", "VESSEL:", "VOYAGE", "FREIGHT",
                           "ISSUE", "托运人", "收货人"]
        if any(kw in header_labels for kw in field_keywords):
            return {}  # 这是字段区域，不是货物明细表格

        # 验证：表头必须包含至少 1 个货物表格的典型列名
        # 注意 OCR 可能把 "Gross Weight" 识别为 "G.W.(KGS)"、"Measurement" 为 "MEAS.(CBM)"
        cargo_cols = ["NO.", "CONTAINER", "SEAL", "QTY", "PACKAGE",
                       "DESCRIPTION", "WEIGHT", "MEASUREMENT",
                       "GROSS", "MARKS", "NOS", "G.W.", "KGS", "CBM",
                       "PKGS", "PCS", "CTNS"]
        if not any(cc in header_labels for cc in cargo_cols):
            return {}  # 不像是货物明细表格

        # Step 3: 每行块→列分配（过滤标签块，防止 "Weight:" 等混入表格数据）
        row_assignments = []  # [{col_idx: text, ...}, ...]
        for row_blocks in physical_rows:
            col_map = {}
            for block in row_blocks:
                if _looks_like_label(block["text"]):
                    continue  # 跳过标签块（如 "Weight:", "Total:", "Measurement:" 等）
                col_idx = self._assign_to_column(block, columns)
                if col_idx is not None:
                    text = block["text"].strip()
                    if text:
                        col_map[col_idx] = text
            row_assignments.append(col_map)

        # Step 4: 行分类 & 多行合并
        headers = [c["label"] for c in columns]
        data_rows = self._merge_table_rows(row_assignments, columns, data_start)

        return {
            "headers": headers,
            "rows": data_rows,
        }

    @staticmethod
    def _should_use_learned_table_layout(table_data, layout):
        if not isinstance(layout, dict) or layout.get("mode") != "anchor_region":
            return False
        learned_headers = [str(item).strip() for item in (layout.get("headers") or []) if str(item).strip()]
        if not learned_headers:
            return False
        if not table_data or not table_data.get("headers") or not table_data.get("rows"):
            return True
        current = " ".join(str(item).upper() for item in table_data.get("headers", []))
        matched = sum(1 for header in learned_headers if str(header).upper() in current)
        return matched < max(1, len(learned_headers) // 2)

    @staticmethod
    def _layout_region_to_rect(region, image_size):
        if not isinstance(region, dict) or not image_size or len(image_size) < 2:
            return None
        try:
            width = float(image_size[0])
            height = float(image_size[1])
            x1 = float(region.get("x1")) * width
            y1 = float(region.get("y1")) * height
            x2 = float(region.get("x2")) * width
            y2 = float(region.get("y2")) * height
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0 or x2 <= x1 or y2 <= y1:
            return None
        return [
            max(0, x1 - width * TABLE_LAYOUT_X_PADDING_RATIO),
            max(0, y1 - height * TABLE_LAYOUT_Y_PADDING_RATIO),
            min(width, x2 + width * TABLE_LAYOUT_X_PADDING_RATIO),
            min(height, y2 + height * TABLE_LAYOUT_Y_PADDING_RATIO),
        ]

    @staticmethod
    def _layout_columns_to_ranges(layout, region_rect, image_size):
        headers = [str(item).strip() for item in (layout.get("headers") or []) if str(item).strip()]
        raw_columns = layout.get("columns") or []
        columns = []
        width = float(image_size[0])
        for index, item in enumerate(raw_columns):
            if not isinstance(item, dict):
                continue
            try:
                x1 = float(item.get("x1")) * width
                x2 = float(item.get("x2")) * width
            except (TypeError, ValueError):
                continue
            if x2 <= x1:
                continue
            header = str(item.get("header") or (headers[index] if index < len(headers) else "")).strip()
            columns.append({"header": header, "x1": x1, "x2": x2})
        if columns:
            columns[0]["x1"] = min(columns[0]["x1"], region_rect[0])
            columns[-1]["x2"] = max(columns[-1]["x2"], region_rect[2])
            return columns

        if not headers:
            return []
        x1, _, x2, _ = region_rect
        step = (x2 - x1) / len(headers)
        return [
            {"header": header, "x1": x1 + index * step, "x2": x1 + (index + 1) * step}
            for index, header in enumerate(headers)
        ]

    @staticmethod
    def _match_layout_header_block(blocks, header, y1, y2):
        needle = re.sub(r"\s+", "", str(header or "")).upper()
        if not needle:
            return None
        for block in blocks or []:
            text = str(block.get("text") or "").strip()
            rect = block.get("rect")
            if not text or not isinstance(rect, list) or len(rect) != 4:
                continue
            haystack = re.sub(r"\s+", "", text).upper()
            if not (haystack and (needle in haystack or haystack in needle)):
                continue
            cy = (rect[1] + rect[3]) / 2.0
            if y1 <= cy <= y2:
                return block
        return None

    def _repair_layout_columns_from_template_headers(self, blocks, layout, region_rect, image_size, table_headers=None):
        headers = [str(item).strip() for item in (table_headers or []) if str(item).strip()]
        layout_headers = [str(item).strip() for item in ((layout or {}).get("headers") or []) if str(item).strip()]
        if len(headers) <= len(layout_headers):
            return region_rect, None

        matched_blocks = [
            self._match_layout_header_block(blocks, header, region_rect[1], region_rect[3])
            for header in headers
        ]
        if len(matched_blocks) != len(headers) or not all(matched_blocks):
            return region_rect, None

        width = float(image_size[0])
        header_centers = [((block["rect"][0] + block["rect"][2]) / 2.0) for block in matched_blocks]
        min_x = max(0, min(block["rect"][0] for block in matched_blocks) - width * TABLE_LAYOUT_X_PADDING_RATIO)
        max_x = min(width, max(block["rect"][2] for block in matched_blocks) + width * TABLE_LAYOUT_X_PADDING_RATIO)
        next_region = [min(region_rect[0], min_x), region_rect[1], max(region_rect[2], max_x), region_rect[3]]
        columns = []
        for index, header in enumerate(headers):
            left = next_region[0] if index == 0 else (header_centers[index - 1] + header_centers[index]) / 2.0
            right = next_region[2] if index == len(headers) - 1 else (header_centers[index] + header_centers[index + 1]) / 2.0
            columns.append({"header": header, "x1": left, "x2": right})
        return next_region, columns

    @staticmethod
    def _is_layout_header_row(cells, headers):
        non_empty = [(idx, str(value).strip()) for idx, value in enumerate(cells) if str(value).strip()]
        if not non_empty:
            return False
        matches = 0
        for idx, value in non_empty:
            header = str(headers[idx] if idx < len(headers) else "").strip()
            if not header:
                continue
            header_norm = re.sub(r"\s+", "", header).upper()
            value_norm = re.sub(r"\s+", "", value).upper()
            if header_norm and (header_norm in value_norm or value_norm in header_norm):
                matches += 1
        return matches >= max(1, len(non_empty) - 1)

    def _extract_table_with_learned_layout(self, blocks, layout, image_size=None, table_headers=None):
        region_rect = self._layout_region_to_rect((layout or {}).get("region"), image_size)
        if not region_rect:
            return {}
        columns = self._layout_columns_to_ranges(layout, region_rect, image_size)
        region_rect, repaired_columns = self._repair_layout_columns_from_template_headers(
            blocks,
            layout,
            region_rect,
            image_size,
            table_headers=table_headers,
        )
        if repaired_columns:
            columns = repaired_columns
        headers = [col["header"] for col in columns if col.get("header")]
        if not columns or not headers:
            return {}

        rx1, ry1, rx2, ry2 = region_rect
        region_blocks = []
        for block in blocks or []:
            text = str(block.get("text") or "").strip()
            rect = block.get("rect")
            if not text or not isinstance(rect, list) or len(rect) != 4:
                continue
            bx1, by1, bx2, by2 = rect
            cx = (bx1 + bx2) / 2.0
            cy = (by1 + by2) / 2.0
            if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                region_blocks.append(block)
        if len(region_blocks) < 2:
            return {}

        grouped_rows = self._group_table_rows(region_blocks)
        row_items = []
        has_header_row = False
        for row_blocks in grouped_rows:
            cells = [[] for _ in columns]
            for block in sorted(row_blocks, key=lambda item: item["rect"][0]):
                bx1, _, bx2, _ = block["rect"]
                cx = (bx1 + bx2) / 2.0
                for index, col in enumerate(columns):
                    if col["x1"] <= cx <= col["x2"]:
                        cells[index].append(str(block.get("text") or "").strip())
                        break
            row = [" ".join(parts).strip() for parts in cells]
            if not any(row):
                continue
            if self._is_layout_header_row(row, headers):
                has_header_row = True
            row_cy = sum((block["rect"][1] + block["rect"][3]) / 2.0 for block in row_blocks) / len(row_blocks)
            row_items.append((row_cy, row))

        rows = []
        header_seen = not has_header_row
        for _, row in sorted(row_items, key=lambda item: item[0]):
            if self._is_layout_header_row(row, headers):
                header_seen = True
                continue
            if not header_seen:
                continue
            if len(headers) > 1 and sum(1 for cell in row if str(cell).strip()) < 2:
                continue
            rows.append(row)

        if not rows:
            return {}
        return {
            "headers": headers,
            "rows": rows,
            "source": "learned_layout",
        }

    @staticmethod
    def _group_table_rows(blocks):
        """Y 中心聚类 → 物理行列表"""
        sorted_blocks = sorted(blocks, key=lambda b: (b["rect"][1] + b["rect"][3]) / 2.0)

        rows = []
        current_row = [sorted_blocks[0]]
        current_cy = (sorted_blocks[0]["rect"][1] + sorted_blocks[0]["rect"][3]) / 2.0
        current_avg_h = sorted_blocks[0]["rect"][3] - sorted_blocks[0]["rect"][1]

        for block in sorted_blocks[1:]:
            by1, by2 = block["rect"][1], block["rect"][3]
            block_cy = (by1 + by2) / 2.0
            block_h = max(by2 - by1, 5)

            if abs(block_cy - current_cy) < max(current_avg_h * 0.7, block_h * 0.7):
                current_row.append(block)
                current_cy = (current_cy * len(current_row) + block_cy) / (len(current_row) + 1)
                current_avg_h = max(current_avg_h, block_h)
            else:
                rows.append(current_row)
                current_row = [block]
                current_cy = block_cy
                current_avg_h = block_h

        rows.append(current_row)
        return rows

    @staticmethod
    def _detect_columns(header_blocks):
        """
        从表头行检测列定义

        算法: 表头块按 X 排序 → 相邻块间距 > 阈值则分列
              间距阈值 = 中位块宽度（列宽通常是均匀的）

        :return: [{"label": "Container No.", "x_center": 268, "x_range": [177, 360]}, ...]
        """
        # 按 X 排序（列顺序从左到右）
        sorted_blocks = sorted(header_blocks, key=lambda b: b["rect"][0])

        columns = []
        for block in sorted_blocks:
            x_center = (block["rect"][0] + block["rect"][2]) / 2.0
            half_w = (block["rect"][2] - block["rect"][0]) / 2.0
            label = block["text"].strip()

            # 跳过看起来不是表头的块
            if not label or len(label) < 1:
                continue

            columns.append({
                "label": label,
                "x_center": x_center,
                "x_min": block["rect"][0] - half_w * 0.3,
                "x_max": block["rect"][2] + half_w * 0.3,
                "_y": block["rect"][1],
                "_y2": block["rect"][3],
            })

        # 合并过近的列（如 "Gross" 和 "Weight" → "Gross Weight"）
        merged = []
        for col in columns:
            if not merged:
                merged.append(col)
                continue
            prev = merged[-1]
            gap = col["x_center"] - prev["x_center"]
            prev_w = prev["x_max"] - prev["x_min"]
            # 间距小于列宽的一半 → 合并同一列的多行标签
            if gap < prev_w * 0.6:
                # 按 Y 顺序拼接标签（先出现的在前，如 "Gross" 在 "Weight" 前面）
                prev_y = (prev.get("_y", 0) + prev.get("_y2", 0)) / 2.0
                col_y = (col.get("_y", 0) + col.get("_y2", 0)) / 2.0
                if prev_y <= col_y:
                    prev["label"] = prev["label"] + " " + col["label"]
                else:
                    prev["label"] = col["label"] + " " + prev["label"]
                prev["x_center"] = (prev["x_center"] + col["x_center"]) / 2.0
                prev["x_max"] = col["x_max"]
                # 保留最早出现的 Y 用于后续合并判断
                if col_y < prev_y:
                    prev["_y"] = col["_y"]
                    prev["_y2"] = col["_y2"]
            else:
                merged.append(col)

        return merged

    @staticmethod
    def _assign_to_column(block, columns):
        """将块分配到最近的列（按 X 中心距离）"""
        bx_center = (block["rect"][0] + block["rect"][2]) / 2.0

        best_col = None
        best_dist = float('inf')

        for i, col in enumerate(columns):
            dist = abs(bx_center - col["x_center"])
            # 列宽的一半作为容差
            max_dist = (col["x_max"] - col["x_min"]) * 0.8
            if dist < best_dist and dist < max_dist:
                best_dist = dist
                best_col = i

        return best_col

    def _merge_table_rows(self, row_assignments, columns, data_start=1):
        """
        合并连续 continuation 行到前一 data 行

        :param data_start: 数据行起始索引（跳过表头行）
        :return: [[cell_text, ...], ...]  每行按列顺序排列
        """
        col_count = len(columns)

        merged_rows = []  # [{col_idx: text, ...}, ...]

        for row_map in row_assignments[data_start:]:
            if not row_map:
                continue

            # 检测 summary 行（包含汇总关键词 → 整行跳过，视为字段区域）
            row_texts = " ".join(row_map.values()).upper()
            if any(kw in row_texts for kw in ["TOTAL GROSS", "TOTAL MEASUREMENT",
                                                "FREIGHT &", "PLACE & DATE",
                                                "PREPAID", "COLLECT",
                                                "CHARGES:", "ISSUE:"]):
                continue  # 跳过汇总行

            # 检测 continuation 行
            is_continuation = len(row_map) < col_count * 0.4

            if is_continuation and merged_rows:
                # 合并到前一 data 行
                prev = merged_rows[-1]
                for col_idx, text in row_map.items():
                    if col_idx in prev:
                        prev[col_idx] = prev[col_idx] + " " + text
                    else:
                        prev[col_idx] = text
            else:
                merged_rows.append(dict(row_map))

        # 转换为行数组（按列顺序）
        result = []
        for row_map in merged_rows:
            row = []
            for i in range(col_count):
                row.append(row_map.get(i, ""))
            result.append(row)

        return result


# ================================================================
# 便捷函数
# ================================================================

def extract_fields_from_ocr(blocks, image_size, regions=None):
    """
    一站式提取：OCR 块 → 结构化字段 JSON

    :param blocks: OCR 识别的全部文本块
    :param image_size: [width, height]
    :param regions: 可选，版面分析结果。不传则所有块视为 body
    :return: extract() 同款输出
    """
    extractor = FieldExtractor()
    if regions is None:
        regions = {"header": [], "body": blocks, "table": []}
    return extractor.extract(regions, image_size, blocks=blocks)

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

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


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

    # 4) 纯中文且极短（<5字），可能是标签 (e.g., "托运人", "收货人")
    #    但中文公司名通常 >5 字，所以阈值设为 5
    if re.match(r'^[一-鿿]{1,4}$', text):
        return True

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
            "templates": dict(_DEFAULT_TEMPLATES_CONFIG),
            "validators": dict(_DEFAULT_VALIDATORS),
            "field_defaults": dict(_DEFAULT_FIELD_DEFAULTS),
        }

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
        return {name: t.get("keywords", []) for name, t in templates.items()}

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
        template = self._detect_template(blocks)

        # 从当前模板读取字段定义（各版式独立，不再依赖全局 field_defs）
        tpl_config = self.config.get("templates", {}).get(template, {})
        tpl_fields = tpl_config.get("fields", {})
        output_list = tpl_config.get("output", list(tpl_fields.keys()))

        body_blocks = regions.get("header", []) + regions.get("body", [])
        table_blocks = regions.get("table", [])

        # 提取字段（只迭代当前版式定义的字段）
        fields = {}
        used_value_ids = set()

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
                used_value_ids.add(id(result["_block"]))

        # 提取表格
        table_data = self._extract_table(table_blocks)

        # 清理内部字段
        for v in fields.values():
            v.pop("_block", None)

        result = {
            "fields": fields,
            "table": table_data,
            "template": template,
        }

        return self.normalize(result, img_size=image_size, blocks=blocks)

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
                extra["label"] = all_fields.get(fname, {}).get("label", fname)
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

    def _detect_template(self, blocks):
        """关键词投票选版式（关键词列表来自 config.yaml 或内置默认值）"""
        all_text = " ".join(b["text"] for b in blocks).upper()

        scores = {}
        for tpl, keywords in self.template_keywords.items():
            if not keywords:
                continue
            hits = sum(1 for kw in keywords if kw.upper() in all_text)
            if hits > 0:
                scores[tpl] = hits

        return max(scores, key=scores.get) if scores else "unknown"

    # ================================================================
    # 单字段提取
    # ================================================================

    def _extract_field(self, field_name, cfg, search_pool, used_value_ids):
        """
        尝试从 search_pool 中提取指定字段

        策略优先级:
          1. 锚点块内部提取（标签+值合并在同一 OCR 块内，如 "Vessel: ONE HARBOUR"）
          2. 同行右侧独立值块
          3. 紧邻下方独立值块

        :return: dict 或 None
        """
        anchors = cfg.get("anchors", [])
        position = cfg.get("position", "right")
        validator_name = cfg.get("validator")
        validator_cfg = self.validators_cfg.get(validator_name) if validator_name else None

        # Step 1: 找锚点块（按匹配分数排序）
        anchor_matches = self._find_anchor_blocks(search_pool, anchors)
        if not anchor_matches:
            return None

        # Step 2: 逐个锚点尝试，直到找到有效值
        for anchor_block, score, matched_anchor in anchor_matches:
            # --- 策略 1: 从锚点块内部提取（标签+值合并） ---
            inline_value = self._extract_inline_value(anchor_block, matched_anchor)
            if inline_value:
                cleaned = inline_value.strip()
                if cleaned and len(cleaned) > 1:
                    cleaned_value, regex_ok = validate_and_clean(
                        field_name, cleaned,
                        validator_cfg=validator_cfg, field_cfg=cfg
                    )
                    return {
                        "value": cleaned,
                        "cleaned": cleaned_value,
                        "regex_valid": regex_ok,
                        "confidence": round(score * 0.3 + anchor_block.get("confidence", 0.8) * 0.7, 4),
                        "anchor_text": matched_anchor,
                        "rect": anchor_block["rect"],
                        "bbox": anchor_block.get("bbox", []),
                        "_block": anchor_block,
                    }

            # --- 策略 2/3: 外部值块 ---
            value_block = None

            if position in ("right", "either"):
                value_block = self._find_value_right(
                    anchor_block, search_pool, used_value_ids
                )

            if value_block is None and position in ("below", "either"):
                value_block = self._find_value_below(
                    anchor_block, search_pool, used_value_ids
                )

            # 共享值块：issue_date 和 issue_place 可能从同一块取值
            # （如 "NINGBO, 14/11/2025" 被 issue_place 用了，issue_date 也应能取）
            if value_block is None and field_name in ("issue_date",):
                value_block = self._find_value_right(
                    anchor_block, search_pool, None  # 不排斥已用块
                )
                if value_block is None:
                    value_block = self._find_value_below(
                        anchor_block, search_pool, None
                    )

            if value_block is None:
                continue

            raw_value = value_block["text"].strip()

            # 单位感知兼容性检查：weight 字段拒绝 CBM 值，volume 字段拒绝 KGS 值
            # 防止 total_gross_weight 抢走 total_measurement 的值（反之亦然）
            raw_upper = raw_value.upper()
            if validator_name == "weight" and "CBM" in raw_upper:
                continue  # 跳过此值块，尝试下一个锚点
            if validator_name == "volume" and ("KGS" in raw_upper or "KG" in raw_upper):
                continue  # 跳过此值块，尝试下一个锚点

            cleaned = _clean_text(raw_value)
            if cleaned is None:
                continue

            cleaned_value, regex_ok = validate_and_clean(
                field_name, cleaned,
                validator_cfg=validator_cfg, field_cfg=cfg
            )

            return {
                "value": raw_value,
                "cleaned": cleaned_value,
                "regex_valid": regex_ok,
                "confidence": round(score * 0.3 + value_block.get("confidence", 0.8) * 0.7, 4),
                "anchor_text": matched_anchor,
                "rect": value_block["rect"],
                "bbox": value_block.get("bbox", []),
                "_block": value_block,
            }

        return None

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
        remainder = full_text[idx + len(matched_anchor):].strip()

        # 去掉常见的分隔符（冒号、空格、破折号等）
        remainder = remainder.lstrip(':、：\s-—―')

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
                if anchor_upper in text_upper:
                    # 锚点占文本比例越高 → 越可能是真正的标签块
                    # 防止 "托运人" 匹配到 "托运人信息" 这类标题块
                    len_ratio = len(anchor) / max(len(text), 1)
                    ratio_bonus = 0.15 * min(len_ratio * 1.5, 1.0)
                    score = 0.85 + ratio_bonus
                    candidates.append((block, score, anchor))
                    break

                # 2) 模糊匹配：OCR 容错
                sim = self._text_similarity(text_upper, anchor_upper)
                if sim >= self.fuzzy_threshold:
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
        if anchor_ns in text_ns or text_ns in anchor_ns:
            return 0.85

        # SequenceMatcher 基于最长公共子序列
        return SequenceMatcher(None, text, anchor).ratio()

    # ================================================================
    # 值定位 — 同行右侧
    # ================================================================

    def _find_value_right(self, anchor_block, candidates, used_ids=None):
        """
        在锚点同行右侧找值块

        评分策略 (0~1):
          - Y 中心对齐  权重 0.6  （同行为王）
          - X 邻近      权重 0.3  （越近越好）
          - 非标签      权重 0.1  （不是另一个锚点）

        :return: 最佳值 block 或 None
        """
        if used_ids is None:
            used_ids = set()

        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        anchor_h = max(ay2 - ay1, 5)
        anchor_cy = (ay1 + ay2) / 2.0

        scored = []

        for block in candidates:
            bid = id(block)
            if bid == id(anchor_block):
                continue
            if bid in used_ids:
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
            # 邻近分：距离 500px 内有效，越近越高
            x_score = max(0.0, 1.0 - x_gap / 500.0)

            # ---- 综合分 ----
            score = y_score * 0.6 + x_score * 0.4

            if score > 0.25:  # 最低阈值
                scored.append((score, block))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    # ================================================================
    # 值定位 — 紧邻下方
    # ================================================================

    def _find_value_below(self, anchor_block, candidates, used_ids=None):
        """
        在锚点紧邻下方找值块

        条件:
          1. X 左边界与锚点左边界接近
          2. Y 在锚点下方且间距不太大
          3. 不是另一个标签

        :return: 最佳值 block 或 None
        """
        if used_ids is None:
            used_ids = set()

        ax1, ay1, ax2, ay2 = anchor_block["rect"]
        anchor_h = max(ay2 - ay1, 5)
        anchor_w = ax2 - ax1

        best = None
        best_gap = float('inf')

        for block in candidates:
            bid = id(block)
            if bid == id(anchor_block):
                continue
            if bid in used_ids:
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
            if y_gap > anchor_h * 3.0 or y_gap > 100:
                continue

            if y_gap < best_gap:
                best_gap = y_gap
                best = block

        return best

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

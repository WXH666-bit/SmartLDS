"""
从 FUNSD 公开数据集中选取 20 份表单，转换为项目 dataset 兼容格式。
FUNSD 作为第4种版式，验证版式自适应 + 动态 Schema 能力。

FUNSD 原始格式: {form: [{box, text, label(question/answer/header/other), words, linking, id}]}
输出格式：与 generate_data.py 一致，字段名使用 FUNSD 表单的实际标签（TO, FROM, DATE 等）
"""

import json
import os
import random
import re
from PIL import Image

# 路径配置
FUNSD_DIR = os.path.dirname(os.path.abspath(__file__))
ANNO_DIR = os.path.join(FUNSD_DIR, "dataset", "testing_data", "annotations")
IMAGE_DIR = os.path.join(FUNSD_DIR, "dataset", "testing_data", "images")

PROJECT_ROOT = os.path.dirname(FUNSD_DIR)
PDF_DIR = os.path.join(PROJECT_ROOT, "dataset", "pdf")
JSON_DIR = os.path.join(PROJECT_ROOT, "dataset", "json")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

# 项目统一字段名映射（FUNSD 表单标签 → 统一 schema）
FUNSD_FIELD_MAP = {
    "TO":     {"name": "recipient",   "cn": "收件人"},
    "FROM":   {"name": "sender",      "cn": "发件人"},
    "DATE":   {"name": "date",        "cn": "日期"},
    "SUBJECT": {"name": "subject",     "cn": "主题"},
    "TOTAL":  {"name": "total",       "cn": "金额"},
    "FAX":    {"name": "fax",         "cn": "传真"},
    "PHONE":  {"name": "phone",       "cn": "电话"},
    "RE":     {"name": "reference",   "cn": "参考号"},
    "CC":     {"name": "cc",          "cn": "抄送"},
    "PAGE":   {"name": "page",        "cn": "页码"},
}


def clean_label(text):
    """清洗字段标签：去掉冒号、多余空格"""
    return text.strip().rstrip(":").rstrip("：").strip().upper()


def extract_fields_with_linking(funsd_data):
    """
    通过 FUNSD 的 linking 关系配对 question → answer
    返回提取的字段字典 + 所有文本块列表
    """
    items = funsd_data.get("form", [])
    id_to_item = {item["id"]: item for item in items}

    fields = {}
    text_blocks = []

    # 遍历所有 question 标签，通过 linking 找对应 answer
    for item in items:
        label = item.get("label", "other")
        text = item.get("text", "").strip()
        box = item.get("box", [])

        if text:
            text_blocks.append({"text": text, "label": label, "bbox": box})

        if label == "question" and text:
            key = clean_label(text)
            if not key:
                continue

            # 通过 linking 找 answer
            value = ""
            for link in item.get("linking", []):
                for linked_id in link:
                    if linked_id in id_to_item:
                        linked_item = id_to_item[linked_id]
                        if linked_item.get("label") == "answer":
                            val = linked_item.get("text", "").strip()
                            if val:
                                value = val
                                break

            # 标准化字段名
            if key in FUNSD_FIELD_MAP:
                field_name = FUNSD_FIELD_MAP[key]["name"]
            else:
                field_name = key.lower().replace(" ", "_").replace("/", "_")

            fields[field_name] = {
                "value": value,
                "anchor": key,
                "bbox": box if box else None,
            }

    return fields, text_blocks


def main():
    all_files = [f for f in os.listdir(ANNO_DIR) if f.endswith(".json")]
    random.seed(42)
    selected = sorted(random.sample(all_files, min(20, len(all_files))))
    print(f"从 {len(all_files)} 份 FUNSD 表单中选取 {len(selected)} 份\n")

    for i, anno_file in enumerate(selected):
        name = anno_file.replace(".json", "")
        anno_path = os.path.join(ANNO_DIR, anno_file)
        img_path = os.path.join(IMAGE_DIR, name + ".png")

        # 读取 FUNSD 原始标注
        with open(anno_path, "r", encoding="utf-8") as f:
            funsd_data = json.load(f)

        # 提取字段
        fields, text_blocks = extract_fields_with_linking(funsd_data)

        # 构建项目兼容格式的数据记录
        record = {
            "template": "funsd_public",
            "source": name,
            # 核心字段（与合成数据 JSON 结构对齐）
            "fields": {k: v["value"] for k, v in fields.items()},
            # 保留锚点 + bbox 信息（供 KIE 模块使用）
            "field_details": fields,
            # 原始文本块（供 OCR 验证对比）
            "ocr_blocks": text_blocks,
        }

        # 输出编号 161~180
        idx = 161 + i
        json_path = os.path.join(JSON_DIR, f"bol_{idx:03d}.json")
        pdf_path = os.path.join(PDF_DIR, f"bol_{idx:03d}.pdf")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        # PNG 转 PDF
        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF")

        field_names = list(fields.keys())
        print(f"  bol_{idx:03d} ← {name}  字段: {field_names}")

    print(f"\n完成！20 份 FUNSD 公开数据已写入 dataset/")
    print(f"  编号范围: bol_161.pdf ~ bol_{idx:03d}.pdf")


if __name__ == "__main__":
    main()

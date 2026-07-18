"""
批量评估脚本。

运行方式：
    python tests/batch_test.py

这个脚本会跑较重的 OCR 批量评估，并在 batch_output/ 下生成 HTML/PDF 报告。
它故意不命名为 test_*.py，避免 unittest discover 时自动加载 OCR 模型和扫描大量样本。
快速单元测试请放在 tests/test_*.py。
"""

import sys, os, json, io, time
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path

from ocr_engine import OCREngine
from preprocess import Preprocessor
from layout_parser import LayoutParser
from field_extractor import FieldExtractor

# ============================================================
# 测试样本
# ============================================================

SAMPLES = [
    # ========== 合成数据 (80%) ==========
    # Maersk: 17 份
    ("001", "Maersk"), ("004", "Maersk"), ("007", "Maersk"),
    ("010", "Maersk"), ("013", "Maersk"), ("016", "Maersk"),
    ("019", "Maersk"), ("022", "Maersk"), ("025", "Maersk"),
    ("028", "Maersk"), ("031", "Maersk"), ("034", "Maersk"),
    ("037", "Maersk"), ("040", "Maersk"), ("043", "Maersk"),
    ("046", "Maersk"), ("049", "Maersk"),
    # COSCO: 17 份
    ("002", "COSCO"), ("005", "COSCO"), ("008", "COSCO"),
    ("011", "COSCO"), ("014", "COSCO"), ("017", "COSCO"),
    ("020", "COSCO"), ("023", "COSCO"), ("026", "COSCO"),
    ("029", "COSCO"), ("032", "COSCO"), ("035", "COSCO"),
    ("038", "COSCO"), ("041", "COSCO"), ("044", "COSCO"),
    ("047", "COSCO"), ("050", "COSCO"),
    # Simple: 16 份
    ("003", "Simple"), ("006", "Simple"), ("009", "Simple"),
    ("012", "Simple"), ("015", "Simple"), ("018", "Simple"),
    ("021", "Simple"), ("024", "Simple"), ("027", "Simple"),
    ("030", "Simple"), ("033", "Simple"), ("036", "Simple"),
    ("039", "Simple"), ("042", "Simple"), ("045", "Simple"),
    ("048", "Simple"),
    # ========== 公开数据集 FUNSD (10%) ==========
    ("161", "FUNSD"), ("163", "FUNSD"), ("165", "FUNSD"),
    ("167", "FUNSD"), ("169", "FUNSD"),
    ("171", "FUNSD"), ("173", "FUNSD"), ("175", "FUNSD"),
    ("177", "FUNSD"), ("179", "FUNSD"),
    # ========== 真实扫描件 (10%) ==========
    ("181", "真扫"), ("183", "真扫"), ("185", "真扫"),
    ("187", "真扫"), ("189", "真扫"), ("191", "真扫"),
    ("193", "真扫"), ("195", "真扫"), ("197", "真扫"),
    ("199", "真扫"),
]

OUT_DIR = os.path.join(ROOT_DIR, "batch_output")
os.makedirs(OUT_DIR, exist_ok=True)


def _normalize_comparison_value(value):
    """Normalize OCR and GT strings without changing their semantic content."""
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _report_file_uri(html_path):
    """Return an absolute file URI so report-relative preview images resolve."""
    return Path(html_path).resolve().as_uri()


GT_KEY_GROUPS = {
    "total_gross_weight": (("total_gw",),),
    "total_measurement": (("total_cbm",),),
    "place_date_of_issue": (("issue_place", "issue_date"),),
    "quantity_unit": (("qty", "unit"),),
}


def _resolve_gt_value(field_name, canonical_key, gt):
    for key in (canonical_key, field_name):
        if key in gt:
            return str(gt[key])

    for key_group in GT_KEY_GROUPS.get(canonical_key, ()):
        if all(key in gt for key in key_group):
            return " ".join(str(gt[key]) for key in key_group)
    return None


def evaluate_extracted_fields(fields, gt):
    """Compare source-label result fields with canonical-key GT values."""
    correct = 0
    total = 0
    details = []

    for field_name, info in (fields or {}).items():
        canonical_key = str(info.get("canonical_key") or field_name)
        expected = _resolve_gt_value(field_name, canonical_key, gt)
        if expected is None:
            continue

        label = info.get("label", field_name)
        display = f"{label} ({canonical_key})" if label != canonical_key else label
        cleaned = info.get("corrected", info.get("cleaned", info.get("value", "")))
        total += 1

        if info.get("status") == "not_found":
            details.append((display, cleaned, expected[:35], "MISS"))
            continue

        actual_norm = _normalize_comparison_value(cleaned)
        expected_norm = _normalize_comparison_value(expected)
        matched = bool(actual_norm and expected_norm) and (
            actual_norm == expected_norm
            or expected_norm in actual_norm
            or actual_norm in expected_norm
        )
        if matched:
            correct += 1
        details.append((display, cleaned, expected[:35], "OK" if matched else "X"))

    return correct, total, details


def run_one(bol, desc, engine, parser, extractor):
    """运行一份样本的完整流水线"""
    pdf_path = os.path.join(os.path.dirname(OUT_DIR), "dataset", "pdf", f"bol_{bol}.pdf")
    json_path = os.path.join(os.path.dirname(OUT_DIR), "dataset", "json", f"bol_{bol}.json")

    # 加载 GT（FUNSD 的字段嵌套在 gt["fields"] 内，需要扁平化）
    with open(json_path, "r", encoding="utf-8") as f:
        gt_raw = json.load(f)
    if "fields" in gt_raw and isinstance(gt_raw["fields"], dict):
        gt = gt_raw["fields"]
    else:
        gt = gt_raw

    # Pipeline
    ocr_result = engine.recognize_pdf(pdf_path)[0]
    blocks = ocr_result["blocks"]
    img_size = ocr_result["image_size"]

    regions = parser.parse(blocks, img_size)
    extracted = extractor.extract(regions, img_size, blocks=blocks)

    # 统计准确率
    fields = extracted.get("fields", {})
    correct, total, details = evaluate_extracted_fields(fields, gt)

    acc = correct / max(total, 1) * 100

    return {
        "bol": bol, "desc": desc,
        "template": extracted.get("template", "?"),
        "fields": fields, "details": details,
        "acc": acc, "correct": correct, "total": total,
        "table": extracted.get("table", {}),
        "meta": extracted.get("meta", {}),
        "pdf_path": pdf_path,
    }


def render_preview(pdf_path, blocks=None):
    """渲染 PDF 第一页为图片，可选叠加 OCR bbox"""
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=150)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def _save_preview(image, path, attempts=3):
    """Save a preview with a short retry for transient Windows file errors."""
    for attempt in range(attempts):
        try:
            image.save(path, "PNG")
            return True
        except OSError:
            if attempt + 1 >= attempts:
                return False
            time.sleep(0.2 * (attempt + 1))
    return False


def build_html(results, summary):
    """生成 HTML 报告 — 按数据来源分组"""
    # 分组：合成数据 / FUNSD / 真实扫描
    synthetic = [r for r in results if r["desc"] in ("Maersk", "COSCO", "Simple")]
    funsd = [r for r in results if r["desc"] == "FUNSD"]
    real = [r for r in results if r["desc"] == "真扫"]

    def render_sample(r):
        det = ""
        for fname, val, gt_val, ok in r["details"]:
            cls = "ok" if ok == "OK" else ("miss" if ok == "MISS" else "err")
            det += f'<tr class="{cls}"><td>{fname}</td><td class="val">{val[:40]}</td><td class="gt">{gt_val[:35]}</td><td class="mark">{ok}</td></tr>'
        tbl = ""
        t = r.get("table", {})
        if t.get("headers"):
            tbl = '<table class="cargo"><tr>' + "".join(f"<th>{h}</th>" for h in t["headers"]) + "</tr>"
            for row in t.get("rows", []):
                tbl += "<tr>" + "".join(f"<td>{c[:25]}</td>" for c in row) + "</tr>"
            tbl += "</table>"
        return f"""
    <div class="sample">
      <h3>bol_{r['bol']} &nbsp; <span class="badge">{r['template']}</span> &nbsp;
        <span class="acc">{r['acc']:.0f}% ({r['correct']}/{r['total']})</span></h3>
      <div class="cols">
        <div class="col-img"><img src="previews/bol_{r['bol']}.png"></div>
        <div class="col-fields">
          <table class="fields"><tr><th>字段</th><th>提取值</th><th>GT</th><th></th></tr>{det}</table>
          {tbl}
        </div>
      </div>
    </div>"""

    def render_simple(r):
        """FUNSD / 真实扫描：展示预览图 + 提取字段（不逐字段对比 GT）"""
        meta = r.get("meta", {})
        det_html = ""
        for display, cleaned, _, status in r.get("details", []):
            cls = "ok" if status == "OK" else "miss"
            det_html += f'<tr><td>{display}</td><td>{cleaned}</td><td class="{cls}">{status}</td></tr>'
        return f"""
    <div class="sample">
      <h3>bol_{r['bol']} &nbsp; <span class="badge">{r['template']}</span></h3>
      <div class="cols">
        <div class="col-img"><img src="previews/bol_{r['bol']}.png"></div>
        <div class="col-fields">
          <p style="font-size:13px;margin-bottom:8px;">OCR 块数: <b>{meta.get('ocr_blocks', '?')}</b> &nbsp;|&nbsp;
             图片尺寸: {meta.get('image_size', ['?','?'])} &nbsp;|&nbsp;
             版式: {r['template']}</p>
          <table class="fields"><tr><th>字段</th><th>提取值</th><th>状态</th></tr>{det_html}</table>
        </div>
      </div>
    </div>"""

    sections = ""
    # 合成数据 — 按版式再分子组
    sections += '<div class="section-header" style="border-left:4px solid #3b82f6;"><h2>合成数据 (80%)</h2><span class="section-acc">准确率: {:.1f}% | {} 份 | 3 种版式</span></div>'.format(
        summary['synth_acc'], summary['synth_count'])
    for r in synthetic:
        sections += render_sample(r)

    # FUNSD
    if funsd:
        sections += '<div class="section-header" style="border-left:4px solid #8b5cf6;"><h2>FUNSD 公开数据集 (10%)</h2><span class="section-acc">{} 份 | OCR 处理验证</span></div>'.format(len(funsd))
        for r in funsd:
            sections += render_simple(r)

    # 真实扫描
    if real:
        sections += '<div class="section-header" style="border-left:4px solid #f97316;"><h2>真实扫描件 (10%)</h2><span class="section-acc">{} 份 | 预处理效果验证</span></div>'.format(len(real))
        for r in real:
            sections += render_simple(r)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>SmartLDS 批量测试报告</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin:20px 30px; color:#1e293b; }}
  h1 {{ font-size:22px; }} .sub {{ color:#888; font-size:13px; margin-bottom:24px; }}

  .summary {{ display:flex; gap:24px; margin:20px 0; flex-wrap:wrap; }}
  .kpi {{ background:#fff; border-radius:8px; padding:16px 24px; box-shadow:0 1px 3px rgba(0,0,0,.08); text-align:center; min-width:100px; }}
  .kpi .num {{ font-size:28px; font-weight:700; }}
  .kpi .lbl {{ font-size:12px; color:#888; }}
  .kpi.g .num {{ color:#10b981; }} .kpi.y .num {{ color:#f59e0b; }} .kpi.b .num {{ color:#3b82f6; }}

  .section-header {{ display:flex; align-items:baseline; gap:12px; margin:28px 0 12px; padding:10px 16px; background:#f8fafc; border-radius:6px; }}
  .section-header h2 {{ font-size:17px; }}
  .section-acc {{ font-size:13px; color:#888; }}
  .badge {{ padding:2px 10px; border-radius:10px; font-size:11px; font-weight:600; }}

  .sample {{ margin:16px 0 20px; border:1px solid #e5e7eb; border-radius:8px; padding:14px; }}
  .sample h3 {{ font-size:14px; margin-bottom:8px; }}
  .acc {{ font-weight:700; color:#10b981; font-size:13px; }}

  .cols {{ display:flex; gap:16px; }}
  .col-img {{ width:45%; }}
  .col-img img {{ width:100%; border:1px solid #e5e7eb; border-radius:4px; }}
  .col-fields {{ flex:1; font-size:12px; }}

  table.fields {{ border-collapse:collapse; width:100%; margin-bottom:12px; }}
  table.fields th {{ background:#f8fafc; text-align:left; padding:4px 8px; border-bottom:2px solid #e5e7eb; font-size:11px; }}
  table.fields td {{ padding:3px 8px; border-bottom:1px solid #f3f4f6; }}
  td.val {{ font-family:Consolas,monospace; font-size:11px; }} td.gt {{ font-size:11px; color:#888; }} td.mark {{ font-weight:700; width:30px; }}
  .ok {{ }} .err {{ color:#ef4444; }} .miss {{ color:#f59e0b; opacity:0.7; }}

  table.cargo {{ border-collapse:collapse; width:100%; font-size:11px; }}
  table.cargo th {{ background:#1e293b; color:#fff; padding:3px 6px; }}
  table.cargo td {{ padding:3px 6px; border-bottom:1px solid #e5e7eb; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

  .footer {{ margin-top:32px; padding-top:16px; border-top:1px solid #e5e7eb; font-size:11px; color:#888; }}

  @media print {{ body {{ margin:10px; }} .sample {{ break-inside:avoid; }} }}
</style></head><body>
<h1>SmartLDS 批量测试报告</h1>
<p class="sub">测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; 样本: {summary['total']} 份 &nbsp;|&nbsp; 版式: 3 种</p>

<div class="summary">
  <div class="kpi g"><div class="num">{summary['synth_acc']:.1f}%</div><div class="lbl">合成数据准确率</div></div>
  <div class="kpi b"><div class="num">{summary['total']}</div><div class="lbl">样本总数</div></div>
  <div class="kpi y"><div class="num">{summary['synth_count']}+{summary.get('funsd_count',0)}+{summary.get('real_count',0)}</div><div class="lbl">合成+FUNSD+真实</div></div>
  <div class="kpi b"><div class="num">{summary['maersk_acc']:.1f}%</div><div class="lbl">Maersk</div></div>
  <div class="kpi y"><div class="num">{summary['cosco_acc']:.1f}%</div><div class="lbl">COSCO</div></div>
  <div class="kpi g"><div class="num">{summary['simple_acc']:.1f}%</div><div class="lbl">Simple</div></div>
</div>
{sections}
<div class="footer">SmartLDS — 物流单证智能识别系统 &nbsp;|&nbsp; 批量测试报告</div>
</body></html>"""


def main():
    print("=" * 60)
    print("SmartLDS 批量测试")
    print("=" * 60)

    # 初始化引擎
    print("\n[1/4] 初始化引擎...")
    engine = OCREngine()
    parser = LayoutParser()
    extractor = FieldExtractor()

    # 运行所有样本
    print(f"[2/4] 测试 {len(SAMPLES)} 份样本...")
    results = []
    previews_dir = os.path.join(OUT_DIR, "previews")
    os.makedirs(previews_dir, exist_ok=True)

    for i, (bol, desc) in enumerate(SAMPLES):
        sys.stdout.write(f"\r  [{i+1}/{len(SAMPLES)}] bol_{bol} ({desc})...")
        sys.stdout.flush()
        r = run_one(bol, desc, engine, parser, extractor)
        results.append(r)
        # 保存预览图
        img = render_preview(r["pdf_path"])
        preview_path = os.path.join(previews_dir, f"bol_{bol}.png")
        if not _save_preview(img, preview_path):
            print(f"\n  [!] Could not refresh preview after retries: {preview_path}")
    print("\n")

    # 汇总
    print("[3/4] 汇总统计...")
    # 合成数据：字段准确率
    synthetic = [r for r in results if r["desc"] in ("Maersk", "COSCO", "Simple")]
    total_correct = sum(r["correct"] for r in synthetic)
    total_fields = sum(r["total"] for r in synthetic)
    by_tpl = {}
    for r in synthetic:
        tpl = r["template"]
        if tpl not in by_tpl:
            by_tpl[tpl] = {"correct": 0, "total": 0}
        by_tpl[tpl]["correct"] += r["correct"]
        by_tpl[tpl]["total"] += r["total"]

    # 非合成数据：OCR 能力统计
    funsd_r = [r for r in results if r["desc"] == "FUNSD"]
    real_r = [r for r in results if r["desc"] == "真扫"]

    summary = {
        "total": len(results),
        "synth_count": len(synthetic),
        "synth_acc": total_correct / max(total_fields, 1) * 100,
        "funsd_count": len(funsd_r),
        "real_count": len(real_r),
        "maersk_acc": by_tpl.get("maersk_style", {"correct": 0, "total": 1})["correct"] /
                      max(by_tpl.get("maersk_style", {"total": 1})["total"], 1) * 100,
        "cosco_acc": by_tpl.get("cosco_style", {"correct": 0, "total": 1})["correct"] /
                     max(by_tpl.get("cosco_style", {"total": 1})["total"], 1) * 100,
        "simple_acc": by_tpl.get("simple_style", {"correct": 0, "total": 1})["correct"] /
                      max(by_tpl.get("simple_style", {"total": 1})["total"], 1) * 100,
    }

    print(f"  合成数据准确率: {summary['synth_acc']:.1f}% ({total_correct}/{total_fields})")
    for tpl, s in by_tpl.items():
        acc = s["correct"] / max(s["total"], 1) * 100
        print(f"    {tpl}: {acc:.1f}% ({s['correct']}/{s['total']})")
    print(f"  FUNSD: {summary['funsd_count']} 份（OCR 处理验证）")
    print(f"  真实扫描: {summary['real_count']} 份（预处理效果验证）")

    # 生成报告
    print("\n[4/4] 生成报告...")
    html = build_html(results, summary)
    html_path = os.path.join(OUT_DIR, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # HTML → PDF (via Playwright)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(_report_file_uri(html_path), wait_until="networkidle")
            pdf_path = os.path.join(OUT_DIR, "report.pdf")
            page.pdf(path=pdf_path, format="A3", landscape=True, print_background=True)
            browser.close()
        print(f"  PDF 报告: {pdf_path}")
    except Exception as e:
        print(f"  [!] PDF 生成失败 (Playwright): {e}")
        print(f"  请在浏览器打开 HTML: {html_path}")

    # 同时保存 JSON 汇总
    summary_path = os.path.join(OUT_DIR, "summary.json")
    summary_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {k: round(v, 2) if isinstance(v, float) else v for k, v in summary.items()},
        "by_template": {k: {"accuracy": round(v["correct"] / max(v["total"], 1) * 100, 2),
                             "correct": v["correct"], "total": v["total"]} for k, v in by_tpl.items()},
        "details": [{"bol": r["bol"], "template": r["template"], "acc": round(r["acc"], 2),
                      "correct": r["correct"], "total": r["total"]} for r in results],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"  JSON 汇总: {summary_path}")
    print(f"\n全部输出在: {OUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()

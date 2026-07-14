"""
SmartLDS Flask 后端 — 物流单证智能识别 API

启动: python app.py  (默认 http://localhost:5000)
依赖: pip install flask flask-cors openpyxl pyyaml

API 端点:
  POST /api/upload          — 上传 PDF/图片
  POST /api/recognize/<id>  — 触发识别流水线
  GET  /api/result/<id>     — 获取结构化结果
  POST /api/correct/<id>    — 保存人工校正
  GET  /api/export/<id>     — 导出 Excel / JSON
  GET  /api/image/<id>      — 获取原始图片
"""

import os
import sys
import uuid
import json
import shutil
import tempfile
import zipfile
import copy
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 确保 backend 模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr_engine import OCREngine
from preprocess import Preprocessor
from layout_parser import LayoutParser
from field_extractor import FieldExtractor

# ================================================================
# Flask 应用初始化
# ================================================================

app = Flask(__name__)
CORS(app)  # 允许前端跨域请求

app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 最大 32MB
app.config["UPLOAD_FOLDER"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"
)

# ================================================================
# 全局引擎实例（单例，避免重复加载模型）
# ================================================================

_engine = None
_preprocessor = None
_parser = None
_extractor = None
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
MAX_ZIP_MEMBERS = 300
MAX_ZIP_UNCOMPRESSED = 256 * 1024 * 1024

# 任务状态存储（内存字典，重启丢失，课设够用）
_jobs: dict[str, dict] = {}


def get_engine():
    global _engine
    if _engine is None:
        _engine = OCREngine()
    return _engine


def get_preprocessor():
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = Preprocessor()
    return _preprocessor


def get_parser():
    global _parser
    if _parser is None:
        _parser = LayoutParser()
    return _parser


def get_extractor():
    global _extractor
    if _extractor is None:
        _extractor = FieldExtractor()
    return _extractor


def is_valid_job_id(job_id: str) -> bool:
    return bool(JOB_ID_RE.fullmatch(job_id or ""))


def _uploads_root() -> Path:
    return Path(app.config["UPLOAD_FOLDER"]).resolve()


def _ensure_under_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if os.path.commonpath([str(root), str(resolved)]) != str(root):
        raise ValueError("path escapes upload directory")
    return resolved


def job_dir(job_id: str, create: bool = True) -> str:
    """每个任务的独立目录"""
    if not is_valid_job_id(job_id):
        raise ValueError("invalid job_id")
    root = _uploads_root()
    d = _ensure_under_root(root / job_id, root)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return str(d)


def read_json_file(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_original_file(job_id: str):
    d = job_dir(job_id, create=False)
    if not os.path.isdir(d):
        return None, None
    for ext in sorted(ALLOWED_EXTENSIONS):
        candidate = os.path.join(d, f"original.{ext}")
        if os.path.exists(candidate):
            return candidate, ext
    return None, None


def apply_corrections(result: dict | None, corrections: dict | None) -> dict:
    result_copy = copy.deepcopy(result or {})
    clean_corrections = corrections or {}
    result_copy["corrections"] = clean_corrections
    fields = result_copy.get("fields", {})
    if isinstance(fields, dict):
        for fname, corrected_val in clean_corrections.items():
            if fname in fields and isinstance(fields[fname], dict):
                fields[fname]["corrected"] = corrected_val
    return result_copy


def load_job(job_id: str):
    if not is_valid_job_id(job_id):
        return None
    if job_id in _jobs:
        return _jobs[job_id]

    d = job_dir(job_id, create=False)
    if not os.path.isdir(d):
        return None

    result = read_json_file(os.path.join(d, "result.json"), None)
    corrections = read_json_file(os.path.join(d, "corrections.json"), {}) or {}
    file_path, file_type = find_original_file(job_id)

    if result is None and file_path is None:
        return None

    filename = (result or {}).get("filename") or (os.path.basename(file_path) if file_path else "")
    status = "corrected" if corrections else ("done" if result else "uploaded")
    job = {
        "id": job_id,
        "filename": filename,
        "file_type": file_type or "",
        "file_path": file_path or "",
        "status": status,
        "created_at": (result or {}).get("recognized_at", ""),
        "result": result,
        "corrections": corrections,
    }
    _jobs[job_id] = job
    return job


def load_blocks(job_id: str):
    return read_json_file(os.path.join(job_dir(job_id, create=False), "blocks.json"), []) or []


def safe_extract_allowed_zip(zip_path: str, extract_dir: str):
    root = Path(extract_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    extracted = []
    total_size = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = [info for info in zf.infolist() if not info.is_dir()]
        if len(members) > MAX_ZIP_MEMBERS:
            raise ValueError(f"ZIP contains too many files, max {MAX_ZIP_MEMBERS}")

        for info in members:
            total_size += info.file_size
            if total_size > MAX_ZIP_UNCOMPRESSED:
                raise ValueError("ZIP uncompressed size is too large")

            raw_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(raw_name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe ZIP member path: {info.filename}")

            ext = member_path.name.rsplit(".", 1)[-1].lower() if "." in member_path.name else ""
            if ext not in ALLOWED_EXTENSIONS:
                continue

            dest = _ensure_under_root(root.joinpath(*member_path.parts), root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(str(dest))

    return extracted


@app.before_request
def validate_route_job_id():
    job_id = (request.view_args or {}).get("job_id")
    if job_id is not None and not is_valid_job_id(job_id):
        return jsonify({"error": "invalid job_id"}), 400


# ================================================================
# 工具函数
# ================================================================

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tiff", "bmp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_pdf(filename: str) -> bool:
    return filename.rsplit(".", 1)[1].lower() == "pdf" if "." in filename else False


def run_recognition_pipeline(job: dict):
    file_path = job["file_path"]
    if not os.path.exists(file_path):
        raise FileNotFoundError("文件已丢失")

    engine = get_engine()
    preprocessor = get_preprocessor()
    parser = get_parser()
    extractor = get_extractor()
    warnings = []

    if is_pdf(job["filename"]):
        ocr_results = engine.recognize_pdf(file_path)
        if not ocr_results:
            raise ValueError("PDF 没有可识别页面")
        page = ocr_results[0]
        page_count = len(ocr_results)
        if page_count > 1:
            warnings.append(f"PDF has {page_count} pages; only page 1 is processed")
        blocks = page["blocks"]
        img_size = page["image_size"]
    else:
        from PIL import Image
        with Image.open(file_path) as img:
            pp_img = preprocessor.process_image(img, engine=engine)
            blocks = engine.recognize_image(pp_img)
            img_size = pp_img.size
        page_count = 1

    regions = parser.parse(blocks, img_size)
    extracted = extractor.extract(regions, img_size, blocks=blocks)
    meta = dict(extracted.get("meta", {}))
    meta["page_count"] = page_count
    meta["processed_page"] = 1
    if warnings:
        meta["warnings"] = warnings
    extracted["meta"] = meta

    result_data = {
        **extracted,
        "job_id": job["id"],
        "filename": job["filename"],
        "recognized_at": datetime.now().isoformat(),
    }

    d = job_dir(job["id"])
    write_json_file(os.path.join(d, "result.json"), result_data)
    write_json_file(os.path.join(d, "blocks.json"), blocks)

    job["status"] = "done"
    job["result"] = result_data
    job.pop("error", None)
    return result_data


# ================================================================
# API: 文件上传
# ================================================================

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """上传单文件 PDF 或图片，返回 job_id"""
    if "file" not in request.files:
        return jsonify({"error": "缺少 file 字段"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": f"不支持的文件类型，允许: {ALLOWED_EXTENSIONS}"}), 400

    job_id = uuid.uuid4().hex[:12]
    d = job_dir(job_id)

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    saved_path = os.path.join(d, f"original.{ext}")
    file.save(saved_path)

    _jobs[job_id] = {
        "id": job_id,
        "filename": filename,
        "file_type": ext,
        "file_path": saved_path,
        "status": "uploaded",
        "created_at": datetime.now().isoformat(),
        "result": None,
        "corrections": {},
    }

    return jsonify({
        "job_id": job_id,
        "filename": filename,
        "status": "uploaded",
    }), 201


# ================================================================
# API: 触发识别
# ================================================================

@app.route("/api/recognize/<job_id>", methods=["POST"])
def api_recognize(job_id):
    """触发完整识别流水线"""
    job = load_job(job_id)
    if job is None:
        return jsonify({"error": "任务不存在"}), 404

    if not job.get("file_path") or not os.path.exists(job["file_path"]):
        return jsonify({"error": "文件已丢失"}), 404

    try:
        job["status"] = "processing"
        result_data = run_recognition_pipeline(job)
        meta = result_data.get("meta", {})

        return jsonify({
            "job_id": job_id,
            "status": "done",
            "template": result_data["template"],
            "fields_count": meta.get("fields_extracted", 0),
            "fields_total": meta.get("fields_total", 0),
            "table_rows": meta.get("table_rows", 0),
            "warnings": meta.get("warnings", []),
        })

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        return jsonify({"error": f"识别失败: {str(e)}"}), 500


# ================================================================
# API: 获取结果
# ================================================================

@app.route("/api/result/<job_id>", methods=["GET"])
def api_result(job_id):
    """获取识别结果（含 bbox 标注数据）— 优先从内存，回退到磁盘"""
    job = load_job(job_id)

    # 如果内存中没有，从磁盘读取（支持重启后访问历史）
    if job is None:
        return jsonify({"error": "任务不存在"}), 404

    if job["status"] in ("uploaded", "processing"):
        return jsonify({"job_id": job_id, "status": job["status"]}), 200

    if job["status"] == "error":
        return jsonify({"job_id": job_id, "status": "error", "error": job.get("error", "")}), 500

    result = apply_corrections(job.get("result", {}), job.get("corrections", {}))
    result["status"] = job["status"]
    result["corrections"] = job.get("corrections", {})
    result["blocks"] = load_blocks(job_id)

    return jsonify(result)


# ================================================================
# API: 人工校正
# ================================================================

@app.route("/api/correct/<job_id>", methods=["POST"])
def api_correct(job_id):
    """保存前端发来的人工校正字段值"""
    job = load_job(job_id)
    if job is None:
        return jsonify({"error": "任务不存在"}), 404

    data = request.get_json(silent=True)
    if not data or "fields" not in data:
        return jsonify({"error": "请求体需包含 fields 对象"}), 400

    if job.get("result") is None:
        return jsonify({"error": "尚未识别"}), 400

    # 保存校正
    corrections = dict(job.get("corrections") or {})
    corrections.update(data["fields"])  # {field_name: corrected_value, ...}
    job["corrections"] = corrections
    job["status"] = "corrected"

    # 写入文件
    corr_path = os.path.join(job_dir(job_id), "corrections.json")
    write_json_file(corr_path, corrections)

    return jsonify({
        "job_id": job_id,
        "status": "corrected",
        "corrected_fields": list(corrections.keys()),
    })


# ================================================================
# API: 导出
# ================================================================

@app.route("/api/export/<job_id>", methods=["GET"])
def api_export(job_id):
    """导出结果，format=json|xlsx (默认 json)"""
    job = load_job(job_id)
    if job is None:
        return jsonify({"error": "任务不存在"}), 404

    if job.get("result") is None:
        return jsonify({"error": "尚未识别"}), 400

    export_format = request.args.get("format", "json").lower()

    # 合并原始结果 + 校正
    result = apply_corrections(job["result"], job.get("corrections", {}))
    fields = result.get("fields", {})

    if export_format == "xlsx":
        return _export_excel(job_id, result, fields)
    else:
        return _export_json(job_id, result)


def _export_json(job_id, result):
    """导出为 JSON 文件"""
    export_path = os.path.join(job_dir(job_id), "export.json")
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return send_file(export_path, as_attachment=True,
                     download_name=f"{job_id}_result.json",
                     mimetype="application/json")


def _export_excel(job_id, result, fields):
    """导出为 Excel 文件"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()

    # ---- Sheet 1: 字段提取结果 ----
    ws1 = wb.active
    ws1.title = "字段提取"

    # 表头样式
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="003882", end_color="003882", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")

    ws1.append(["字段名", "原始值", "清洗值", "置信度", "锚点文本", "校正值"])
    for cell in ws1[1]:
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    corrections = result.get("corrections", {})
    for fname, info in fields.items():
        conf = info.get("confidence", 0)
        ws1.append([
            fname,
            info.get("value", ""),
            info.get("cleaned", ""),
            f"{conf:.0%}" if isinstance(conf, (int, float)) else str(conf),
            info.get("anchor_text", ""),
            corrections.get(fname, ""),
        ])

    # 调整列宽
    ws1.column_dimensions["A"].width = 20
    ws1.column_dimensions["B"].width = 30
    ws1.column_dimensions["C"].width = 30
    ws1.column_dimensions["D"].width = 10
    ws1.column_dimensions["E"].width = 20
    ws1.column_dimensions["F"].width = 20

    # ---- Sheet 2: 货物明细表格 ----
    table = result.get("table", {})
    if table and table.get("headers"):
        ws2 = wb.create_sheet("货物明细")
        ws2.append(table["headers"])
        for cell in ws2[1]:
            cell.font = header_font_white
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for row in table.get("rows", []):
            ws2.append(row)

        for col_letter in ["A", "B", "C", "D", "E", "F", "G", "H"]:
            ws2.column_dimensions[col_letter].width = 18

    # ---- Sheet 3: 元信息 ----
    ws3 = wb.create_sheet("元信息")
    ws3.append(["键", "值"])
    for cell in ws3[1]:
        cell.font = header_font
    meta = {
        "任务 ID": job_id,
        "文件名": result.get("filename", ""),
        "识别版式": result.get("template", ""),
        "图片尺寸": str(result.get("image_size", "")),
        "文本块数": result.get("blocks_count", 0),
        "识别时间": result.get("recognized_at", ""),
    }
    for k, v in meta.items():
        ws3.append([k, str(v)])
    ws3.column_dimensions["A"].width = 15
    ws3.column_dimensions["B"].width = 40

    export_path = os.path.join(job_dir(job_id), "export.xlsx")
    wb.save(export_path)
    return send_file(export_path, as_attachment=True,
                     download_name=f"{job_id}_result.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ================================================================
# API: 获取原始图片
# ================================================================

@app.route("/api/image/<job_id>", methods=["GET"])
def api_image(job_id):
    """返回原始图片（PDF 转第一页 PNG）供前端 Canvas 展示"""
    job = load_job(job_id)
    if job is None:
        return jsonify({"error": "任务不存在"}), 404

    file_path = job["file_path"]
    if not os.path.exists(file_path):
        return jsonify({"error": "文件已丢失"}), 404

    ext = job.get("file_type", "pdf")

    if ext == "pdf":
        # PDF → 第一页渲染为 PNG（200 DPI 与 OCR 引擎一致，标注框才对齐）
        import fitz
        from PIL import Image
        import io

        doc = fitz.open(file_path)
        pix = doc[0].get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    else:
        return send_file(file_path, mimetype=f"image/{ext}")


# ================================================================
# API: ZIP 批量上传 + 批量识别
# ================================================================

@app.route("/api/upload/zip", methods=["POST"])
def api_upload_zip():
    """上传 ZIP 压缩包，提取文件，返回批量 job 列表"""
    if "file" not in request.files:
        return jsonify({"error": "缺少 file 字段"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return jsonify({"error": "只支持 .zip 文件"}), 400

    batch_id = uuid.uuid4().hex[:12]
    batch_dir = os.path.join(app.config["UPLOAD_FOLDER"], "batch_" + batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    # 解压
    zip_path = os.path.join(batch_dir, "upload.zip")
    file.save(zip_path)
    extract_dir = os.path.join(batch_dir, "files")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        extracted_files = safe_extract_allowed_zip(zip_path, extract_dir)
    except (zipfile.BadZipFile, ValueError) as e:
        shutil.rmtree(batch_dir, ignore_errors=True)
        return jsonify({"error": f"ZIP 解压失败: {str(e)}"}), 400

    # 遍历解压后的文件，为每个合法文件创建 job
    jobs = []
    for src in sorted(extracted_files):
        fname = os.path.basename(src)
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        job_id = uuid.uuid4().hex[:12]
        d = job_dir(job_id)
        dst = os.path.join(d, f"original.{ext}")
        shutil.copy2(src, dst)

        _jobs[job_id] = {
            "id": job_id,
            "filename": fname,
            "file_type": ext,
            "file_path": dst,
            "status": "uploaded",
            "batch_id": batch_id,
            "created_at": datetime.now().isoformat(),
            "result": None,
            "corrections": {},
        }
        jobs.append({"job_id": job_id, "filename": fname})

    # 清理临时文件
    os.remove(zip_path)
    shutil.rmtree(extract_dir, ignore_errors=True)

    return jsonify({
        "batch_id": batch_id,
        "count": len(jobs),
        "jobs": jobs,
    }), 201


@app.route("/api/recognize/batch", methods=["POST"])
def api_recognize_batch():
    """批量触发识别 — 逐个处理并返回结果"""
    data = request.get_json(silent=True)
    if not data or "job_ids" not in data:
        return jsonify({"error": "请求体需包含 job_ids 数组"}), 400

    job_ids = data["job_ids"]
    results = []
    for job_id in job_ids:
        job = load_job(job_id)
        if not job:
            results.append({"job_id": job_id, "status": "error", "error": "任务不存在"})
            continue

        job["status"] = "processing"
        file_path = job.get("file_path")
        if not file_path or not os.path.exists(file_path):
            job["status"] = "error"
            results.append({"job_id": job_id, "status": "error", "error": "文件丢失"})
            continue

        try:
            result_data = run_recognition_pipeline(job)
            meta = result_data.get("meta", {})
            results.append({
                "job_id": job_id,
                "filename": job["filename"],
                "status": "done",
                "template": result_data["template"],
                "fields_extracted": meta.get("fields_extracted", 0),
                "fields_total": meta.get("fields_total", 0),
                "warnings": meta.get("warnings", []),
            })
            continue

        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            results.append({"job_id": job_id, "status": "error", "error": str(e)})

    return jsonify({"results": results})


@app.route("/api/results/batch/<batch_id>", methods=["GET"])
def api_batch_results(batch_id):
    """获取某批次的全部结果汇总"""
    batch_jobs = [j for j in _jobs.values() if j.get("batch_id") == batch_id]
    summary = []
    for job in batch_jobs:
        summary.append({
            "job_id": job["id"],
            "filename": job.get("filename", ""),
            "status": job.get("status", ""),
            "template": job.get("result", {}).get("template", "?") if job.get("result") else "?",
            "fields_extracted": job.get("result", {}).get("meta", {}).get("fields_extracted", 0) if job.get("result") else 0,
            "fields_total": job.get("result", {}).get("meta", {}).get("fields_total", 0) if job.get("result") else 0,
        })
    return jsonify({"batch_id": batch_id, "count": len(summary), "jobs": summary})


# ================================================================
# API: 版式配置查询
# ================================================================

@app.route("/api/config", methods=["GET"])
def api_config():
    """返回当前 config.yaml 的可视化友好格式（供前端版式管理展示）"""
    extractor = get_extractor()
    config_templates = extractor.config.get("templates", {})

    templates = []
    for tname, tcfg in config_templates.items():
        tpl_fields = tcfg.get("fields", {})
        output_list = tcfg.get("output", list(tpl_fields.keys()))

        tpl_info = {
            "name": tname,
            "has_table": tcfg.get("has_table", False),
            "keywords": tcfg.get("keywords", []),
            "fields": [],
        }
        for fname in output_list:
            fdef = tpl_fields.get(fname, {})
            f_info = {
                "key": fname,
                "label": fdef.get("label", fname),
                "anchors": fdef.get("anchors", []),
                "position": fdef.get("position", "right"),
                "validator": fdef.get("validator") or "",
            }
            tpl_info["fields"].append(f_info)
        templates.append(tpl_info)

    return jsonify({
        "templates": templates,
        "validators": extractor.validators_cfg,
    })


# ================================================================
# API: 版式管理 — 删除版式
# ================================================================

@app.route("/api/config/<template_name>", methods=["DELETE"])
def api_config_delete(template_name):
    """删除指定版式（同步更新 config.yaml + 热重载）"""
    import yaml

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )
    if not os.path.exists(config_path):
        return jsonify({"error": "config.yaml 不存在"}), 404

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if template_name not in cfg.get("templates", {}):
        return jsonify({"error": f"版式 '{template_name}' 不存在"}), 404

    del cfg["templates"][template_name]

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    get_extractor().reload_config()

    return jsonify({"success": True, "deleted": template_name})


# ================================================================
# API: 版式管理 — 应用 Few-shot 生成的配置
# ================================================================

@app.route("/api/config/apply", methods=["POST"])
def api_config_apply():
    """
    将 Few-shot 生成的版式配置写入 config.yaml（新自包含格式）

    Body: { "template_name": "...", "keywords": [...], "fields": {...} }
    """
    import yaml

    data = request.get_json(silent=True)
    if not data or "template_name" not in data:
        return jsonify({"error": "缺少 template_name"}), 400

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )
    if not os.path.exists(config_path):
        return jsonify({"error": "config.yaml 不存在"}), 404

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    template_name = data["template_name"]
    keywords = data.get("keywords", [])
    fields = data.get("fields", {})

    # 构建自包含模板条目
    template_fields = {}
    for fname, fcfg in fields.items():
        entry = {
            "label": fcfg.get("label", fname),
            "anchors": fcfg.get("anchors", [fcfg.get("anchor", fname)]),
            "position": fcfg.get("position", "right"),
        }
        if fcfg.get("validator"):
            entry["validator"] = fcfg["validator"]
        if fcfg.get("search_in"):
            entry["search_in"] = fcfg["search_in"]
        template_fields[fname] = entry

    if "templates" not in cfg:
        cfg["templates"] = {}
    cfg["templates"][template_name] = {
        "keywords": keywords,
        "has_table": False,
        "fields": template_fields,
        "output": list(fields.keys()),
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    get_extractor().reload_config()

    return jsonify({"success": True, "template": template_name, "fields_count": len(fields)})


# ================================================================
# API: 历史记录
# ================================================================

@app.route("/api/history", methods=["GET"])
def api_history():
    """返回所有完成过的识别任务列表（从磁盘读取，重启不丢失）"""
    history = []

    # 从 uploads 目录扫描已保存的 result.json
    uploads = app.config["UPLOAD_FOLDER"]
    if os.path.exists(uploads):
        for job_name in os.listdir(uploads):
            if not is_valid_job_id(job_name):
                continue
            job_dir_path = os.path.join(uploads, job_name)
            if not os.path.isdir(job_dir_path):
                continue
            result_path = os.path.join(job_dir_path, "result.json")
            if not os.path.exists(result_path):
                continue
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    r = json.load(f)
                m = r.get("meta", {})
                history.append({
                    "job_id": job_name,
                    "filename": r.get("filename", ""),
                    "template": r.get("template", "?"),
                    "fields_extracted": m.get("fields_extracted", 0),
                    "fields_total": m.get("fields_total", 0),
                    "ocr_blocks": m.get("ocr_blocks", 0),
                    "recognized_at": r.get("recognized_at", ""),
                })
            except Exception:
                pass

    # 也加上内存中已识别但还未写盘的任务
    for jid, job in _jobs.items():
        if job.get("status") == "done" and not any(h["job_id"] == jid for h in history):
            r = job.get("result", {})
            m = r.get("meta", {})
            history.append({
                "job_id": jid,
                "filename": job.get("filename", ""),
                "template": r.get("template", "?"),
                "fields_extracted": m.get("fields_extracted", 0),
                "fields_total": m.get("fields_total", 0),
                "ocr_blocks": m.get("ocr_blocks", 0),
                "recognized_at": r.get("recognized_at", ""),
            })

    # 按时间降序
    history.sort(key=lambda x: x.get("recognized_at", ""), reverse=True)
    return jsonify({"history": history, "count": len(history)})


@app.route("/api/history/<job_id>", methods=["DELETE"])
def api_history_delete(job_id):
    """删除单条历史记录（磁盘 + 内存）"""
    deleted = False

    # 从内存移除
    if job_id in _jobs:
        del _jobs[job_id]
        deleted = True

    # 从磁盘删除
    target_dir = job_dir(job_id, create=False)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
        deleted = True

    if deleted:
        return jsonify({"success": True, "deleted": job_id})
    return jsonify({"error": "记录不存在"}), 404


@app.route("/api/history", methods=["DELETE"])
def api_history_delete_all():
    """删除全部历史记录（磁盘 + 内存）"""
    count = 0

    # 清空所有已完成任务（保留可能正在处理中的？全删即可）
    done_ids = [jid for jid, j in _jobs.items() if j.get("status") == "done"]
    for jid in done_ids:
        del _jobs[jid]
        count += 1

    # 删除 uploads 目录下所有子目录
    uploads = app.config["UPLOAD_FOLDER"]
    if os.path.exists(uploads):
        for name in os.listdir(uploads):
            if not is_valid_job_id(name):
                continue
            dir_path = os.path.join(uploads, name)
            if os.path.isdir(dir_path) and os.path.exists(os.path.join(dir_path, "result.json")):
                shutil.rmtree(dir_path, ignore_errors=True)
                count += 1

    return jsonify({"success": True, "deleted_count": count})


# ================================================================
# API: Few-shot 版式学习
# ================================================================

@app.route("/api/fewshot/learn", methods=["POST"])
def api_fewshot_learn():
    """
    Few-shot 版式学习：上传 1~5 份 PDF + GT JSON → 自动生成配置

    Body (multipart/form-data):
      - files: PDF 文件列表
      - gts:   JSON 字符串数组 (每个对应一份 PDF)
    """
    from fewshot import FewShotLearner

    if "files" not in request.files:
        return jsonify({"error": "缺少 files"}), 400

    files = request.files.getlist("files")
    gt_strs = request.form.getlist("gts")

    if len(files) != len(gt_strs):
        return jsonify({"error": "files 和 gts 数量不匹配"}), 400
    if len(files) < 1:
        return jsonify({"error": "至少需要 1 份样本"}), 400
    if len(files) > 5:
        return jsonify({"error": "最多 5 份样本"}), 400

    # 保存临时文件
    tmp_dir = tempfile.mkdtemp()
    samples = []
    try:
        for i, (f, gt_str) in enumerate(zip(files, gt_strs)):
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "pdf"
            tmp_path = os.path.join(tmp_dir, f"sample_{i}.{ext}")
            f.save(tmp_path)
            gt = json.loads(gt_str)
            samples.append((tmp_path, gt))

        learner = FewShotLearner()
        result = learner.learn(samples)

        return jsonify({
            "success": True,
            "result": result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ================================================================
# API: 健康检查
# ================================================================

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "ok",
        "active_jobs": len(_jobs),
    })


@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    """列出所有任务状态"""
    summary = []
    for jid, job in _jobs.items():
        summary.append({
            "job_id": jid,
            "filename": job.get("filename", ""),
            "status": job.get("status", "unknown"),
            "created_at": job.get("created_at", ""),
        })
    return jsonify({"jobs": summary})


# ================================================================
# 启动
# ================================================================

if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    print("\n  SmartLDS API Server")
    print(f"  上传目录: {app.config['UPLOAD_FOLDER']}")
    print(f"  最大文件: {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)}MB")
    print("\n  端点:")
    print("    POST /api/upload          上传文件")
    print("    POST /api/recognize/<id>  触发识别")
    print("    GET  /api/result/<id>     获取结果")
    print("    POST /api/correct/<id>    人工校正")
    print("    GET  /api/export/<id>     导出 (format=json|xlsx)")
    print("    GET  /api/image/<id>      获取图片")
    print("    GET  /api/health          健康检查")
    print()
    app.run(host="0.0.0.0", port=5000, debug=True)

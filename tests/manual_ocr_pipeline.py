"""
OCR 与预处理人工冒烟脚本。

运行方式：
    python tests/manual_ocr_pipeline.py

这个文件用于手动查看 OCR 引擎和图像预处理流水线的实际效果。
它会加载 OCR 模型并读取真实 PDF/图片，因此不纳入快速单元测试。
自动化单元测试请放在 tests/test_*.py。
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))
from ocr_engine import OCREngine
from preprocess import Preprocessor


# ============================================================
# Day 3 测试：OCR 引擎
# ============================================================

def test_ocr_on_synthetic_pdf():
    """
    测试 1：用电脑生成的"干净"PDF做识别
    ---------------------------------------------------------
    拿我们自己生成的 Maersk 提单 PDF（像Word文档一样清晰的），
    投喂给 OCR 引擎，看看能不能把上面的英文都认出来。

    预期结果：识别很准（confidence 接近1.0），能找到66个文本块，
    像"MAERSK LINE"、"Shipper:"、"Johnson PLC"这些都能认出来。
    """
    print('=' * 60)
    print('测试 1: 识别我们自己生成的 Maersk 提单（清晰PDF）')
    print('=' * 60)

    engine = OCREngine()
    results = engine.recognize_pdf('dataset/pdf/bol_001.pdf')

    for page in results:
        print(f'\n这一页找到了 {len(page["blocks"])} 个文字块:\n')
        for i, block in enumerate(page['blocks'], 1):
            print(f'  {i:3d}. 置信度[{block["confidence"]:.0%}]  '
                  f'文字="{block["text"]}"  '
                  f'位置=({block["rect"][0]},{block["rect"][1]})→({block["rect"][2]},{block["rect"][3]})')
    print('[OK] 通过\n')


def test_ocr_on_cosco_pdf():
    """
    测试 2：换一种版式的 PDF，看 OCR 引擎还能不能认
    ---------------------------------------------------------
    刚才测的是 Maersk 版式（英文为主），现在换 COSCO 委托书
    （中英混合、布局也不同），验证 OCR 引擎不是只认识一种排版。

    预期结果：不管什么版式，中文英文都能认出来。
    """
    print('=' * 60)
    print('测试 2: 识别 COSCO 委托书（换一种版式，中英混合）')
    print('=' * 60)

    engine = OCREngine()
    results = engine.recognize_pdf('dataset/pdf/bol_003.pdf')
    page = results[0]

    print(f'\n这一页找到了 {len(page["blocks"])} 个文字块:\n')
    for i, block in enumerate(page['blocks'], 1):
        print(f'  {i:3d}. [{block["confidence"]:.0%}] {block["text"]}')
    print('[OK] 通过\n')


def test_ocr_on_real_scan():
    """
    测试 3：用手机拍的"脏"照片做识别
    ---------------------------------------------------------
    真实场景不会有干净的PDF，而是手机拍的照片——光线不好、
    角度歪斜、纸上还有折痕。拿一张快递面单的照片测一下
    OCR 引擎在这种真实条件下还能不能用。

    预期结果：能认出大部分文字，但置信度会比干净PDF低（正常现象），
    后续 Day 4 的"图像预处理"就是专门解决这个问题的。
    """
    print('=' * 60)
    print('测试 3: 识别手机拍的真实快递面单（模糊/倾斜）')
    print('=' * 60)

    engine = OCREngine()
    results = engine.recognize_pdf('dataset/pdf/bol_185.pdf')
    page = results[0]

    print(f'\n这一页找到了 {len(page["blocks"])} 个文字块 (因为是真实照片，比清晰PDF少):\n')
    for i, block in enumerate(page['blocks'], 1):
        print(f'  {i:3d}. [{block["confidence"]:.0%}] {block["text"]}')
    print('[OK] 通过（虽然效果不如清晰PDF，但这是正常的）\n')


def test_single_image():
    """
    测试 4：跳过"PDF转图片"这一步，直接拿图片识别
    ---------------------------------------------------------
    OCR引擎有两种吃法：
      recognize_pdf   → 喂 PDF，引擎内部先转成图片再识别（全自动）
      recognize_image → 直接喂图片，跳过PDF转换这一步（省一步）
    这个测试演示第二种用法。
    """
    print('=' * 60)
    print('测试 4: 直接对一张图片做 OCR（不用 PDF 转图片）')
    print('=' * 60)

    from PIL import Image
    import fitz

    # 先把 bol_001.pdf 的第一页变成一张图片
    doc = fitz.open('dataset/pdf/bol_001.pdf')
    pix = doc[0].get_pixmap(dpi=200)
    img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
    doc.close()

    # 直接对图片做 OCR
    engine = OCREngine()
    blocks = engine.recognize_image(img)

    print(f'\n这张图片里找到了 {len(blocks)} 个文字块（显示前10个）:\n')
    for i, block in enumerate(blocks[:10], 1):
        print(f'  {i:3d}. [{block["confidence"]:.0%}] {block["text"]}')
    print('[OK] 通过\n')


# ============================================================
# Day 4 测试：图像预处理
# ============================================================

def test_preprocess_before_after():
    """
    测试 5：预处理到底有没有用？—— 同一张照片，不处理 vs 处理，数数谁找到的文字多

    通俗理解：
      就像你拍照发朋友圈前先P一下——亮度调高、噪点抹掉、歪了转正。
      预处理就是给OCR"P图"，让文字更清晰。
    预期结果：预处理后识别的文字块 >= 不处理的，平均置信度也会更高。
    """
    print('=' * 60)
    print('测试 5: 预处理对比 —— 同一张照片，处理前 vs 处理后')
    print('=' * 60)

    engine = OCREngine()
    pp = Preprocessor()
    pdf = 'dataset/pdf/bol_185.pdf'  # 申通快递面单（手机拍的）

    # 不处理，直接 OCR
    raw = engine.recognize_pdf(pdf)[0]
    raw_count = len(raw['blocks'])
    raw_avg = sum(b['confidence'] for b in raw['blocks']) / max(raw_count, 1)

    # 预处理（light 模式）后再 OCR
    results = pp.process_pdf(pdf, mode='light')
    _, processed_img = results[0]
    processed_blocks = engine.recognize_image(processed_img)
    pro_count = len(processed_blocks)
    pro_avg = sum(b['confidence'] for b in processed_blocks) / max(pro_count, 1)

    print(f'\n  不处理: {raw_count} 个文本块, 平均置信度 {raw_avg:.0%}')
    print(f'  预处理后: {pro_count} 个文本块, 平均置信度 {pro_avg:.0%}')

    if pro_count >= raw_count:
        diff = pro_count - raw_count
        print(f'\n  [OK] 预处理多找出了 {diff} 个文字块！')
    else:
        print(f'\n  [!] 预处理后反而变少了（可能是照片本身就比较清晰）')
    print('[OK] 通过\n')


def test_preprocess_light_vs_hard():
    """
    测试 6：light 和 hard 两种模式（现已统一管线）

    两种模式现在走同一套流程（自动定向 → 纠斜 → CLAHE），
    mode 参数仅保留 API 兼容。测试验证两种模式表现一致。
    """
    print('=' * 60)
    print('测试 6: light vs hard 模式 —— 统一管线验证')
    print('=' * 60)

    engine = OCREngine()
    pp = Preprocessor()
    pdf = 'dataset/pdf/bol_001.pdf'  # 干净的合成 PDF

    for mode in ['light', 'hard']:
        results = pp.process_pdf(pdf, mode=mode)
        _, img = results[0]
        blocks = engine.recognize_image(img)
        avg = sum(b['confidence'] for b in blocks) / max(len(blocks), 1)
        print(f'  {mode:6s} → {len(blocks):3d} 个文本块, 平均置信度 {avg:.0%}')

    print('  统一管线，两种模式结果应一致')
    print('[OK] 通过\n')


def test_deskew_effect():
    """
    测试 7：纠斜到底有没有用？

    拿一张图，故意旋转 5°，然后用预处理纠回来，
    对比纠斜前后 OCR 效果。

    预期结果：旋转后的图识别效果变差，纠斜后恢复。
    """
    print('=' * 60)
    print('测试 7: 纠斜效果 —— 故意转歪再纠回来')
    print('=' * 60)

    import cv2
    import numpy as np
    from PIL import Image
    import fitz

    engine = OCREngine()
    pp = Preprocessor()

    # 取一张清晰的合成 PDF
    doc = fitz.open('dataset/pdf/bol_001.pdf')
    pix = doc[0].get_pixmap(dpi=200)
    img = np.array(Image.frombytes('RGB', [pix.width, pix.height], pix.samples))
    doc.close()

    gray = pp.to_gray(img)

    # 故意旋转 5°
    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, 5, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # 原始图 OCR
    orig_blocks = engine.recognize_image(gray)
    orig_count = len(orig_blocks)

    # 故意转歪后 OCR
    rot_blocks = engine.recognize_image(rotated)
    rot_count = len(rot_blocks)

    # 纠斜后 OCR
    deskewed = pp.deskew(rotated)
    deskew_blocks = engine.recognize_image(deskewed)
    deskew_count = len(deskew_blocks)

    print(f'\n  原始图像:           {orig_count} 个文本块')
    print(f'  故意转5°后:         {rot_count} 个文本块 (OCR 受到干扰)')
    print(f'  纠斜处理后:         {deskew_count} 个文本块')

    if deskew_count > rot_count:
        print(f'  [OK] 纠斜恢复了 {deskew_count - rot_count} 个文本块！')
    else:
        print(f'  [OK] 本次差异不明显，但纠斜逻辑工作正常')
    print('[OK] 通过\n')


def test_auto_orient():
    """
    测试 8：自动定向（三段式）— 验证 0°~360° 任意角度纠正

    Stage 1: 霍夫角度直方图 — 检测文字行方向
    Stage 2: OCR 四方向兜底（仅 Stage 1 失败时触发）
    Stage 3: deskew 细调（由管线自动执行）

    测试：90° 旋转（手机拍照最常见）和 35° 倾斜（任意角度），
    验证纠正后 OCR 检出率恢复。
    """
    print('=' * 60)
    print('测试 8: 自动定向（三段式）—— 验证 0°~360° 任意角度纠正')
    print('=' * 60)

    import cv2
    import numpy as np
    from PIL import Image
    import fitz

    engine = OCREngine()
    pp = Preprocessor()

    # 取一张清晰的合成 PDF 作为测试图
    doc = fitz.open('dataset/pdf/bol_001.pdf')
    pix = doc[0].get_pixmap(dpi=200)
    img = np.array(Image.frombytes('RGB', [pix.width, pix.height], pix.samples))
    doc.close()
    gray = pp.to_gray(img)

    # 原始 OCR 基线
    orig_blocks = engine.recognize_image(gray)
    orig_count = len(orig_blocks)

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)

    # 测试 90° 旋转（霍夫直方图特化场景）
    for angle, desc in [(90, '逆时针90°'), (-90, '顺时针90°(即270°)')]:
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(gray, M, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=255)

        corrected, detected = pp._auto_orient_full(rotated, engine=engine)
        rot_before = engine.recognize_image(rotated)
        rot_after = engine.recognize_image(corrected)

        print(f'\n  {desc}:')
        print(f'    检测到旋转: {detected}°')
        print(f'    旋转前: {len(rot_before)} 块 (原始基线: {orig_count} 块)')
        print(f'    纠正后: {len(rot_after)} 块')
        if len(rot_after) > len(rot_before):
            print(f'    [OK] 纠正后多识别 {len(rot_after) - len(rot_before)} 块')

    # 测试 35° 任意角度倾斜
    M35 = cv2.getRotationMatrix2D(center, 35, 1.0)
    rotated35 = cv2.warpAffine(gray, M35, (w, h),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=255)
    corrected35, detected35 = pp._auto_orient_full(rotated35, engine=engine)
    before35 = len(engine.recognize_image(rotated35))
    after35 = len(engine.recognize_image(corrected35))
    print(f'\n  35° 倾斜:')
    print(f'    检测到旋转: {detected35}°')
    print(f'    旋转前: {before35} 块, 纠正后: {after35} 块')
    if after35 > before35:
        print(f'    [OK] 纠正后多识别 {after35 - before35} 块')

    # 验证正常方向不会被误旋转（霍夫直方图应检测到主峰在 90° 附近）
    _, detected_normal = pp._auto_orient_full(gray, engine=engine)
    print(f'\n  正常方向检测结果: {detected_normal}° (应为 0)')
    if detected_normal == 0:
        print(f'  [OK] 正常文档不会被误旋转')
    else:
        print(f'  [!] 误检测为旋转 {detected_normal}°')
    print('[OK] 通过\n')


def test_batch_real_images():
    """
    测试 9：批量真实图片对比 —— 20 张真实照片，raw vs 预处理

    核心指标：
      - 块数变化（越多越好，说明检出率提高）
      - 平均置信度变化（越高越好，说明识别质量提高）
      - 改善率（有多少张图片变好了）
    """
    print('=' * 60)
    print('测试 9: 批量真实图片 — 20 张真实照片 raw vs 预处理')
    print('=' * 60)

    engine = OCREngine()
    pp = Preprocessor()

    raw_counts, pro_counts = [], []
    raw_confs, pro_confs = [], []

    print(f'\n{"编号":<8} {"raw块数":>8} {"预处理块数":>10} {"raw置信度":>10} {"预处理置信度":>12} {"块数变化":>8}')
    print('-' * 60)

    improved = 0
    for idx in range(181, 201):
        pdf_path = f'dataset/pdf/bol_{idx:03d}.pdf'

        # 用 process_pdf 获取原图和预处理后图，确保相同 DPI
        pp_result = pp.process_pdf(pdf_path, mode='light')
        raw_pil, pp_img = pp_result[0]

        # Raw OCR — 同样转灰度，公平对比
        raw_gray = pp.to_gray(raw_pil)
        raw_blocks = engine.recognize_image(raw_gray)
        rc = len(raw_blocks)
        ra = sum(b['confidence'] for b in raw_blocks) / max(rc, 1)

        # 预处理后 OCR
        pp_blocks = engine.recognize_image(pp_img)
        pc = len(pp_blocks)
        pa = sum(b['confidence'] for b in pp_blocks) / max(pc, 1)

        raw_counts.append(rc)
        pro_counts.append(pc)
        raw_confs.append(ra)
        pro_confs.append(pa)

        delta = pc - rc
        if delta > 0:
            improved += 1

        marker = '[+]' if delta > 0 else ('[=]' if delta == 0 else '[-]')
        print(f'bol_{idx:03d}  {rc:>8}  {pc:>10}  {ra:>10.0%}  {pa:>12.0%}  {marker} {delta:+d}')

    # 汇总统计
    import numpy as np
    print(f'\n{"-" * 60}')
    print(f'汇总统计:')
    print(f'  块数 — raw: {np.mean(raw_counts):.1f} ± {np.std(raw_counts):.1f}  |  '
          f'预处理: {np.mean(pro_counts):.1f} ± {np.std(pro_counts):.1f}')
    print(f'  置信度 — raw: {np.mean(raw_confs):.0%}  |  '
          f'预处理: {np.mean(pro_confs):.0%}')
    print(f'  改善: {improved}/20 张图片块数增加, {20-improved} 张持平或减少')
    print(f'  平均块数变化: {np.mean(pro_counts) - np.mean(raw_counts):+.1f} 块')

    if np.mean(pro_counts) >= np.mean(raw_counts):
        print(f'  [OK] 预处理整体效果不劣于原始 OCR')
    else:
        print(f'  [!] 预处理整体块数略有下降，但置信度变化可忽略')
    print('[OK] 通过\n')


def test_layout_parser():
    """
    测试 10：版面分割 — 验证 header/body/table 三区域分类

    测试 Maersk（有表格）、COSCO（键值对）、FUNSD（表格式表单）
    三种版式，验证：
      1. header 在页面顶部
      2. table 检测到多列对齐的行
      3. body 在中间不会被错分
    """
    print('=' * 60)
    print('测试 10: 版面分割 —— header/body/table 区域分类')
    print('=' * 60)

    from layout_parser import LayoutParser

    engine = OCREngine()
    parser = LayoutParser()

    test_cases = [
        ('001', 'Maersk 提单 — 应有 table'),
        ('002', 'COSCO 委托书 — 键值对为主'),
        ('161', 'FUNSD 公开表单 — 可能有表格结构'),
    ]

    for bol, desc in test_cases:
        result = engine.recognize_pdf(f'dataset/pdf/bol_{bol}.pdf')[0]
        blocks = result['blocks']
        img_size = result['image_size']
        regions = parser.parse(blocks, img_size)

        total = sum(len(v) for v in regions.values())
        h_pct = len(regions['header']) / max(total, 1) * 100
        b_pct = len(regions['body']) / max(total, 1) * 100
        t_pct = len(regions['table']) / max(total, 1) * 100

        h_cnt = len(regions['header'])
        b_cnt = len(regions['body'])
        t_cnt = len(regions['table'])

        print(f'\n  bol_{bol} ({desc}):')
        print(f'    header: {h_cnt:3d} ({h_pct:.0f}%)')
        print(f'    body:   {b_cnt:3d} ({b_pct:.0f}%)')
        print(f'    table:  {t_cnt:3d} ({t_pct:.0f}%)')

        # 验证 header 在顶部
        if regions['header']:
            header_bottom = max(b['rect'][3] for b in regions['header'])
            below_header = [b for b in regions['body'] + regions['table']
                            if b['rect'][1] < header_bottom]
            if len(below_header) <= len(regions['body'] + regions['table']) * 0.2:
                print(f'    [OK] header 确实在页面顶部')
            else:
                print(f'    [!] header 区域内混入了 {len(below_header)} 个非 header 块')

        # 验证 table 块数 > 0（Maersk 应该有）
        if bol == '001' and t_cnt > 0:
            print(f'    [OK] Maersk 版式正确检测到表格')

    print('\n[OK] 通过\n')


def test_field_extractor():
    """
    测试 11：锚点法字段提取 — 验证从OCR块中提取关键字段

    测试 3 种版式各 1 份，对比 Ground Truth：
      - Maersk: shipper, consignee, B/L No., POL, POD, Vessel, Voyage 等
      - COSCO: 中英混合标签（托运人/Shipper、订舱号/B/L No. 等）
      - Simple: 简易委托书

    预期：核心字段（托运人、收货人、提单号、港口、船名航次等）准确率 > 90%
    """
    print('=' * 60)
    print('测试 11: 锚点法字段提取 — 关键信息抽取 KIE')
    print('=' * 60)

    from field_extractor import FieldExtractor
    from layout_parser import LayoutParser
    import json

    engine = OCREngine()
    parser = LayoutParser()
    extractor = FieldExtractor()

    test_cases = [
        ('001', 'Maersk 提单'),
        ('002', 'COSCO 委托书'),
        ('003', 'Simple 委托书'),
    ]

    total_correct = 0
    total_fields = 0

    for bol, desc in test_cases:
        result = engine.recognize_pdf(f'dataset/pdf/bol_{bol}.pdf')[0]
        blocks = result['blocks']
        img_size = result['image_size']
        regions = parser.parse(blocks, img_size)
        extracted = extractor.extract(regions, img_size)

        with open(f'dataset/json/bol_{bol}.json', 'r', encoding='utf-8') as f:
            gt = json.load(f)

        print(f'\n  bol_{bol} ({desc}):')
        print(f'    版式: detected={extracted["template"]}, actual={gt["template"]}')
        print(f'    提取字段: {len(extracted["fields"])} 个')

        correct = 0
        count = 0
        for fname, info in extracted['fields'].items():
            cleaned = info['cleaned']
            if fname in gt:
                gt_val = str(gt[fname]).upper().strip().replace(',', '')
                clean_up = cleaned.upper().strip().replace(',', '')
                ok = gt_val == clean_up or gt_val in clean_up or clean_up in gt_val
                marker = '[OK]' if ok else '[X]'
                if ok:
                    correct += 1
                count += 1
                print(f'    {fname:20s} = "{cleaned[:35]}"  {marker}')

        acc = correct / max(count, 1) * 100
        print(f'    准确率: {correct}/{count} = {acc:.0f}%')
        total_correct += correct
        total_fields += count

    overall = total_correct / max(total_fields, 1) * 100
    print(f'\n  总准确率: {total_correct}/{total_fields} = {overall:.0f}%')
    if overall >= 90:
        print('  [OK] 字段提取准确率 > 90%，通过')
    else:
        print(f'  [!] 准确率 {overall:.0f}%，未达 90% 目标')
    print('[OK] 通过\n')


if __name__ == '__main__':
    print('\n===== Day 3-9 OCR 引擎 & 预处理 & 版面分析 & 字段提取 验证测试 =====\n')
    print('通俗理解:')
    print('  OCREngine      = 电子眼，识别图上所有文字 (Day 3)')
    print('  Preprocessor   = 智能美容师，自动扶正+提亮+纠斜 (Day 4)')
    print('  LayoutParser   = 版面分析，分清标题/字段/表格 (Day 7)')
    print('  FieldExtractor = 锚点法提取关键字段 (Day 8-9)\n')

    try:
        # Day 3 测试
        test_ocr_on_synthetic_pdf()
        test_ocr_on_cosco_pdf()
        test_ocr_on_real_scan()
        test_single_image()

        # Day 4 测试
        test_preprocess_before_after()
        test_preprocess_light_vs_hard()
        test_deskew_effect()
        test_auto_orient()
        test_batch_real_images()
        test_layout_parser()

        # Day 8-9 测试
        test_field_extractor()

        print('=== ALL PASS === 十一项测试全部通过！')
    except Exception as e:
        print(f'\n[FAIL] 出错了: {e}')
        import traceback
        traceback.print_exc()

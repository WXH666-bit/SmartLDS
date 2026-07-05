"""
OCR 引擎封装
基于 PaddleOCR 实现文字检测与识别，输出带坐标的文本框
"""

from paddleocr import PaddleOCR
import numpy as np
from PIL import Image


class OCREngine:
    """封装 PaddleOCR，提供统一的识别接口"""

    def __init__(self, lang="ch", use_gpu=False):
        """
        初始化 OCR 引擎
        :param lang: 语言，'ch'=中英文混合
        :param use_gpu: 是否使用 GPU（Windows 下默认 CPU）
        """
        self.ocr = PaddleOCR(lang=lang)

    # ================================================================
    # 核心识别接口
    # ================================================================

    def recognize_image(self, image, normalize=False):
        """
        对单张图片进行 OCR 识别（检测 + 识别）

        :param image: PIL Image 或 numpy array
        :param normalize: 是否将坐标归一化到 [0, 1] 区间（除以图片宽高）
        :return: [{text, confidence, bbox, rect}, ...]
                 若 normalize=True，bbox/rect 均为归一化坐标
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        h, w = image.shape[:2]

        raw = self.ocr.ocr(image)
        if raw is None or len(raw) == 0 or raw[0] is None:
            return []

        blocks = []
        for line in raw[0]:
            bbox, (text, confidence) = line
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]

            if normalize:
                bbox_norm = [[x / w, y / h] for x, y in bbox]
                rect_norm = [min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h]
                blocks.append({
                    "text": text,
                    "confidence": round(confidence, 4),
                    "bbox": [[round(x, 6), round(y, 6)] for x, y in bbox_norm],
                    "rect": [round(v, 6) for v in rect_norm],
                })
            else:
                blocks.append({
                    "text": text,
                    "confidence": round(confidence, 4),
                    "bbox": bbox,
                    "rect": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                })

        blocks.sort(key=lambda b: (b["rect"][1], b["rect"][0]))
        return blocks

    def detect_only(self, image):
        """
        仅文字检测（不识别），返回文本框坐标。
        用于自动定向等只需数框数量的场景，比完整 OCR 快 ~10 倍。

        :param image: numpy array (灰度或彩色均可)
        :return: [rect, ...]  每个框的 [x1, y1, x2, y2]
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        raw = self.ocr.ocr(image, rec=False)
        if raw is None or len(raw) == 0 or raw[0] is None:
            return []

        boxes = []
        for bbox in raw[0]:
            if bbox is None or len(bbox) == 0:
                continue
            # rec=False 时返回 np.array 列表，每个是 (4, 2) 形状
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            boxes.append([int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))])

        boxes.sort(key=lambda r: (r[1], r[0]))
        return boxes

    def recognize_images(self, images, normalize=False):
        """
        批量识别多张图片

        :param images: PIL Image 或 numpy array 列表
        :param normalize: 是否归一化坐标
        :return: [[{...}, ...], ...]  每张图的识别结果
        """
        return [self.recognize_image(img, normalize=normalize) for img in images]

    # ================================================================
    # PDF 接口
    # ================================================================

    def recognize_pdf(self, pdf_path, normalize=False):
        """
        对 PDF 文件进行 OCR 识别（逐页）

        :param pdf_path: PDF 文件路径
        :param normalize: 是否归一化坐标
        :return: [{page, image_size, blocks}, ...]
        """
        import fitz
        results = []
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            blocks = self.recognize_image(img, normalize=normalize)
            results.append({
                "page": page_num + 1,
                "image_size": [pix.width, pix.height],
                "blocks": blocks,
            })

        doc.close()
        return results

    def detect_pdf(self, pdf_path):
        """
        对 PDF 进行仅检测（逐页）

        :return: [{page, image_size, boxes}, ...]
        """
        import fitz
        results = []
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            boxes = self.detect_only(np.array(img))
            results.append({
                "page": page_num + 1,
                "image_size": [pix.width, pix.height],
                "boxes": boxes,
                "count": len(boxes),
            })

        doc.close()
        return results


# 便捷函数
_default_engine = None


def get_engine(lang="ch", use_gpu=False):
    """获取全局 OCR 引擎单例（避免重复加载模型）"""
    global _default_engine
    if _default_engine is None:
        _default_engine = OCREngine(lang=lang, use_gpu=use_gpu)
    return _default_engine

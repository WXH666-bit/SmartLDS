"""
图像预处理模块
将 PDF/图片转为适合 OCR 的干净图像

流水线: PDF → 图片 → 灰度化 → 纠斜 → CLAHE增强 → numpy array

设计决策:
  - 不二值化: PaddleOCR 检测器在自然灰度图上效果更好，二值化会丢失梯度信息
  - 不去噪:   PaddleOCR 的 CNN 检测器自带噪声鲁棒性，额外去噪收效甚微
  - CLAHE:   局部直方图均衡化，改善光照不均和阴影。实测置信度 +5pp
  - 纠斜:    霍夫变换 + HoughLinesP 回退 + 角度一致性检验，防止热敏纸噪点误触发
  - 自动定向: 不加入默认管线（Sobel 法对稀疏文本误判率高），需要时单独调用 auto_orient()
"""

import numpy as np
from PIL import Image
import cv2


class Preprocessor:
    """图像预处理器 — 自动定向、纠斜、CLAHE增强，输出适合 OCR 的灰度图"""

    @staticmethod
    def pdf_to_images(pdf_path, dpi=200):
        """
        PDF → PIL Image 列表（每页一张图）
        :param pdf_path: PDF 文件路径
        :param dpi: 渲染分辨率，默认 200
        :return: [PIL.Image, ...]
        """
        import fitz  # pymupdf
        images = []
        doc = fitz.open(pdf_path)
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        return images

    @staticmethod
    def to_gray(image):
        """
        转灰度图
        如果输入是彩色 PIL Image / numpy array → 输出单通道灰度 numpy array
        """
        if isinstance(image, Image.Image):
            img = np.array(image.convert("L"))
        else:
            img = image
            if len(img.shape) == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    @staticmethod
    def binarize(gray_img, method="adaptive"):
        """
        二值化：把灰度图变成纯黑白（文字=黑255，背景=白）
        :param method: "otsu" 全局阈值 / "adaptive" 自适应阈值（推荐）

        注意：默认管线不再使用二值化。PaddleOCR 的检测器在自然灰度图上
        效果更好，二值化会丢失梯度信息、破坏细笔画中文字。保留此方法仅供
        调试对比或特殊用途（如版面分析的表格线检测）。
        """
        if method == "otsu":
            _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            # 自适应阈值：局部区域内动态计算阈值，适合光照不均的拍照文档
            binary = cv2.adaptiveThreshold(
                gray_img, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=11,  # 邻域大小
                C=2            # 常数偏移
            )
        return binary

    @staticmethod
    def denoise(img, method="gaussian", kernel_size=3):
        """
        去噪：抹掉图片上的麻点、噪点
        :param method: "gaussian" 高斯滤波 / "median" 中值滤波（椒盐噪声效果好）

        注意：默认管线不再使用去噪。PaddleOCR 的 CNN 检测器自带噪声鲁棒性，
        额外去噪收效甚微，可能反而模糊文字边缘。保留此方法供特殊场景使用
        （如版面分析的连通域预处理）。
        """
        if method == "median":
            return cv2.medianBlur(img, kernel_size)
        else:
            return cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)

    @staticmethod
    def deskew(gray_img):
        """
        纠斜：检测文字行倾斜角度并旋转校正
        原理：霍夫变换找出图中最长的直线 → 计算倾斜角度 → 旋转校正

        改进点:
          - Hough 阈值从 100 降到 50，对短文本行（快递面单）更敏感
          - HoughLines 检测不到线时用 HoughLinesP 回退
          - 白边填充代替边缘复制，减少 OCR 边界伪影

        :return: 校正后的图像
        """
        edges = cv2.Canny(gray_img, 50, 150, apertureSize=3)

        # 标准霍夫变换
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=80)
        angles = []

        if lines is not None:
            for line in lines:
                rho, theta = line[0]
                angle = np.rad2deg(theta)
                if 0 < angle < 45:
                    angles.append(angle)
                elif 135 < angle < 180:
                    angles.append(angle)
                elif 85 < angle < 95:
                    angles.append(angle - 90)

        # 回退：概率霍夫变换，更高阈值防止热敏纸噪点
        if not angles:
            lines_p = cv2.HoughLinesP(
                edges, 1, np.pi / 180, threshold=60,
                minLineLength=50, maxLineGap=10
            )
            if lines_p is not None:
                for line in lines_p:
                    x1, y1, x2, y2 = line[0]
                    angle = np.rad2deg(np.arctan2(y2 - y1, x2 - x1))
                    if abs(angle) < 45:
                        angles.append(angle)

        # 角度一致性检验：真正倾斜的文档，检测到的线角度高度一致；
        # 噪点产生的假线则方向散乱，IQR 会很大
        if len(angles) < 5:
            return gray_img

        arr = np.array(angles)
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        if iqr > 5.0:
            return gray_img  # 角度太散乱，是噪点不是倾斜

        if not angles:
            return gray_img

        # 取中位数作为整体倾斜角度
        median_angle = np.median(angles)
        median_angle = np.clip(median_angle, -15, 15)

        if abs(median_angle) < 0.5:
            return gray_img

        # 旋转校正（白边填充，看起来自然且不产生伪影）
        h, w = gray_img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            gray_img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255  # 白色背景
        )
        return rotated

    @staticmethod
    def enhance_contrast(gray_img):
        """
        CLAHE 对比度增强：让暗处的文字更清晰，但又不像二值化那样暴力
        适合手机拍的照片、光线不均匀的场景
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray_img)

    @staticmethod
    def _auto_orient_full(gray_img, engine=None):
        """
        三段式自动定向，覆盖 0°~360° 任意旋转角度。

        Stage 1 — 霍夫角度直方图（快，~0.1s）:
          统计 HoughLines 检测到的所有直线的角度分布，
          找主峰 → 文字行方向。主峰尖锐 + 票数够 → 直接用。

        Stage 2 — OCR 4 方向兜底（慢，~2s，仅 Stage 1 失败时触发）:
          旋转 0°/90°/180°/270°，各跑一次 OCR 检测，
          哪个方向检出文字最多就选哪个。

        Stage 3 — deskew 细调:
          由 _apply_pipeline 在之后自动执行，精调到 ±0.5°。

        :param gray_img: 灰度图 numpy array
        :param engine: OCREngine 实例（Stage 2 兜底用，可选）
        :return: (corrected_image, rotation_degrees_applied)
        """
        h, w = gray_img.shape[:2]
        center = (w // 2, h // 2)

        # ---- Stage 1: Hough 角度直方图 ----
        edges = cv2.Canny(gray_img, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=80)

        if lines is not None and len(lines) >= 10:
            # 收集所有线的角度（度），theta=90° = 水平线 = 文字行
            all_angles = []
            for line in lines:
                theta = line[0][1]
                all_angles.append(np.rad2deg(theta))

            # 直方图，2° 一个 bin，范围 [0, 180)
            hist, bins = np.histogram(all_angles, bins=90, range=(0, 180))
            peak_idx = np.argmax(hist)
            peak_angle = (bins[peak_idx] + bins[peak_idx + 1]) / 2  # 主峰角度
            peak_votes = hist[peak_idx]
            total_votes = len(all_angles)

            # 置信度 = 主峰票数占比
            confidence = peak_votes / total_votes

            # 主峰够高且票数够多 → 信任
            if confidence > 0.12 and peak_votes >= 5:
                # 文字行在 Hough 空间对应 theta≈90°，实际旋转角 = peak_angle - 90°
                rot_angle = peak_angle - 90.0

                # 正规划到 [-90°, 90°)
                if rot_angle > 90:
                    rot_angle -= 180
                elif rot_angle < -90:
                    rot_angle += 180

                # ±15° 以内：deskew 细调就够了
                if abs(rot_angle) <= 15:
                    return gray_img, 0

                # 近 ±90°：90° 旋转（手机拍照最常见的大角度错误）
                if abs(rot_angle) >= 75:
                    rot = -90 if rot_angle > 0 else 90
                    M = cv2.getRotationMatrix2D(center, rot, 1.0)
                    rotated = cv2.warpAffine(
                        gray_img, M, (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_CONSTANT,
                        borderValue=255
                    )
                    return rotated, rot

                # 其他角度（15°~75°）：直接粗调
                M = cv2.getRotationMatrix2D(center, -rot_angle, 1.0)
                rotated = cv2.warpAffine(
                    gray_img, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=255
                )
                return rotated, -rot_angle

        # ---- Stage 2: OCR 4 方向兜底 ----
        if engine is not None:
            best_count = -1
            best_img = gray_img
            best_angle = 0

            for angle in [0, 90, 180, 270]:
                if angle == 0:
                    test_img = gray_img
                else:
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    test_img = cv2.warpAffine(
                        gray_img, M, (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_CONSTANT,
                        borderValue=255
                    )

                boxes = engine.detect_only(test_img)  # 仅检测，比完整识别快 ~10x
                count = len(boxes)
                if count > best_count:
                    best_count = count
                    best_img = test_img
                    best_angle = angle

            if best_angle != 0 and best_count > 0:
                return best_img, best_angle

        return gray_img, 0

    def _apply_pipeline(self, gray_img, engine=None, mode="light"):
        """
        统一预处理管线

        处理顺序（经批量验证的最优流程）:
          1. 自动定向 — 霍夫直方图粗调 0°~360°（失败则 OCR 四方向兜底）
          2. 纠斜     — 霍夫变换细调 ±15°，精度 ±0.5°
          3. CLAHE    — 局部对比度增强，置信度 +5pp

        :param engine: OCREngine 实例，Stage 2 OCR 兜底用，可选
        """
        # Step 1: 自动定向（霍夫角度直方图 → OCR 四方向兜底）
        oriented, _rot_deg = self._auto_orient_full(gray_img, engine=engine)

        # Step 2: 细调纠斜
        aligned = self.deskew(oriented)

        # Step 3: CLAHE 对比度增强
        return self.enhance_contrast(aligned)

    def auto_orient(self, gray_img, engine=None):
        """
        公开接口：自动检测并纠正 0°~360° 任意旋转。
        先霍夫角度直方图（快），失败则用 OCR 四方向兜底（慢但可靠）。

        :param gray_img: 灰度图 numpy array
        :param engine: OCREngine 实例，OCR 兜底用
        :return: 纠正后的图像
        """
        corrected, _ = self._auto_orient_full(gray_img, engine=engine)
        return corrected

    def process_pdf(self, pdf_path, dpi=200, mode="light", engine=None):
        """
        预处理 PDF 文件

        :param pdf_path: PDF 路径
        :param dpi: 渲染分辨率
        :param mode: 保留参数，light/hard 已统一管线
        :param engine: OCREngine 实例，Stage 2 OCR 兜底用
        :return: [(PIL.Image, np.ndarray), ...] 每页的 (原图, 处理后)
        """
        pil_images = self.pdf_to_images(pdf_path, dpi=dpi)
        results = []
        for pil_img in pil_images:
            gray = self.to_gray(pil_img)
            processed = self._apply_pipeline(gray, engine=engine, mode=mode)
            results.append((pil_img, processed))
        return results

    def process_image(self, image, engine=None, mode="light"):
        """
        预处理单张图片（numpy array 或 PIL Image）

        :param image: 输入图像
        :param engine: OCREngine 实例，Stage 2 OCR 兜底用
        :param mode: 保留参数
        :return: np.ndarray 处理后的图像
        """
        gray = self.to_gray(image)
        return self._apply_pipeline(gray, engine=engine, mode=mode)

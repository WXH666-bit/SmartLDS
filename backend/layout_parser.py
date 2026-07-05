"""
版面分析模块
将 OCR 输出的散落文本块按版面结构组织为 header / body / table 三个区域

核心算法:
  1. Y 投影 → 把文本块按行分组（同行块 Y 坐标重叠）
  2. 列对齐分析 → 检测多行共享相同 X 列位 → 表格特征
  3. 区域分类 → 顶部大号字 → header，对齐网格 → table，其余 → body
"""

import numpy as np


class LayoutParser:
    """
    版面分析器：将 OCR 文本块按版面语义分类

    用法:
        parser = LayoutParser()
        regions = parser.parse(ocr_blocks, image_size)
        # → {"header": [...], "body": [...], "table": [...]}
    """

    def __init__(self, header_ratio=0.18, row_gap_ratio=1.8, col_align_threshold=30):
        """
        :param header_ratio: 页面顶部多少比例算 header 区域（默认 18%）
        :param row_gap_ratio: 行间距大于中位数多少倍时切分区块（默认 1.8x）
        :param col_align_threshold: 列对齐容差（像素），两块 X 差在此范围内视为同列
        """
        self.header_ratio = header_ratio
        self.row_gap_ratio = row_gap_ratio
        self.col_align_threshold = col_align_threshold

    # ================================================================
    # 主入口
    # ================================================================

    def parse(self, blocks, image_size):
        """
        解析 OCR 文本块，输出版面区域

        :param blocks: OCR 输出列表 [{text, confidence, bbox, rect}, ...]
                       每个块的 rect 格式 [x1, y1, x2, y2]
        :param image_size: [width, height] 原始图片尺寸
        :return: {"header": [block, ...], "body": [...], "table": [...]}
        """
        if not blocks:
            return {"header": [], "body": [], "table": []}

        img_w, img_h = image_size

        # Step 1: 按行分组
        rows = self._group_into_rows(blocks)

        # Step 2: 检测表格行（行内多块且列对齐）
        table_row_indices = self._detect_table_rows(rows)

        # Step 3: 分类
        header_blocks = []
        body_blocks = []
        table_blocks = []

        header_boundary = img_h * self.header_ratio

        for i, row in enumerate(rows):
            if i in table_row_indices:
                table_blocks.extend(row)
            elif all(b["rect"][1] < header_boundary for b in row):
                # 完全在 header 区域内的行
                header_blocks.extend(row)
            else:
                body_blocks.extend(row)

        return {
            "header": header_blocks,
            "body": body_blocks,
            "table": table_blocks,
        }

    # ================================================================
    # 行分组
    # ================================================================

    def _group_into_rows(self, blocks):
        """
        将 OCR 文本块按 Y 坐标分组为行。

        原理：同一行内的文本块 Y 范围有重叠（如标签 "Shipper:" 和值 "ABC Co."），
        不同行之间有明显间距。通过 Y 投影找行间间隙来切分。

        :return: [[block, ...], ...]  每行一组块，按 Y 从小到大排列
        """
        if len(blocks) == 1:
            return [list(blocks)]

        # 按 Y 中心排序
        sorted_blocks = sorted(blocks, key=lambda b: (b["rect"][1] + b["rect"][3]) / 2)

        # 计算相邻块之间的 Y 间距
        gaps = []
        for i in range(len(sorted_blocks) - 1):
            curr_bottom = sorted_blocks[i]["rect"][3]
            next_top = sorted_blocks[i + 1]["rect"][1]
            gap = next_top - curr_bottom
            if gap > 0:
                gaps.append(gap)

        # 没有明显间隙 → 所有块算一行
        if not gaps:
            return [list(sorted_blocks)]

        # 计算间隙阈值：大于中位数的 row_gap_ratio 倍视为行间切分点
        median_gap = float(np.median(gaps))
        avg_height = float(np.median([b["rect"][3] - b["rect"][1] for b in sorted_blocks]))
        min_row_gap = max(median_gap * self.row_gap_ratio, avg_height * 0.6)

        rows = []
        current_row = [sorted_blocks[0]]
        current_y_min = sorted_blocks[0]["rect"][1]
        current_y_max = sorted_blocks[0]["rect"][3]

        for block in sorted_blocks[1:]:
            by1, by2 = block["rect"][1], block["rect"][3]

            # 当前块与当前行有 Y 重叠 → 同行
            if by1 <= current_y_max and by2 >= current_y_min:
                current_row.append(block)
                current_y_min = min(current_y_min, by1)
                current_y_max = max(current_y_max, by2)
                continue

            # Y 间隙超过阈值 → 新行
            if by1 - current_y_max > min_row_gap:
                rows.append(current_row)
                current_row = [block]
                current_y_min = by1
                current_y_max = by2
            else:
                # 间隙小 → 仍算同行
                current_row.append(block)
                current_y_max = max(current_y_max, by2)

        rows.append(current_row)
        return rows

    # ================================================================
    # 表格检测
    # ================================================================

    def _detect_table_rows(self, rows):
        """
        检测哪些行属于表格区域。

        表格特征：一行 3+ 块，且连续多行的块在 X 方向对齐（共享列位）。

        :return: set of row indices that belong to table
        """
        if len(rows) < 2:
            return set()

        # 每行提取块数和 X 中心列表
        row_info = []
        for row in rows:
            if len(row) < 3:
                row_info.append(None)
                continue
            x_centers = sorted([(b["rect"][0] + b["rect"][2]) / 2 for b in row])
            row_info.append({"count": len(row), "x_centers": x_centers})

        # 找连续的多列表格行段
        threshold = self.col_align_threshold
        table_candidates = []

        i = 0
        while i < len(rows):
            if row_info[i] is None or row_info[i]["count"] < 3:
                i += 1
                continue

            j = i
            while j + 1 < len(rows):
                if row_info[j + 1] is None:
                    break
                overlap = self._column_overlap(
                    row_info[j]["x_centers"],
                    row_info[j + 1]["x_centers"],
                    threshold
                )
                if overlap < 2:  # 至少 2 列对齐
                    break
                j += 1

            if j > i:  # 至少连续 2 行
                table_candidates.append((i, j))

            i = j + 1

        if not table_candidates:
            return set()

        # 合并相邻候选段（间距 ≤1 行合并）
        table_candidates.sort(key=lambda x: x[0])
        merged = [table_candidates[0]]
        for start, end in table_candidates[1:]:
            prev_start, prev_end = merged[-1]
            if start - prev_end <= 1:
                merged[-1] = (prev_start, end)
            else:
                merged.append((start, end))

        # 选覆盖行数最多的段
        best = max(merged, key=lambda x: x[1] - x[0] + 1)
        return set(range(best[0], best[1] + 1))

    @staticmethod
    def _column_overlap(x_centers_a, x_centers_b, threshold):
        """计算两行之间有多少列 X 位置对齐"""
        count = 0
        for xa in x_centers_a:
            for xb in x_centers_b:
                if abs(xa - xb) < threshold:
                    count += 1
                    break
        return count

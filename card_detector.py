# -*- coding: utf-8 -*-
"""
CardDetector — nhận diện lá bài Tiến Lên bằng template matching.

Tối ưu cho resolution 1280x720 (MEMU Tablet mode):
- CARD_ROI: chỉ scan vùng bài (nửa dưới màn hình)
- Grayscale matching: nhanh hơn + robust hơn với biến đổi màu
- Parallel matching: ThreadPoolExecutor cho 52 templates đồng thời
- NMS (Non-Max Suppression): loại duplicate gần nhau

Interface:
    detector = CardDetector(template_dir: str, threshold: float = 0.82)
    detector.detect(img_bgr) -> dict[str, tuple[int, int]]
        # {card_name: (x, y)} — tâm tuyệt đối trên frame gốc.
        # card_name dạng "3_co", "10_ro", "K_bich", "A_chuon", "2_co"
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

# Vùng chứa bài trên tay (1280x720). Chỉ scan khu vực này.
# (y_min, y_max, x_min, x_max)
CARD_ROI = (480, 700, 0, 1280)

# Khoảng cách tối thiểu (pixel) giữa 2 detection cùng template
# để coi là 2 lá khác nhau (NMS).
NMS_DIST = 30


class CardDetector:
    def __init__(self, template_dir: str, threshold: float = 0.82):
        self.template_dir = Path(template_dir)
        self.threshold = threshold
        self._templates = {}  # {card_name: gray_template}
        self._pool = ThreadPoolExecutor(max_workers=8)

        if not self.template_dir.exists():
            logging.warning(
                f"Template dir khong ton tai: {self.template_dir}. "
                "Card detection se khong hoat dong."
            )
            return

        self._load_templates()

    def _load_templates(self):
        """Load tất cả template PNG, chuyển grayscale, lưu vào RAM."""
        count = 0
        for img_path in sorted(self.template_dir.glob("*.png")):
            tpl_bgr = cv2.imread(str(img_path))
            if tpl_bgr is None:
                logging.warning(f"Khong doc duoc template: {img_path.name}")
                continue
            tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
            card_name = img_path.stem  # "3_co", "K_bich", ...
            self._templates[card_name] = tpl_gray
            count += 1
        logging.info(f"CardDetector: da tai {count} templates tu {self.template_dir}")

    def _match_one(self, card_name, tpl_gray, roi_gray, threshold):
        """Match 1 template trong ROI. Trả về list[(score, cx, cy)]."""
        if roi_gray.shape[0] < tpl_gray.shape[0] or roi_gray.shape[1] < tpl_gray.shape[1]:
            return []

        result = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        h, w = tpl_gray.shape[:2]
        hits = []
        for pt_y, pt_x in zip(*locations):
            score = float(result[pt_y, pt_x])
            cx = int(pt_x + w // 2)
            cy = int(pt_y + h // 2)
            hits.append((score, cx, cy))

        return self._nms(hits)

    @staticmethod
    def _nms(hits, min_dist=NMS_DIST):
        """Non-max suppression: giữ hit score cao nhất trong bán kính min_dist."""
        if not hits:
            return []
        hits_sorted = sorted(hits, key=lambda h: -h[0])
        kept = []
        for score, cx, cy in hits_sorted:
            too_close = False
            for _, kx, ky in kept:
                if abs(cx - kx) < min_dist and abs(cy - ky) < min_dist:
                    too_close = True
                    break
            if not too_close:
                kept.append((score, cx, cy))
        return kept

    def detect(self, img_bgr) -> dict:
        """
        Nhận diện lá bài trong frame.

        Args:
            img_bgr: ảnh BGR từ ADB screencap (numpy array).

        Returns:
            dict {card_name: (abs_x, abs_y)} — tọa độ tâm tuyệt đối.
        """
        if not self._templates:
            return {}

        h_img, w_img = img_bgr.shape[:2]

        # Crop ROI
        y_min, y_max, x_min, x_max = CARD_ROI
        y_min = max(0, min(y_min, h_img))
        y_max = max(0, min(y_max, h_img))
        x_min = max(0, min(x_min, w_img))
        x_max = max(0, min(x_max, w_img))

        roi_bgr = img_bgr[y_min:y_max, x_min:x_max]
        if roi_bgr.size == 0:
            # Fallback: scan toàn frame
            roi_bgr = img_bgr
            y_min, x_min = 0, 0

        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

        # Parallel matching cho tất cả templates
        futures = {}
        for card_name, tpl_gray in self._templates.items():
            fut = self._pool.submit(
                self._match_one, card_name, tpl_gray, roi_gray, self.threshold
            )
            futures[card_name] = fut

        # Thu thập kết quả (card_name, score, abs_x, abs_y)
        all_hits = []
        for card_name, fut in futures.items():
            try:
                hits = fut.result(timeout=2.0)
            except Exception:
                continue
            if hits:
                best = max(hits, key=lambda h: h[0])
                abs_x = best[1] + x_min
                abs_y = best[2] + y_min
                all_hits.append((card_name, best[0], abs_x, abs_y))

        # Cross-template NMS: nếu 2 lá khác nhau cùng vị trí, giữ score cao nhất
        all_hits.sort(key=lambda h: -h[1])  # sort by score desc
        detected = {}
        taken_positions = []  # list of (x, y)
        for card_name, score, ax, ay in all_hits:
            too_close = False
            for tx, ty in taken_positions:
                if abs(ax - tx) < NMS_DIST and abs(ay - ty) < NMS_DIST:
                    too_close = True
                    break
            if not too_close:
                detected[card_name] = (ax, ay)
                taken_positions.append((ax, ay))

        return detected

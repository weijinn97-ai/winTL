# -*- coding: utf-8 -*-
"""
CardDetectorV2 — phiên bản cải tiến nhận diện lá bài.

Drop-in replacement cho CardDetector (cùng interface detect()).
Cải tiến so với v1:
- All-peaks detection: tìm TẤT CẢ vị trí match (không chỉ best)
- Template cropping: chỉ dùng top 30% (rank+suit) để tìm vị trí
- Per-template NMS + Cross-template NMS

Interface (giống hệt v1):
    detector = CardDetectorV2(template_dir: str, threshold: float = 0.66)
    detector.detect(img_bgr) -> dict[str, tuple[int, int]]
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

# Vùng chứa bài trên tay (1280x720) — giống v1
CARD_ROI = (480, 700, 0, 1280)

NMS_DIST = 30
CROP_TOP_PCT = 30
MAX_PT_Y_PCT = 0.40


class CardDetectorV2:
    def __init__(self, template_dir: str, threshold: float = 0.66):
        self.template_dir = Path(template_dir)
        self.threshold = threshold
        self._templates = {}       # {card_name: gray_template}
        self._templates_crop = {}  # {card_name: top-30% cropped template}
        self._pool = ThreadPoolExecutor(max_workers=8)

        if not self.template_dir.exists():
            logging.warning(
                f"Template dir khong ton tai: {self.template_dir}. "
                "Card detection se khong hoat dong."
            )
            return

        self._load_templates()

    def _load_templates(self):
        count = 0
        for img_path in sorted(self.template_dir.glob("*.png")):
            tpl_bgr = cv2.imread(str(img_path))
            if tpl_bgr is None:
                logging.warning(f"Khong doc duoc template: {img_path.name}")
                continue
            tpl_gray = cv2.cvtColor(tpl_bgr, cv2.COLOR_BGR2GRAY)
            card_name = img_path.stem
            self._templates[card_name] = tpl_gray

            crop_h = max(10, int(tpl_gray.shape[0] * CROP_TOP_PCT / 100))
            self._templates_crop[card_name] = tpl_gray[:crop_h, :]
            count += 1
        logging.info(f"CardDetectorV2: da tai {count} templates tu {self.template_dir}")

    @staticmethod
    def _find_all_peaks(tpl, roi, threshold, full_h=None, max_pt_y=None):
        """Find ALL peaks above threshold, then per-template NMS."""
        if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]:
            return []

        result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        h, w = tpl.shape[:2]
        cy_offset = (full_h // 2) if full_h is not None else (h // 2)
        hits = []
        for pt_y, pt_x in zip(*locations):
            if max_pt_y is not None and pt_y > max_pt_y:
                continue
            score = float(result[pt_y, pt_x])
            cx = int(pt_x + w // 2)
            cy = int(pt_y + cy_offset)
            hits.append((score, cx, cy))

        if not hits:
            return []

        # Per-template NMS: keep best within NMS_DIST
        hits.sort(key=lambda h: -h[0])
        kept = []
        for score, cx, cy in hits:
            too_close = False
            for _, kx, ky in kept:
                if abs(cx - kx) < NMS_DIST and abs(cy - ky) < NMS_DIST:
                    too_close = True
                    break
            if not too_close:
                kept.append((score, cx, cy))
        return kept

    @staticmethod
    def _cross_nms(all_hits):
        """Cross-template NMS: nếu 2 lá cùng vị trí, giữ score cao nhất."""
        all_hits.sort(key=lambda h: -h[1])
        detected = {}
        taken_positions = []
        for card_name, score, ax, ay in all_hits:
            if card_name in detected:
                continue
            too_close = False
            for tx, ty in taken_positions:
                if abs(ax - tx) < NMS_DIST and abs(ay - ty) < NMS_DIST:
                    too_close = True
                    break
            if not too_close:
                detected[card_name] = (ax, ay)
                taken_positions.append((ax, ay))
        return detected

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
            roi_bgr = img_bgr
            y_min, x_min = 0, 0

        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

        max_pt_y = int(roi_gray.shape[0] * MAX_PT_Y_PCT)

        # Parallel matching cho tất cả templates (tương tự v1)
        futures = {}
        for card_name, tpl_crop in self._templates_crop.items():
            tpl_full_h = self._templates[card_name].shape[0]
            fut = self._pool.submit(
                self._find_all_peaks,
                tpl_crop, roi_gray, self.threshold,
                full_h=tpl_full_h, max_pt_y=max_pt_y,
            )
            futures[card_name] = fut

        all_hits = []
        for card_name, fut in futures.items():
            try:
                peaks = fut.result(timeout=2.0)
            except Exception:
                continue
            for score, cx, cy in peaks:
                abs_x = cx + x_min
                abs_y = cy + y_min
                all_hits.append((card_name, score, abs_x, abs_y))

        detected = self._cross_nms(all_hits)
        return detected

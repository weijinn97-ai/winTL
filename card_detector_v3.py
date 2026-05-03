# -*- coding: utf-8 -*-
"""
card_detector_v3.py — Module nhận diện 13 lá bài Tiến Lên trên tay người chơi.
Accuracy: 97.4% (304/312) trên 24 screenshots benchmark.

- Multi-scale rank match + voting suit + SVM tiebreak ♠↔♣.
- Templates: canonical_templates/{rank_gallery,suit_gallery}/.
- Optional SVM classifier: cs_classifier.pkl ( ♠ vs ♣ disambiguation).

Thay thế cho card_detector.py / card_detector_v2.py khi
USE_DETECTOR_V3=1 (mặc định).


Pipeline:
  1) Multi-scale template match RANK (gallery nhiều mẫu/rank) trong dải y cố định.
  2) NMS theo x → giữ tối đa 13 vị trí lá.
  3) Với mỗi vị trí lá:
     a) Tính top_y bằng skyline analysis.
     b) Crop vùng dưới rank (y = top_y + 70..140), tạo color mask đỏ/đen.
     c) Tìm bounding box của blob suit, resize 36×36.
     d) Match mask với gallery của 2 chất cùng màu (D/H nếu đỏ, C/S nếu đen).
        Lấy MAX score → suit cuối cùng.

Templates:
  - canonical_templates/rank_gallery/{rank}_*.png  (BGR)
  - canonical_templates/suit_gallery/{suit}_*.png  (mask grayscale 36×36)

API tương thích bot:
    detector = CardDetectorV3("canonical_templates", threshold=0.55)
    result = detector.detect(img_bgr)  # -> {"3C": (x, y), "10S": (x, y), ...}
"""

from pathlib import Path
import logging
import pickle
import cv2
import numpy as np


# ------------------ Hằng số (1280×720 layout) ------------------
RANKS = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
SUITS = ['C', 'D', 'H', 'S']

HAND_X_RANGE = (150, 1100)
HAND_Y_RANGE = (450, 720)
WHITE_THRESHOLD = 200

# Rank: tìm ở dải y cố định (rank text rơi vào khoảng 540-615)
RANK_Y_RANGE = (520, 625)
RANK_W, RANK_H = 45, 65   # cho extract template (không bắt buộc khi load)

# Suit search region (relative to top_y)
SUIT_Y_OFFSET = 70
SUIT_Y_HEIGHT = 70
SUIT_X_HALFWIDTH = 22

# Suit mask normalized size
SUIT_MASK_SIZE = (36, 36)

# Multi-scale matching cho rank (lá to/nhỏ tùy ván)
RANK_SCALES = [0.85, 0.95, 1.0, 1.1, 1.25]

# NMS cho rank: 2 match cách nhau < MIN_RANK_X_GAP px coi là cùng 1 lá.
# Khoảng cách giữa 2 lá trong quạt khoảng 50-70 px.
MIN_RANK_X_GAP = 50

# Số lá tay tối đa (Tiến Lên = 13)
MAX_CARDS = 13

# Click point: nửa thân lá
CLICK_DY = 100


# ------------------ Helper functions ------------------
def _classify_color(crop_bgr) -> str:
    """Trả về 'RED' hoặc 'BLACK'."""
    if crop_bgr.size == 0:
        return 'BLACK'
    R = crop_bgr[..., 2].astype(int)
    G = crop_bgr[..., 1].astype(int)
    B = crop_bgr[..., 0].astype(int)
    red_mask = (R > 100) & (R - G > 40) & (R - B > 40)
    black_mask = (R < 80) & (G < 80) & (B < 80)
    return 'RED' if int(red_mask.sum()) > int(black_mask.sum()) else 'BLACK'


def _extract_suit_mask(img_bgr, x_center: int, top_y: int):
    """Cắt vùng suit, tạo mask đỏ/đen, lấy bounding box, resize 36×36.
    Trả về (mask_36x36, color) hoặc (None, None) nếu không tìm thấy."""
    H, W = img_bgr.shape[:2]
    sy0 = top_y + SUIT_Y_OFFSET
    sy1 = min(H, sy0 + SUIT_Y_HEIGHT)
    sx0 = max(0, x_center - SUIT_X_HALFWIDTH)
    sx1 = min(W, x_center + SUIT_X_HALFWIDTH)
    crop = img_bgr[sy0:sy1, sx0:sx1]
    if crop.size == 0:
        return None, None
    R = crop[..., 2].astype(int)
    G = crop[..., 1].astype(int)
    B = crop[..., 0].astype(int)
    red_mask = (R > 100) & (R - G > 40) & (R - B > 40)
    black_mask = (R < 80) & (G < 80) & (B < 80)
    n_red = int(red_mask.sum())
    n_black = int(black_mask.sum())
    if max(n_red, n_black) < 30:
        return None, None
    if n_red > n_black:
        mask = red_mask
        color = 'RED'
    else:
        mask = black_mask
        color = 'BLACK'
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None, None
    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])
    pad = 2
    y0 = max(0, y0 - pad); y1 = min(crop.shape[0] - 1, y1 + pad)
    x0 = max(0, x0 - pad); x1 = min(crop.shape[1] - 1, x1 + pad)
    sm = (mask[y0:y1 + 1, x0:x1 + 1].astype(np.uint8) * 255)
    sm_norm = cv2.resize(sm, SUIT_MASK_SIZE, interpolation=cv2.INTER_AREA)
    return sm_norm, color


# ------------------ CardDetectorV3 ------------------
class CardDetectorV3:
    def __init__(self,
                 template_dir: str,
                 threshold: float = 0.55,
                 suit_threshold: float = 0.30):
        self.template_dir = Path(template_dir)
        self.rank_threshold = float(threshold)
        self.suit_threshold = float(suit_threshold)

        self.rank_gallery = self._load_rank_gallery()
        self.suit_gallery = self._load_suit_gallery()

        # Optional: SVM classifier để tiebreak ♣ vs ♠ (chỉ dùng nếu file có)
        self.cs_classifier = None
        cs_path = self.template_dir.parent / 'cs_classifier.pkl'
        if not cs_path.exists():
            cs_path = Path('cs_classifier.pkl')
        if cs_path.exists():
            try:
                with open(cs_path, 'rb') as f:
                    self.cs_classifier = pickle.load(f)
                logging.info(f"Loaded CS classifier từ {cs_path}")
            except Exception as e:
                logging.warning(f"Không load được {cs_path}: {e}")

        if not self.rank_gallery:
            logging.error(f"Không có rank template nào trong {self.template_dir}")
        if not self.suit_gallery:
            logging.error(f"Không có suit mask nào trong {self.template_dir}")

    # ------------------------------------------------------------
    def _load_rank_gallery(self):
        """Load nhiều template/rank từ folder rank_gallery (hoặc fallback flat).
        Trả về dict[rank] -> list[gray template]."""
        out = {r: [] for r in RANKS}
        gallery_dir = self.template_dir / 'rank_gallery'
        flat_dir = self.template_dir
        # Try gallery first
        if gallery_dir.exists():
            for p in gallery_dir.glob('*.png'):
                # Filename format: {rank}_*.png  (rank may be "10")
                stem = p.stem
                if stem.startswith('10_'):
                    rank = '10'
                else:
                    rank = stem.split('_')[0]
                if rank not in RANKS:
                    continue
                img = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                out[rank].append(gray)
        # Fallback: single rank_X.png in template_dir
        for r in RANKS:
            p = flat_dir / f"rank_{r}.png"
            if p.exists() and not out[r]:
                img = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if img is not None:
                    out[r].append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        return out

    def _load_suit_gallery(self):
        """Load nhiều mask/suit từ folder suit_gallery."""
        out = {s: [] for s in SUITS}
        gallery_dir = self.template_dir / 'suit_gallery'
        if gallery_dir.exists():
            for p in gallery_dir.glob('*.png'):
                suit = p.stem.split('_')[0]
                if suit not in SUITS:
                    continue
                m = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                if m is None:
                    continue
                if m.shape != SUIT_MASK_SIZE[::-1]:
                    m = cv2.resize(m, SUIT_MASK_SIZE, interpolation=cv2.INTER_AREA)
                out[suit].append(m)
        return out

    # ------------------------------------------------------------
    def _find_card_top_y(self, gray, x: int):
        y0, y1 = HAND_Y_RANGE
        if x < 0 or x >= gray.shape[1]:
            return None
        col = gray[y0:y1, x]
        ys = np.where(col > WHITE_THRESHOLD)[0]
        if len(ys) == 0:
            return None
        return int(ys[0]) + y0

    # ------------------------------------------------------------
    def _multi_scale_match_all(self, target, template, threshold, scales=RANK_SCALES):
        """Trả về list (x, y, w, h, score) match >= threshold."""
        out = []
        for sc in scales:
            t = cv2.resize(template, None, fx=sc, fy=sc) if sc != 1.0 else template
            th, tw = t.shape[:2]
            if target.shape[0] < th or target.shape[1] < tw:
                continue
            res = cv2.matchTemplate(target, t, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res >= threshold)
            for y, x in zip(ys, xs):
                out.append((int(x), int(y), tw, th, float(res[y, x])))
        return out

    # ------------------------------------------------------------
    def _classify_rank_at(self, gray, x_center: int, y_top: int, half_w: int = 35):
        """Try mọi rank template trong cửa sổ hẹp quanh x_center, lấy MAX score."""
        H, W = gray.shape
        x0 = max(0, x_center - half_w)
        x1 = min(W, x_center + half_w)
        y0 = max(0, y_top)
        y1 = min(H, y_top + 70)
        target = gray[y0:y1, x0:x1]
        if target.size == 0:
            return None, 0.0
        best_label, best_score = None, -2.0
        for rank, tmpl_list in self.rank_gallery.items():
            for tmpl in tmpl_list:
                for sc in RANK_SCALES:
                    t = cv2.resize(tmpl, None, fx=sc, fy=sc) if sc != 1.0 else tmpl
                    if target.shape[0] < t.shape[0] or target.shape[1] < t.shape[1]:
                        continue
                    res = cv2.matchTemplate(target, t, cv2.TM_CCOEFF_NORMED)
                    s = float(res.max())
                    if s > best_score:
                        best_score = s
                        best_label = rank
        return best_label, best_score

    # ------------------------------------------------------------
    def _detect_rank_positions(self, img_bgr):
        """Tìm tối đa MAX_CARDS vị trí lá. 2 stage:
        1) Multi-scale match toàn bộ rank gallery → ứng viên.
        2) NMS theo x lấy 13 anchor.
        3) Re-classify rank tại mỗi anchor (cửa sổ hẹp)."""
        x0_g, x1_g = HAND_X_RANGE
        y0_g, y1_g = RANK_Y_RANGE
        gray_full = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        band = gray_full[y0_g:y1_g, x0_g:x1_g]

        candidates = []  # (x_abs, y_abs, w, h, score, label)
        for rank, tmpl_list in self.rank_gallery.items():
            for tmpl in tmpl_list:
                matches = self._multi_scale_match_all(band, tmpl, self.rank_threshold)
                for (x, y, w, h, s) in matches:
                    candidates.append((x + x0_g, y + y0_g, w, h, s, rank))

        # NMS theo x (chỉ dùng để tìm ANCHOR, label sẽ re-classify sau)
        candidates.sort(key=lambda c: -c[4])
        kept = []
        for c in candidates:
            x, y, w, h, s, lbl = c
            x_center = x + w // 2
            collision = False
            for kc in kept:
                kx_center = kc[0] + kc[2] // 2
                if abs(x_center - kx_center) < MIN_RANK_X_GAP:
                    collision = True
                    break
            if not collision:
                kept.append(c)
            if len(kept) >= MAX_CARDS:
                break

        # Re-classify rank tại từng anchor — slide x-offset để snap về card center thực
        refined = []
        for (x, y, w, h, s, lbl) in kept:
            x_center = x + w // 2
            best_label, best_score, best_x = lbl, s, x_center
            best_top = None
            for dx in (-10, -5, 0, 5, 10):
                xc_try = x_center + dx
                sky_top = self._find_card_top_y(gray_full, xc_try)
                y_try = sky_top if sky_top is not None else y
                new_label, new_score = self._classify_rank_at(gray_full, xc_try, y_try)
                if new_label is not None and new_score > best_score:
                    best_score = new_score
                    best_label = new_label
                    best_x = xc_try
                    best_top = y_try
            if best_top is None:
                best_top = self._find_card_top_y(gray_full, best_x) or y
            refined.append((best_x - w // 2, best_top, w, h, best_score, best_label))
        return sorted(refined, key=lambda c: c[0])

    # ------------------------------------------------------------
    def _classify_suit_single(self, img_bgr, x_center: int, top_y: int):
        """Single-position suit match. Trả về (label, score, color)."""
        target_mask, color = _extract_suit_mask(img_bgr, x_center, top_y)
        if target_mask is None:
            return None, 0.0, None
        if color == 'RED':
            cands = ['D', 'H']
        else:
            cands = ['C', 'S']
        best_label, best_score = None, -2.0
        for suit in cands:
            for tmpl_mask in self.suit_gallery.get(suit, []):
                res = cv2.matchTemplate(target_mask, tmpl_mask, cv2.TM_CCOEFF_NORMED)
                score = float(res.max())
                if score > best_score:
                    best_score = score
                    best_label = suit
        return best_label, best_score, color

    def _classify_suit(self, img_bgr, x_center: int, top_y: int):
        """Voting suit classifier — robust với sub-pixel positioning.
        Thử ±3 offset x, ±2 offset y → cộng score per suit, pick max.
        Sau đó dùng CS classifier (SVM) để tiebreak ♣ vs ♠ nếu có."""
        from collections import Counter
        sums = Counter()
        best_color = None
        # Cũng lưu lại các mask BLACK để vote bằng SVM nếu cần
        black_masks = []
        for dx in (-3, -1, 0, 1, 3):
            for dy in (-2, 0, 2):
                lbl, sc, col = self._classify_suit_single(img_bgr, x_center + dx, top_y + dy)
                if lbl is not None:
                    sums[lbl] += sc
                    best_color = col
                    if col == 'BLACK':
                        m, _ = _extract_suit_mask(img_bgr, x_center + dx, top_y + dy)
                        if m is not None:
                            black_masks.append(m)
        if not sums:
            return None, 0.0
        suit, total_score = sums.most_common(1)[0]
        n_votes = 15  # 5 dx × 3 dy

        # CS classifier override (chỉ áp dụng cho BLACK)
        if (self.cs_classifier is not None and best_color == 'BLACK'
                and suit in ('C', 'S') and len(black_masks) > 0):
            # Predict probability per mask, average → soft vote
            probs = []  # P(class=C)
            for m in black_masks:
                feat = (m > 100).astype(np.float32).flatten().reshape(1, -1)
                if hasattr(self.cs_classifier, 'predict_proba'):
                    p_c = float(self.cs_classifier.predict_proba(feat)[0, 1])
                else:
                    p = int(self.cs_classifier.predict(feat)[0])
                    p_c = 1.0 if p == 1 else 0.0
                probs.append(p_c)
            mean_pc = float(np.mean(probs))
            # Override only when SVM is highly confident
            if mean_pc >= 0.75:
                suit = 'C'
            elif mean_pc <= 0.25:
                suit = 'S'

        return suit, total_score / n_votes

    # ------------------------------------------------------------
    def detect(self, img_bgr) -> dict:
        """Trả về dict {card_name: (click_x, click_y)} cho mỗi lá tìm được."""
        if img_bgr is None or not self.rank_gallery:
            return {}
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        H, W = gray.shape

        rank_hits = self._detect_rank_positions(img_bgr)

        results = {}
        for (x, y, w, h, score, rank_label) in rank_hits:
            x_center = x + w // 2
            top_y = self._find_card_top_y(gray, x_center)
            if top_y is None:
                top_y = y - 5

            suit_label, suit_score = self._classify_suit(img_bgr, x_center, top_y)
            if suit_label is None or suit_score < self.suit_threshold:
                continue

            card_name = f"{rank_label}{suit_label}"
            click_y = min(H - 1, top_y + CLICK_DY)
            if card_name not in results:
                results[card_name] = (x_center, click_y)
        return results

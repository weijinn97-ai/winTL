# -*- coding: utf-8 -*-
"""
debug_detect.py — chẩn đoán tại sao bot KHÔNG nhận được nút / lá bài.

Chạy độc lập, KHÔNG tap. Capture 1 frame từ MEMU, in chi tiết:
- Score template matching cho 5 nút (danh_giua, danh_phai, bo_luot_trai,
  bo_luot_giua, tiep_tuc) ở các threshold 0.50 / 0.65 / 0.70 / 0.85.
- Crop vùng BUTTON_ROI (400-850, 370-470) lưu thành ảnh để xem trực quan.
- Chạy CardDetector → liệt kê lá phát hiện được.
- Vẽ annotation (box quanh nút match, chấm tâm lá) → debug_annotated.png.

Usage:
    .venv\\Scripts\\python debug_detect.py            # picker chọn device
    .venv\\Scripts\\python debug_detect.py 127.0.0.1:23523   # chỉ định serial
"""
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

ADB_PATH = os.getenv("ADB_PATH", "adb")
MEMU_IP = os.getenv("MEMU_IP", "")
BUTTON_ROI = (350, 920, 370, 470)  # khớp bottlll.py
BUTTON_ROI_VAN_SAU = (560, 950, 580, 710)  # khớp bottlll.py
BUTTON_NAMES = ["danh_giua", "danh_phai", "bo_luot_trai", "bo_luot_giua", "tiep_tuc", "van_sau"]
THRESHOLDS = [0.50, 0.65, 0.70, 0.85]


def run_adb(args, timeout=5):
    flags = 0x08000000 if sys.platform == "win32" else 0
    r = subprocess.run([ADB_PATH] + args, capture_output=True,
                       timeout=timeout, creationflags=flags)
    return r.stdout, r.stderr, r.returncode


def list_devices():
    out, _, _ = run_adb(["devices"])
    devs = []
    for line in out.decode("utf-8", errors="replace").splitlines()[1:]:
        if line.strip() and "device" in line.split():
            devs.append(line.split()[0])
    return devs


def pick_device():
    if len(sys.argv) > 1:
        return sys.argv[1]
    devs = list_devices()
    if not devs:
        sys.exit("❌ Không có ADB device nào.")
    if len(devs) == 1:
        return devs[0]
    print("Chọn device:")
    for i, d in enumerate(devs, 1):
        marker = " <-- MEMU_IP" if MEMU_IP and MEMU_IP in d else ""
        print(f"  [{i}] {d}{marker}")
    default = 1
    for i, d in enumerate(devs, 1):
        if MEMU_IP and MEMU_IP in d:
            default = i
            break
    raw = input(f"[1-{len(devs)}, Enter = {default}]: ").strip()
    try:
        n = int(raw) if raw else default
        return devs[n - 1]
    except (ValueError, IndexError):
        return devs[default - 1]


def capture(serial):
    out, err, rc = run_adb(["-s", serial, "exec-out", "screencap", "-p"], timeout=10)
    if rc != 0 or not out:
        sys.exit(f"❌ Capture fail: {err.decode(errors='replace')}")
    arr = np.frombuffer(out, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit("❌ Decode PNG fail.")
    return img


def match_button(img, template, roi=BUTTON_ROI):
    x1, x2, y1, y2 = roi
    region = img[y1:y2, x1:x2]
    if region.size == 0 or region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        # ROI quá nhỏ hoặc template lớn hơn ROI → match toàn frame
        region = img
        ox, oy = 0, 0
    else:
        ox, oy = x1, y1
    res = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    h, w = template.shape[:2]
    cx = max_loc[0] + w // 2 + ox
    cy = max_loc[1] + h // 2 + oy
    top_left = (max_loc[0] + ox, max_loc[1] + oy)
    bot_right = (top_left[0] + w, top_left[1] + h)
    return max_val, (cx, cy), top_left, bot_right


def main():
    serial = pick_device()
    print(f"📱 Device: {serial}")

    img = capture(serial)
    h, w = img.shape[:2]
    print(f"🖼  Frame: {w}x{h}")
    cv2.imwrite(str(BASE / "debug_capture.png"), img)
    print(f"💾 Lưu: debug_capture.png")

    # Crop ROI để xem trực quan
    x1, x2, y1, y2 = BUTTON_ROI
    if y2 <= h and x2 <= w:
        roi_img = img[y1:y2, x1:x2].copy()
        cv2.imwrite(str(BASE / "debug_button_roi.png"), roi_img)
        print(f"💾 Lưu: debug_button_roi.png ({x2-x1}x{y2-y1}, vùng {BUTTON_ROI})")
    else:
        print(f"⚠️ BUTTON_ROI {BUTTON_ROI} ngoài frame {w}x{h}")

    annotated = img.copy()

    # ===== BUTTON MATCHING =====
    btn_dir = BASE / "button_templates"
    print("\n=========== BUTTON MATCHING ===========")
    print(f"{'name':<16} {'tpl_size':<12} {'best_score':<12} {'pos':<14} {'>=0.50':<8} {'>=0.65':<8} {'>=0.70':<8} {'>=0.85':<8}")
    for name in BUTTON_NAMES:
        p = btn_dir / f"{name}.png"
        if not p.exists():
            print(f"{name:<16} MISSING")
            continue
        tpl = cv2.imread(str(p))
        if tpl is None:
            print(f"{name:<16} READ_FAIL")
            continue
        roi = BUTTON_ROI_VAN_SAU if name == "van_sau" else BUTTON_ROI
        score, center, tl, br = match_button(img, tpl, roi=roi)
        passes = [f"{'✓' if score >= t else '✗':<8}" for t in THRESHOLDS]
        print(f"{name:<16} {tpl.shape[1]}x{tpl.shape[0]:<8} {score:<12.4f} {str(center):<14} " + " ".join(passes))
        # Annotate top match (any score)
        color = (0, 255, 0) if score >= 0.65 else (0, 0, 255)
        cv2.rectangle(annotated, tl, br, color, 2)
        cv2.putText(annotated, f"{name} {score:.2f}", (tl[0], tl[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # Vẽ ROI
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 255, 0), 1)
    cv2.putText(annotated, "BUTTON_ROI", (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    # ===== CARD DETECTION =====
    print("\n=========== CARD DETECTION ===========")
    try:
        from card_detector import CardDetector
        det = CardDetector(str(BASE / "cards_output"), threshold=0.82)
        cards = det.detect(img)
        print(f"Detected {len(cards)} lá ở threshold 0.82:")
        for name, pos in sorted(cards.items()):
            print(f"  {name:<10} {pos}")
            cv2.circle(annotated, pos, 8, (0, 255, 255), 2)
            cv2.putText(annotated, name, (pos[0] + 10, pos[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        if not cards:
            print("⚠️ Không phát hiện lá nào → thử threshold thấp hơn:")
            for t in [0.80, 0.75, 0.70]:
                det2 = CardDetector(str(BASE / "cards_output"), threshold=t)
                cards2 = det2.detect(img)
                print(f"  threshold {t}: {len(cards2)} lá")
                if cards2:
                    print(f"    {list(cards2.keys())[:10]}")
                    break
    except Exception as e:
        print(f"❌ CardDetector fail: {e}")

    cv2.imwrite(str(BASE / "debug_annotated.png"), annotated)
    print(f"\n💾 Lưu: debug_annotated.png  (mở để xem box quanh nút + chấm vàng quanh lá)")

    print("\n✅ Xong. Gửi 3 file cho debug:")
    print("   - debug_capture.png")
    print("   - debug_button_roi.png")
    print("   - debug_annotated.png")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
capture_buttons.py — Chụp lại template nút từ game hiện tại.

Hướng dẫn:
1. Mở game Tiến Lên trên MEMU, vào ván chơi
2. ĐỢI cho đến khi MÀN HÌNH HIỆN ĐỦ NÚT cần chụp:
   - Để chụp "Bỏ Lượt" + "Đánh": chờ đến lượt mình, đối thủ vừa đánh
   - Để chụp "Tiếp Tục": chờ hết ván (màn hình kết quả)
3. Chạy script: .venv\Scripts\python capture_buttons.py
4. Script sẽ chụp màn hình và hỏi bạn vị trí từng nút
5. Template mới lưu vào button_templates/

Usage:
    .venv/Scripts/python capture_buttons.py
    .venv/Scripts/python capture_buttons.py 127.0.0.1:23523
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
BTN_DIR = BASE / "button_templates"

# Vị trí ước tính các nút trên màn 1280x720
# Format: (x_center, y_center, width, height)
# Dựa trên screenshot thực tế từ game
BUTTON_REGIONS = {
    "bo_luot_giua": {
        "desc": "Nút BỎ LƯỢT ở GIỮA (khi chỉ có 1 nút Bỏ Lượt)",
        "crop": (540, 375, 740, 445),  # x1,y1,x2,y2
    },
    "bo_luot_trai": {
        "desc": "Nút BỎ LƯỢT ở TRÁI (khi có cả Đánh bên phải)",
        "crop": (370, 375, 570, 445),
    },
    "danh_giua": {
        "desc": "Nút ĐÁNH ở GIỮA (khi chỉ có 1 nút Đánh)",
        "crop": (540, 375, 740, 445),
    },
    "danh_phai": {
        "desc": "Nút ĐÁNH ở PHẢI (khi có cả Bỏ Lượt bên trái)",
        "crop": (710, 375, 910, 445),
    },
    "tiep_tuc": {
        "desc": "Nút TIẾP TỤC (màn hình kết quả ván)",
        "crop": (540, 375, 740, 445),
    },
    "van_sau": {
        "desc": "Nút VÁN SAU (màn Tổng Kết Ván)",
        "crop": (715, 605, 925, 690),
    },
}


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
        sys.exit("Khong co ADB device nao.")
    if len(devs) == 1:
        return devs[0]
    for i, d in enumerate(devs, 1):
        print(f"  [{i}] {d}")
    raw = input(f"Chon [1-{len(devs)}]: ").strip()
    try:
        return devs[int(raw) - 1]
    except (ValueError, IndexError):
        return devs[0]


def capture(serial):
    out, err, rc = run_adb(["-s", serial, "exec-out", "screencap", "-p"], timeout=10)
    if rc != 0 or not out:
        sys.exit(f"Capture fail: {err.decode(errors='replace')}")
    arr = np.frombuffer(out, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit("Decode PNG fail.")
    return img


def main():
    serial = pick_device()
    print(f"Device: {serial}")
    print()

    BTN_DIR.mkdir(exist_ok=True)

    while True:
        print("=" * 60)
        print("HUONG DAN: Mo game, cho den khi man hinh hien nut can chup.")
        print("Cac nut co the chup:")
        for i, (name, info) in enumerate(BUTTON_REGIONS.items(), 1):
            existing = (BTN_DIR / f"{name}.png").exists()
            status = " [DA CO]" if existing else ""
            print(f"  [{i}] {name}: {info['desc']}{status}")
        print(f"  [0] Thoat")
        print()

        raw = input(f"Chon nut can chup (1-{len(BUTTON_REGIONS)}, hoac 0 de thoat): ").strip()
        if raw == "0":
            break

        try:
            idx = int(raw) - 1
            btn_name = list(BUTTON_REGIONS.keys())[idx]
        except (ValueError, IndexError):
            print("Lua chon khong hop le!")
            continue

        info = BUTTON_REGIONS[btn_name]
        print(f"\nDang chup: {btn_name} - {info['desc']}")
        print("Dam bao nut dang hien tren man hinh game!")
        input("Nhan Enter khi san sang...")

        print("Dang capture...")
        img = capture(serial)
        h_img, w_img = img.shape[:2]
        print(f"Frame: {w_img}x{h_img}")

        # Lưu full capture để tham khảo
        cv2.imwrite(str(BASE / "capture_for_template.png"), img)

        x1, y1, x2, y2 = info["crop"]
        x1 = max(0, min(x1, w_img))
        x2 = max(0, min(x2, w_img))
        y1 = max(0, min(y1, h_img))
        y2 = max(0, min(y2, h_img))

        crop = img[y1:y2, x1:x2].copy()
        if crop.size == 0:
            print(f"LOI: Crop rong ({x1},{y1})-({x2},{y2})")
            continue

        preview_path = BASE / f"preview_{btn_name}.png"
        cv2.imwrite(str(preview_path), crop)
        print(f"\nDa luu preview: {preview_path}")
        print(f"Kich thuoc: {crop.shape[1]}x{crop.shape[0]}")
        print(f"Vung crop: ({x1},{y1})-({x2},{y2})")
        print()

        # Mở preview để user xem
        if sys.platform == "win32":
            os.system(f'start "" "{preview_path}"')

        confirm = input("Anh nay dung la nut can chup? (y/n): ").strip().lower()
        if confirm == "y":
            out_path = BTN_DIR / f"{btn_name}.png"
            cv2.imwrite(str(out_path), crop)
            print(f"DA LUU: {out_path}")
            print()
        else:
            print("Bo qua. Thu chup lai voi man hinh khac.\n")
            # Cho phép user nhập tọa độ thủ công
            manual = input("Nhap toa do thu cong? (y/n): ").strip().lower()
            if manual == "y":
                try:
                    coords = input("Nhap x1,y1,x2,y2 (vd: 400,380,600,440): ").strip()
                    parts = [int(p.strip()) for p in coords.split(",")]
                    x1, y1, x2, y2 = parts
                    crop2 = img[y1:y2, x1:x2].copy()
                    cv2.imwrite(str(preview_path), crop2)
                    print(f"Preview moi: {preview_path} ({crop2.shape[1]}x{crop2.shape[0]})")
                    if sys.platform == "win32":
                        os.system(f'start "" "{preview_path}"')
                    ok = input("Dung chua? (y/n): ").strip().lower()
                    if ok == "y":
                        out_path = BTN_DIR / f"{btn_name}.png"
                        cv2.imwrite(str(out_path), crop2)
                        print(f"DA LUU: {out_path}\n")
                except Exception as e:
                    print(f"Loi: {e}\n")

    print("\nXong! Chay debug_detect.py de kiem tra score cac template moi.")
    print("Lenh: .venv\\Scripts\\python debug_detect.py")


if __name__ == "__main__":
    main()

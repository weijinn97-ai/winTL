# -*- coding: utf-8 -*-
"""
Smoke test cho bot Tiến Lên.

Chạy 1 lần sau khi setup để xác nhận môi trường OK.
KHÔNG tap màn hình. Chỉ đọc config + kiểm tra ADB + chụp 1 frame
+ thử nhận diện nút trong frame đó.

Usage:
    python test_smoke.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")  # nạp ADB_PATH/MEMU_IP trước khi đọc os.getenv ở module-level
RESULTS = []  # list of (status, name, detail)


def step(name, fn):
    try:
        detail = fn() or ""
        RESULTS.append(("OK", name, detail))
        line = f"  [OK]   {name}"
        if detail:
            line += f"  →  {detail}"
        print(line)
        return True
    except AssertionError as e:
        RESULTS.append(("FAIL", name, str(e)))
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        RESULTS.append(("FAIL", name, f"{type(e).__name__}: {e}"))
        print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
        return False


# -------------------- 1. Imports --------------------
def check_imports():
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import dotenv  # noqa: F401
    try:
        import keyboard  # noqa: F401
        return "keyboard OK"
    except ImportError:
        return "keyboard MISSING (hotkey sẽ không chạy, bot vẫn chạy)"


# -------------------- 2. .env --------------------
def check_env():
    env = BASE / ".env"
    assert env.exists(), f".env không tồn tại tại {env}. Copy .env.example -> .env."
    from dotenv import load_dotenv
    load_dotenv(env)
    adb = os.getenv("ADB_PATH", "")
    assert adb, "ADB_PATH trống trong .env"
    return f"ADB_PATH={adb}"


# -------------------- 3. bot_config.json --------------------
def check_config():
    cfg_path = BASE / "bot_config.json"
    assert cfg_path.exists(), f"{cfg_path} không tồn tại. Copy bot_config.json.example -> bot_config.json."
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    btns = cfg.get("buttons", {})
    required = ["danh_phai", "danh_giua", "bo_luot_trai", "bo_luot_giua", "tiep_tuc", "van_sau"]
    for key in required:
        assert key in btns, f"Thiếu button '{key}'"
        assert len(btns[key]) == 2, f"Button '{key}' phải là [x, y]"
    return f"{len(required)} buttons OK"


# -------------------- 4. Templates --------------------
def check_cards_dir():
    # V3 dùng canonical_templates/ (commit sẵn). V1/V2 dùng cards_output/ (user tự đặt).
    canonical = BASE / "canonical_templates"
    legacy = BASE / "cards_output"
    if canonical.exists():
        rank = list((canonical / "rank_gallery").glob("*.png"))
        suit = list((canonical / "suit_gallery").glob("*.png"))
        assert rank and suit, "canonical_templates/ thiếu rank_gallery hoặc suit_gallery"
        return f"V3: {len(rank)} rank + {len(suit)} suit templates"
    assert legacy.exists(), "Không tìm thấy canonical_templates/ hoặc cards_output/"
    pngs = list(legacy.glob("*.png"))
    assert pngs, f"{legacy} không có file .png nào"
    detail = f"V1/V2: {len(pngs)} file .png"
    if len(pngs) < 52:
        detail += " (kỳ vọng 52)"
    return detail


def check_button_templates():
    d = BASE / "button_templates"
    assert d.exists(), f"{d} không tồn tại"
    required = ["danh_giua", "danh_phai", "bo_luot_trai", "bo_luot_giua", "tiep_tuc", "van_sau"]
    missing = [n for n in required if not (d / f"{n}.png").exists()]
    assert not missing, f"Thiếu: {missing}"
    return f"{len(required)} template OK"


# -------------------- 5. ADB --------------------
ADB = os.getenv("ADB_PATH", "adb")
DEVICE = {"serial": None}


def check_adb_binary():
    out = subprocess.run([ADB, "version"], capture_output=True, timeout=5, text=True)
    assert out.returncode == 0, f"adb version fail: {out.stderr.strip()[:200]}"
    return out.stdout.splitlines()[0] if out.stdout else "OK"


def check_adb_devices():
    memu_ip = os.getenv("MEMU_IP", "")
    if memu_ip:
        subprocess.run([ADB, "connect", memu_ip], capture_output=True, timeout=5)
    out = subprocess.run([ADB, "devices"], capture_output=True, timeout=5, text=True)
    devs = [
        line.split("\t")[0]
        for line in out.stdout.splitlines()
        if "\tdevice" in line and not line.startswith("List of")
    ]
    assert devs, "Không thấy thiết bị nào ở trạng thái 'device'. Bật MEMU + USB debug, hoặc 'adb connect <ip:port>'."
    DEVICE["serial"] = devs[0]
    return f"{len(devs)} device(s), dùng: {devs[0]}"


# -------------------- 6. Capture --------------------
def check_capture():
    serial = DEVICE["serial"]
    assert serial, "Skip: chưa có device"
    out_path = BASE / "smoke_capture.png"
    out = subprocess.run(
        [ADB, "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=8,
    )
    assert out.returncode == 0 and len(out.stdout) > 1000, f"screencap fail: {out.stderr[:200]!r}"
    out_path.write_bytes(out.stdout)
    import cv2
    img = cv2.imread(str(out_path))
    assert img is not None, "cv2 không decode được capture (file hỏng?)"
    h, w = img.shape[:2]
    return f"{w}x{h}, lưu {out_path.name}"


# -------------------- 7. Button detection --------------------
def check_button_match():
    cap = BASE / "smoke_capture.png"
    assert cap.exists(), "smoke_capture.png chưa có"
    import cv2
    img = cv2.imread(str(cap))
    btn_dir = BASE / "button_templates"
    found = {}
    for name in ["danh_giua", "danh_phai", "bo_luot_trai", "bo_luot_giua", "tiep_tuc", "van_sau"]:
        tp = btn_dir / f"{name}.png"
        if not tp.exists():
            continue
        tpl = cv2.imread(str(tp))
        if tpl is None:
            continue
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, mloc = cv2.minMaxLoc(res)
        if mx >= 0.65:
            h, w = tpl.shape[:2]
            found[name] = (mloc[0] + w // 2, mloc[1] + h // 2, round(float(mx), 2))
    if not found:
        return "không thấy nút nào (có thể đang ở màn hình khác — bình thường)"
    return f"{len(found)} button: {found}"


# -------------------- Run --------------------
def main():
    print("=" * 60)
    print("SMOKE TEST — BOT TIẾN LÊN MIỀN NAM")
    print("=" * 60)

    step("Imports (cv2, numpy, dotenv, keyboard)", check_imports)
    step(".env tồn tại + ADB_PATH có giá trị", check_env)
    step("bot_config.json hợp lệ + đủ 6 button", check_config)
    step("cards_output/ có file .png", check_cards_dir)
    step("button_templates/ có 6 file bắt buộc", check_button_templates)
    step(f"ADB binary chạy được ('{ADB}')", check_adb_binary)
    step("ADB devices: ít nhất 1 thiết bị connected", check_adb_devices)
    step("Capture 1 frame -> smoke_capture.png", check_capture)
    step("Button matching trên smoke_capture.png", check_button_match)

    print()
    print("=" * 60)
    fail = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"PASS: {len(RESULTS) - len(fail)} / {len(RESULTS)}")
    if fail:
        print(f"FAIL: {len(fail)}")
        for _, name, detail in fail:
            print(f"  - {name}: {detail}")
        return 1
    print("Tất cả OK. Chạy bot: python bottlll.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

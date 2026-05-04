# -*- coding: utf-8 -*-
"""
BOT TIẾN LÊN MIỀN NAM - V65 (TỐI ƯU ĐÔI THÔNG, PARALLEL DETECTION, GIẢM CAPTURE THỪA)
"""

import os
import sys
import asyncio
import logging
import traceback
import re
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import csv
import time
from dotenv import load_dotenv
import threading
import json
import atexit
import subprocess
import tempfile
import shutil

from card_detector import CardDetector
from card_detector_v2 import CardDetectorV2
from screen_stream import ScreenStream

try:
    import keyboard
    HOTKEY_ENABLED = True
except ImportError:
    HOTKEY_ENABLED = False
    print("⚠️ Thư viện 'keyboard' chưa cài. Phím tắt sẽ không hoạt động.")

# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# ------------------------------------------------------------------
# ENV & CONSTANTS
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ADB_PATH = os.getenv('ADB_PATH', 'adb')
MEMU_IP = os.getenv('MEMU_IP', '')
TEMPLATE_DIR = BASE_DIR / 'cards_output'
BUTTON_TEMPLATE_DIR = BASE_DIR / 'button_templates'

RANK_ORDER_STRAIGHT = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUE_FULL = {r: i for i, r in enumerate(['3','4','5','6','7','8','9','10','J','Q','K','A','2'])}

BASE_SCAN_INTERVAL       = 0.05
BASE_POST_ACTION_DELAY   = 0.05
BASE_SELECT_GAP_STRAIGHT = 0.02
BASE_SELECT_GAP_NORMAL   = 0.01
BASE_CLICK_CHECK_DELAY   = 0.05

# Sàn delay tối thiểu — KHÔNG cho phép speed cao hạ dưới giá trị này
MIN_SCAN_INTERVAL        = 0.15
MIN_POST_ACTION_DELAY    = 0.05

# Khoảng cách tối thiểu giữa 2 lệnh ADB bất kỳ (s)
ADB_MIN_INTERVAL         = 0.10

# Tốc độ tối đa cho phép (để tránh ADB quá tải)
MAX_SPEED                = 300

SPEED_MAP = {
    '2': 160, '3': 210, '4': 300, '5': 400, '6': 440, '7': 490, '8': 520
}

FAST_CARD_POS = (640, 530)
FAST_DANH_POS = (602, 427)
FAST_TIEP_TUC_POS = (773, 649)
TURN_WAIT_TIME = 4.5
BUTTON_ROI = (350, 920, 370, 470)
# ROI rieng cho nut man hinh ket thuc van (Van Sau) — nam o nua duoi
BUTTON_ROI_VAN_SAU = (560, 950, 580, 710)

# Thời gian chờ tối đa cho mỗi lượt đánh (tránh treo)
TURN_TIMEOUT = 10.0

# ------------------------------------------------------------------
# THOÁT AN TOÀN - KILL ADB SERVER
# ------------------------------------------------------------------
def cleanup_adb():
    try:
        adb_path = ADB_PATH or "adb"
        subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=2)
        print("Đã kill ADB server.")
    except Exception as e:
        print(f"Lỗi khi kill ADB: {e}")

atexit.register(cleanup_adb)

# ------------------------------------------------------------------
# TiLenBot
# ------------------------------------------------------------------
class TiLenBot:
    def __init__(self):
        self.auto_playing = False
        self.paused = False
        self.allow_adb = False
        self.battle_task = None
        self.adb_sem = asyncio.Semaphore(1)
        # Chọn detector: True = v2 (multi-scale, adaptive), False = v1 (gốc)
        USE_DETECTOR_V2 = os.getenv('USE_DETECTOR_V2', '1') == '1'
        if USE_DETECTOR_V2:
            self.detector = CardDetectorV2(str(TEMPLATE_DIR), threshold=0.66)
            logging.info("Dùng CardDetectorV2 (crop30 + all-peaks detection)")
        else:
            self.detector = CardDetector(str(TEMPLATE_DIR), threshold=0.82)
            logging.info("Dùng CardDetector v1 (gốc)")
        self.last_opponent_cards = []
        self.last_my_cards = []
        self.failed_attempts = 0

        self.phase = "idle"
        self.init_attempts = 0
        self.init_success = False

        self.current_speed = 100
        self.update_speed_params()

        self.log_file = BASE_DIR / "speed_log.csv"
        self._init_log_file()

        self.reset_delay = 0.01
        self.select_retry_delay = 0.01
        self.tap_delay = 0.005
        self.click_check_delay = 0.02
        self.no_button_timeout = 10
        self.last_action_time = time.time()

        self.button_templates = self.load_button_templates()
        self.fallback_buttons = {}

        self.load_config()
        
        self.selected_device = None
        self.screen_stream = None
        self._auto_connect_adb()
        # Khởi động scrcpy stream (nếu có)
        if self.selected_device:
            self.screen_stream = ScreenStream(self.selected_device)
            self.screen_stream.start()

        self.show_status_menu()

        self.fast_click_mode = False
        self._in_fast_mode = False

        # Thêm biến đếm lỗi capture liên tiếp
        self.consecutive_capture_failures = 0
        # Throttle log lỗi "ADB không kết nối" (tránh spam)
        self._last_disconnect_log = 0.0
        # Throttle thử reconnect (không gọi `adb connect` quá thường xuyên)
        self._last_reconnect_attempt = 0.0
        # Thời điểm lệnh ADB gần nhất — rate limiter chống spam
        self._last_adb_call = 0.0
        # Đếm số lần click Tiếp Tục liên tiếp khi không thấy bài
        self._tiep_tuc_streak = 0

    # -------------------- ADB TỰ ĐỘNG KẾT NỐI --------------------
    def _run_adb_command(self, args, timeout=5):
        """Chạy lệnh ADB đồng bộ, có xử lý timeout và kill process."""
        cmd = [ADB_PATH] + args
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout.decode('utf-8', errors='replace').strip()
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.communicate()
            logging.error(f"Lệnh ADB timeout sau {timeout}s: {args}")
            return ""
        except Exception as e:
            logging.error(f"Lỗi ADB command: {e}")
            if proc:
                proc.kill()
            return ""

    def list_adb_devices(self):
        output = self._run_adb_command(["devices"])
        lines = output.splitlines()
        devices = []
        for line in lines:
            if '\tdevice' in line:
                serial = line.split('\t')[0].strip()
                if serial and serial != "List of devices attached":
                    devices.append(serial)
        return devices

    def _find_memuc(self):
        """Tìm MEmuc.exe trong các vị trí phổ biến, trả None nếu không có."""
        candidates = []
        if ADB_PATH:
            candidates.append(Path(ADB_PATH).parent / "MEmuc.exe")
        candidates.extend([
            Path("C:/Microvirt/MEmu/MEmuc.exe"),
            Path("C:/Program Files/Microvirt/MEmu/MEmuc.exe"),
            Path("C:/Program Files (x86)/Microvirt/MEmu/MEmuc.exe"),
        ])
        for p in candidates:
            try:
                if p.exists():
                    return str(p)
            except OSError:
                continue
        return None

    def _get_memu_names(self):
        """Map ADB serial (vd '127.0.0.1:23503') -> tên VM MEMU.

        Parse output `MEmuc.exe listvms` (format: index,name,top_handle,handle,pid).
        VM đang chạy khi pid != 0. ADB port mặc định = 21503 + index*10.
        Trả {} nếu MEmuc.exe không có hoặc parse fail.
        """
        memuc = self._find_memuc()
        if not memuc:
            return {}
        mapping = {}
        flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            r = subprocess.run([memuc, "listvms"],
                               capture_output=True, timeout=5, creationflags=flags)
            out = r.stdout.decode('utf-8', errors='replace')
        except Exception as e:
            logging.debug(f"MEmuc listvms thất bại: {e}")
            return {}
        for line in out.splitlines():
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            try:
                idx = int(parts[0])
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid == 0:
                continue
            vm_name = ",".join(parts[1:-3])
            serial = f"127.0.0.1:{21503 + idx * 10}"
            mapping[serial] = vm_name
        return mapping

    def connect_adb_tcpip(self, ip_port):
        output = self._run_adb_command(["connect", ip_port])
        logging.info(f"Kết nối TCP/IP {ip_port}: {output}")
        return "connected" in output.lower()

    def _auto_connect_adb(self):
        print("\n" + "="*60)
        print("🔌 ĐANG KIỂM TRA KẾT NỐI ADB...")
        devices = self.list_adb_devices()
        print(f"📱 Danh sách thiết bị ADB đang kết nối: {devices if devices else 'KHÔNG CÓ'}")
        if MEMU_IP:
            print(f"🌐 Đang thử kết nối đến thiết bị qua IP: {MEMU_IP}")
            if self.connect_adb_tcpip(MEMU_IP):
                devices = self.list_adb_devices()
                print(f"✅ Đã kết nối thành công đến {MEMU_IP}")
            else:
                print(f"⚠️ Không thể kết nối đến {MEMU_IP}")
        devices = self.list_adb_devices()
        if not devices:
            logging.error("❌ KHÔNG TÌM THẤY THIẾT BỊ ADB NÀO.")
            self.selected_device = None
            self.allow_adb = False
        elif len(devices) == 1:
            self.selected_device = devices[0]
            print(f"✅ Chọn thiết bị: {self.selected_device}")
            self.allow_adb = True
        else:
            print(f"🔍 Có {len(devices)} thiết bị ADB:")
            memu_map = self._get_memu_names()
            device_info = []
            for dev in devices:
                name = memu_map.get(dev)
                if not name:
                    name = self._run_adb_command(["-s", dev, "shell", "getprop", "ro.product.model"]).strip() or "?"
                device_info.append((dev, name))
            default_idx = 1
            for i, (dev, _) in enumerate(device_info, 1):
                if MEMU_IP and MEMU_IP in dev:
                    default_idx = i
                    break
            for i, (dev, model) in enumerate(device_info, 1):
                marker = "  <-- MEMU_IP" if MEMU_IP and MEMU_IP in dev else ""
                star = " *" if i == default_idx else "  "
                print(f" {star}[{i}] {dev:<25} {model}{marker}")
            choice = default_idx
            if sys.stdin.isatty():
                try:
                    raw = input(f"Chọn thiết bị [1-{len(devices)}, Enter = {default_idx}]: ").strip()
                    if raw:
                        n = int(raw)
                        if 1 <= n <= len(devices):
                            choice = n
                        else:
                            print(f"⚠️ Số ngoài phạm vi, dùng mặc định {default_idx}")
                except (ValueError, EOFError):
                    print(f"⚠️ Nhập không hợp lệ, dùng mặc định {default_idx}")
            self.selected_device = device_info[choice - 1][0]
            print(f"✅ Chọn thiết bị: {self.selected_device} ({device_info[choice - 1][1]})")
            self.allow_adb = True
        if self.selected_device:
            test_output = self._run_adb_command(["-s", self.selected_device, "shell", "echo", "ok"])
            if "ok" in test_output:
                print(f"✅ Kết nối ADB đến {self.selected_device} thành công.")
                logging.info(f"ADB device ready: {self.selected_device}")
            else:
                print(f"⚠️ Kết nối ADB đến {self.selected_device} thất bại.")
                self.allow_adb = False
                self.selected_device = None
        print("="*60 + "\n")

    # -------------------- TEMPLATE NÚT --------------------
    def load_button_templates(self):
        templates = {}
        if not BUTTON_TEMPLATE_DIR.exists():
            return templates
        for button_name in ["danh_giua", "danh_phai", "bo_luot_trai", "bo_luot_giua", "tiep_tuc", "van_sau"]:
            template_path = BUTTON_TEMPLATE_DIR / f"{button_name}.png"
            if template_path.exists():
                template = cv2.imread(str(template_path))
                if template is not None:
                    templates[button_name] = template
                    logging.info(f"Đã tải template cho nút {button_name}")
        return templates

    async def find_button_position(self, img, button_name, threshold=0.7):
        if button_name not in self.button_templates:
            return None
        template = self.button_templates[button_name]
        roi_box = BUTTON_ROI_VAN_SAU if button_name == "van_sau" else BUTTON_ROI
        x1, x2, y1, y2 = roi_box
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            roi = img
            offset_x, offset_y = 0, 0
        else:
            offset_x, offset_y = x1, y1
        result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= threshold:
            h, w = template.shape[:2]
            x = max_loc[0] + w // 2 + offset_x
            y = max_loc[1] + h // 2 + offset_y
            return (x, y)
        return None

    async def find_button_score(self, img, button_name):
        """Trả về (max_score, position) cho button_name, không filter threshold."""
        if button_name not in self.button_templates:
            return 0.0, None
        template = self.button_templates[button_name]
        roi_box = BUTTON_ROI_VAN_SAU if button_name == "van_sau" else BUTTON_ROI
        x1, x2, y1, y2 = roi_box
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            roi = img
            offset_x, offset_y = 0, 0
        else:
            offset_x, offset_y = x1, y1
        result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        h, w = template.shape[:2]
        x = max_loc[0] + w // 2 + offset_x
        y = max_loc[1] + h // 2 + offset_y
        return float(max_val), (x, y)

    async def click_button(self, button_name, fallback_pos=None, img=None, max_attempts=1):
        if fallback_pos:
            await self.tap_screen(*fallback_pos, delay=50)  # tăng delay lên 50ms
            logging.info(f"✅ Click nút {button_name} tại fallback {fallback_pos}")
            return True
        if img is None:
            img = await self.capture_screen()
            if img is None:
                return False
        pos = await self.find_button_position(img, button_name, threshold=0.7)
        if pos:
            await self.tap_screen(*pos, delay=50)
            return True
        return False

    async def detect_buttons_state(self, img):
        danh = False
        bo_luot = False
        danh_scores = {}
        bo_scores = {}
        for btn in ["danh_phai", "danh_giua"]:
            score, pos = await self.find_button_score(img, btn)
            danh_scores[btn] = score
            if score >= 0.65:
                danh = True
        for btn in ["bo_luot_trai", "bo_luot_giua"]:
            score, pos = await self.find_button_score(img, btn)
            bo_scores[btn] = score
            if score >= 0.50:
                bo_luot = True
        # Log scores mỗi 20 lần (để debug khi cần)
        if not hasattr(self, '_btn_log_count'):
            self._btn_log_count = 0
        self._btn_log_count += 1
        if self._btn_log_count % 20 == 1:
            logging.debug(
                f"BTN scores: danh={danh_scores} bo={bo_scores} "
                f"-> danh={danh} bo={bo_luot}"
            )
        return danh, bo_luot

    # -------------------- XỬ LÝ BÀI --------------------
    def get_rank(self, card_name):
        if not card_name:
            return None
        s = str(card_name).upper().strip().replace('_', '').replace('-', '').replace(' ', '')
        if "VANSAU" in s or "TIEPTUC" in s or "DANH" in s or "BOLUOT" in s:
            return None
        m = re.search(r'(10|[3-9]|J|Q|K|A|2)', s)
        if m:
            return m.group(1)
        return None

    def get_rank_value(self, card_name):
        rank = self.get_rank(card_name)
        return RANK_VALUE_FULL.get(rank, -1) if rank else -1

    def get_rank_value_straight(self, card_name):
        rank = self.get_rank(card_name)
        if rank is None or rank == '2':
            return -1
        return RANK_ORDER_STRAIGHT.index(rank)

    def group_cards_by_rank(self, card_names):
        groups = {}
        for name in card_names:
            rank = self.get_rank(name)
            if rank:
                groups.setdefault(rank, []).append(name)
        return groups

    def find_pair_sequences(self, groups):
        """Tìm tất cả đôi thông (consecutive pairs) >= 3 đôi.
        Trả list of (cards_list, num_pairs). Không dùng lá 2."""
        pair_ranks = [(rank, names[:2]) for rank, names in groups.items()
                      if len(names) >= 2 and rank != '2']
        pair_ranks.sort(key=lambda x: RANK_VALUE_FULL.get(x[0], 99))
        sequences = []
        temp = []
        last_val = None
        for rank, cards in pair_ranks:
            val = RANK_VALUE_FULL.get(rank, -1)
            if last_val is None or val == last_val + 1:
                temp.append((rank, cards))
            else:
                if len(temp) >= 3:
                    sequences.append(temp[:])
                temp = [(rank, cards)]
            last_val = val
        if len(temp) >= 3:
            sequences.append(temp)
        return sequences

    def find_best_hand(self, card_names):
        groups = self.group_cards_by_rank(card_names)
        # Sảnh
        rank_list = [(rank, names[0]) for rank, names in groups.items() if rank != '2']
        rank_list.sort(key=lambda x: RANK_VALUE_FULL.get(x[0], 99))
        straights = []
        temp = []
        last_val = None
        for rank, card in rank_list:
            val = RANK_VALUE_FULL.get(rank, -1)
            if last_val is None or val == last_val + 1:
                temp.append(card)
            else:
                if len(temp) >= 3:
                    straights.append(temp.copy())
                temp = [card]
            last_val = val
        if len(temp) >= 3:
            straights.append(temp)
        if straights:
            straights.sort(key=lambda s: (-len(s), self.get_rank_value_straight(s[0])))
            return straights[0], "straight"
        # Đôi thông (3+ đôi liên tiếp) — chặt được con 2 / đôi 2
        pair_seqs = self.find_pair_sequences(groups)
        if pair_seqs:
            # Ưu tiên dài nhất, cùng dài thì nhỏ nhất
            pair_seqs.sort(key=lambda seq: (-len(seq), RANK_VALUE_FULL.get(seq[0][0], 99)))
            best_seq = pair_seqs[0]
            cards_flat = []
            for _, cards in best_seq:
                cards_flat.extend(cards)
            return cards_flat, "pair_sequence"
        # Tứ quý
        quads = [(rank, names) for rank, names in groups.items() if len(names) == 4]
        if quads:
            quads.sort(key=lambda x: RANK_VALUE_FULL.get(x[0], 99))
            return quads[0][1], "quads"
        # Ba cây
        trips = [(rank, names) for rank, names in groups.items() if len(names) == 3]
        if trips:
            trips.sort(key=lambda x: RANK_VALUE_FULL.get(x[0], 99))
            return trips[0][1], "trips"
        # Đôi
        pairs = [(rank, names) for rank, names in groups.items() if len(names) == 2]
        if pairs:
            pairs.sort(key=lambda x: RANK_VALUE_FULL.get(x[0], 99))
            return pairs[0][1], "pair"
        # Lẻ
        if card_names:
            single = min(card_names, key=lambda c: self.get_rank_value(c))
            return [single], "single"
        return [], "none"

    # -------------------- CẤU HÌNH --------------------
    def load_config(self):
        config_path = BASE_DIR / "bot_config.json"
        example_path = BASE_DIR / "bot_config.json.example"
        if not config_path.exists():
            if example_path.exists():
                shutil.copyfile(example_path, config_path)
                logging.info(
                    f"Tự tạo {config_path.name} từ {example_path.name} (lần chạy đầu)."
                )
            else:
                logging.error(f"Không tìm thấy file cấu hình: {config_path}")
                print(f"\n[LỖI] Không tìm thấy file bot_config.json tại: {config_path}")
                print(f"       Cũng không thấy {example_path.name} để tạo mặc định.")
                if sys.stdin.isatty():
                    input("Nhấn Enter để thoát...")
                sys.exit(1)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            logging.error(f"Lỗi đọc JSON: {e}")
            print(f"\n[LỖI] Đọc file bot_config.json thất bại: {e}")
            if sys.stdin.isatty():
                input("Nhấn Enter để thoát...")
            sys.exit(1)
        self.positions = cfg.get("player_positions", [])
        btns = cfg.get("buttons", {})
        self.fallback_buttons = {
            "danh_phai": tuple(btns.get("danh_phai", [787, 424])),
            "danh_giua": tuple(btns.get("danh_giua", [602, 427])),
            "bo_luot_trai": tuple(btns.get("bo_luot_trai", [453, 434])),
            "bo_luot_giua": tuple(btns.get("bo_luot_giua", [640, 410])),
            "tiep_tuc": tuple(btns.get("tiep_tuc", [773, 649])),
            "van_sau": tuple(btns.get("van_sau", [819, 647])),
        }
        self.RESET_POS = tuple(btns.get("reset_pos", [200, 400]))
        self.SAFE_CLICK_POS = tuple(btns.get("safe_click", [500, 500]))
        logging.info("Đã tải cấu hình từ bot_config.json")

    def _init_log_file(self):
        if not self.log_file.exists():
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'speed_percent', 'scan_interval', 'action_delay',
                                 'turn_duration', 'success', 'hit_attempts', 'notes'])

    def write_log(self, turn_duration, success, hit_attempts, notes=""):
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    self.current_speed,
                    f"{self.scan_interval:.2f}",
                    f"{self.post_action_delay:.2f}",
                    f"{turn_duration:.2f}",
                    str(success),
                    hit_attempts,
                    notes
                ])
        except Exception as e:
            logging.error(f"Ghi log thất bại: {e}")

    def update_speed_params(self):
        factor = 100.0 / self.current_speed
        self.scan_interval = max(BASE_SCAN_INTERVAL * factor, MIN_SCAN_INTERVAL)
        self.post_action_delay = max(BASE_POST_ACTION_DELAY * factor, MIN_POST_ACTION_DELAY)
        self.select_gap_straight = BASE_SELECT_GAP_STRAIGHT * factor
        self.select_gap_normal = BASE_SELECT_GAP_NORMAL * factor
        self.click_check_delay = BASE_CLICK_CHECK_DELAY * factor

    def set_speed(self, speed):
        limit = 520 if (self.screen_stream and self.screen_stream.is_active) else MAX_SPEED
        if speed > limit:
            logging.warning(f"⚠️ Giới hạn tốc độ {limit}% (yêu cầu {speed}%)")
            speed = limit
        self.current_speed = speed
        self.update_speed_params()
        logging.info(f"⚡ Tốc độ: {speed}%")
        self.update_status_display()

    def request_custom_speed(self):
        print("\n" + "="*20)
        try:
            val = input("Nhập tốc độ bot (%): ")
            if val.isdigit():
                self.set_speed(int(val))
        except Exception:
            print("Lỗi: Vui lòng nhập số nguyên.")
        print("="*20)

    def show_current_speed(self):
        logging.info(f"📊 Tốc độ hiện tại: {self.current_speed}%")
        self.update_status_display()

    def set_auto_play(self, enabled: bool):
        self.auto_playing = enabled
        self.allow_adb = True if enabled and self.selected_device else False
        if not enabled:
            self.phase = "idle"
            self.init_attempts = 0
            self.init_success = False
        logging.info(f"🔘 Bot đã {'BẬT' if enabled else 'TẮT'}")
        self.update_status_display()

    def toggle_pause(self):
        self.paused = not self.paused
        logging.info(f"⏸️ Bot {'TẠM DỪNG' if self.paused else 'TIẾP TỤC'}")
        self.update_status_display()

    def show_status_menu(self):
        device_status = f"📱 Thiết bị: {self.selected_device if self.selected_device else 'Chưa kết nối'}"
        print("\n" + "="*70)
        print("            BOT TIẾN LÊN MIỀN NAM - MENU ĐIỀU KHIỂN")
        print("="*70)
        print(device_status)
        print("⚡ TỐC ĐỘ:")
        scrcpy_on = self.screen_stream and self.screen_stream.is_active
        if scrcpy_on:
            print("   Ctrl+2 → 160%   Ctrl+3 → 210%   Ctrl+4 → 300%")
            print("   Ctrl+5 → 400%   Ctrl+6 → 440%   Ctrl+7 → 490%   Ctrl+8 → 520%")
        else:
            print("   Ctrl+2 → 160%   Ctrl+3 → 210%   Ctrl+4 → 300% (max)")
        print("   Ctrl+9 → Nhập tốc độ tùy chỉnh   Ctrl+0 → Xem tốc độ hiện tại")
        print("\n🎮 ĐIỀU KHIỂN:")
        print("   Ctrl+J → BẬT bot tự động")
        print("   Ctrl+K → TẮT bot")
        print("   Ctrl+L → Tạm dừng / Tiếp tục")
        print("\n📊 TRẠNG THÁI HIỆN TẠI:")
        print(f"   Bot tự động: {'🟢 BẬT' if self.auto_playing else '🔴 TẮT'}")
        print(f"   Tạm dừng: {'⏸️ CÓ' if self.paused else '▶️ KHÔNG'}")
        print(f"   Tốc độ: {self.current_speed}% (delay quét: {self.scan_interval:.2f}s)")
        capture_mode = "📹 scrcpy stream" if scrcpy_on else "📷 ADB screencap"
        print(f"   Capture: {capture_mode}")
        print(f"   Phase: {self.phase}")
        print("="*70 + "\n")

    def update_status_display(self):
        self.show_status_menu()

    # -------------------- ADB & CAPTURE (SỬA LỖI TỐI ĐA) --------------------
    async def _adb_alive(self):
        """Kiểm tra device còn alive bằng `adb shell echo test`."""
        try:
            proc = await asyncio.create_subprocess_exec(
                ADB_PATH, "-s", self.selected_device, "shell", "echo", "test",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            return b"test" in stdout
        except Exception:
            return False

    async def ensure_adb_connected(self):
        """Kiểm tra ADB; nếu drop thì thử `adb connect` 1 lần (cooldown 5s)."""
        if not self.allow_adb or not self.selected_device:
            return False
        if await self._adb_alive():
            return True
        now = time.time()
        if now - self._last_reconnect_attempt < 5.0:
            return False
        self._last_reconnect_attempt = now
        logging.warning(f"🔄 ADB drop, thử reconnect {self.selected_device}")
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                ADB_PATH, "connect", self.selected_device,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            await asyncio.wait_for(proc.communicate(), timeout=3.0)
        except asyncio.TimeoutError:
            if proc:
                proc.kill()
                try:
                    await proc.communicate()
                except Exception:
                    pass
            logging.error(f"adb connect timeout {self.selected_device}")
            return False
        except Exception as e:
            if proc:
                proc.kill()
            logging.error(f"adb connect lỗi: {e}")
            return False
        return await self._adb_alive()

    async def run_adb(self, args, timeout=4.0):
        if not self.allow_adb or not self.selected_device:
            return None
        # Rate limiter: đảm bảo khoảng cách tối thiểu giữa các lệnh ADB
        now = time.time()
        elapsed = now - self._last_adb_call
        if elapsed < ADB_MIN_INTERVAL:
            await asyncio.sleep(ADB_MIN_INTERVAL - elapsed)
        async with self.adb_sem:
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    ADB_PATH, "-s", self.selected_device, *args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    creationflags=0x08000000 if sys.platform == "win32" else 0
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                self._last_adb_call = time.time()
                return stdout
            except asyncio.TimeoutError:
                if proc:
                    proc.kill()
                    await proc.communicate()
                logging.error(f"Lệnh ADB timeout sau {timeout}s: {args}")
                return None
            except Exception as e:
                if proc:
                    proc.kill()
                logging.error(f"Lỗi ADB: {e}")
                return None

    async def tap_screen(self, x, y, delay=50):
        """Tăng delay mặc định lên 50ms để đảm bảo chạm ổn định"""
        await self.run_adb(["shell", "input", "swipe", str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(int(delay))])

    def _is_black_screen(self, img, threshold=10):
        """Kiểm tra ảnh có bị đen (mean pixel < threshold)."""
        if img is None:
            return True
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        return float(gray.mean()) < threshold

    async def capture_screen(self):
        """
        Chụp màn hình. Ưu tiên scrcpy stream (nhanh, không tải ADB).
        Fallback: exec-out raw → screencap -p.
        """
        # Scrcpy stream: đọc frame từ H264 stream, không cần gọi ADB
        if self.screen_stream and self.screen_stream.is_active:
            frame = self.screen_stream.get_frame()
            if frame is not None:
                self.consecutive_capture_failures = 0
                return frame

        if not await self.ensure_adb_connected():
            now = time.time()
            if now - self._last_disconnect_log >= 1.0:
                logging.error("capture_screen: ADB không kết nối")
                self._last_disconnect_log = now
            return None

        # Phương pháp 1: File tạm (tránh xung đột)
        local_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                local_path = tmp.name
            remote_path = "/sdcard/temp_cap.png"
            # Chụp lên device
            ret = await self.run_adb(["shell", "screencap", remote_path], timeout=3.0)
            if ret is not None:
                # Pull về local
                pull_proc = await asyncio.create_subprocess_exec(
                    ADB_PATH, "-s", self.selected_device, "pull", remote_path, local_path,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await pull_proc.communicate()
                if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
                    img = cv2.imread(local_path)
                    if img is not None:
                        logging.debug("✅ capture via file thành công")
                        return img
                # Xóa file trên device
                await self.run_adb(["shell", "rm", remote_path], timeout=2.0)
        except Exception as e:
            logging.warning(f"Capture via file lỗi: {e}")
        finally:
            try:
                if local_path and os.path.exists(local_path):
                    os.unlink(local_path)
            except Exception:
                pass

        # Phương pháp 2: exec-out screencap (raw)
        try:
            stdout = await self.run_adb(["exec-out", "screencap"], timeout=3.0)
            if stdout and len(stdout) > 12:
                # Loại bỏ ký tự \r nếu có (do Windows)
                if sys.platform == "win32":
                    stdout = stdout.replace(b'\r', b'')
                width = int.from_bytes(stdout[0:4], byteorder='little')
                height = int.from_bytes(stdout[4:8], byteorder='little')
                expected_size = width * height * 4
                if len(stdout) >= expected_size + 12:
                    pixels = stdout[12:12+expected_size]
                    img = np.frombuffer(pixels, dtype=np.uint8).reshape((height, width, 4))
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                    logging.debug("✅ exec-out capture thành công")
                    return img_bgr
                else:
                    logging.warning(f"exec-out: dữ liệu không đủ ({len(stdout)} < {expected_size+12})")
        except Exception as e:
            logging.warning(f"exec-out lỗi: {e}")

        # Phương pháp 3: screencap -p
        try:
            def _cap_p():
                cmd = [ADB_PATH, '-s', self.selected_device, 'shell', 'screencap', '-p']
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    data, _ = proc.communicate(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    return None
                if not data or len(data) < 100:
                    return None
                nparr = np.frombuffer(data, np.uint8)
                return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img = await asyncio.to_thread(_cap_p)
            if img is not None:
                logging.debug("✅ screencap -p thành công")
                return img
        except Exception as e:
            logging.error(f"screencap -p lỗi: {e}")

        # Nếu tất cả thất bại
        self.consecutive_capture_failures += 1
        if self.consecutive_capture_failures >= 5:
            logging.critical("❌ Capture thất bại 5 lần liên tiếp. Có thể ADB server bị lỗi. Thử restart...")
            await self.run_adb(["kill-server"], timeout=2)
            await asyncio.sleep(1)
            self.consecutive_capture_failures = 0
        logging.error("capture_screen: Tất cả phương pháp thất bại")
        return None

    async def capture_screen_safe(self):
        """capture_screen + kiểm tra ảnh đen. Trả None nếu đen.
        Tự động giảm tốc khi ảnh đen liên tục (dấu hiệu quá tải).
        """
        img = await self.capture_screen()
        if img is not None and self._is_black_screen(img):
            if not hasattr(self, '_black_screen_count'):
                self._black_screen_count = 0
            self._black_screen_count += 1
            if self._black_screen_count % 5 == 1:
                logging.warning(
                    f"⚫ Ảnh đen (lần {self._black_screen_count}) — "
                    "MEMU có thể đang loading hoặc ADB screencap lỗi"
                )
            # Backoff động: ảnh đen liên tục = quá tải ADB
            if self._black_screen_count >= 3:
                backoff = min(self._black_screen_count * 0.5, 3.0)
                logging.warning(f"⚫ Backoff {backoff:.1f}s do ảnh đen liên tục")
                await asyncio.sleep(backoff)
            return None
        if img is None:
            # Capture thất bại hoàn toàn — cũng backoff
            if hasattr(self, '_capture_fail_count'):
                self._capture_fail_count += 1
            else:
                self._capture_fail_count = 0
            if self._capture_fail_count >= 3:
                backoff = min(self._capture_fail_count * 0.5, 3.0)
                await asyncio.sleep(backoff)
            return None
        # Ảnh OK — reset counters
        if hasattr(self, '_black_screen_count') and self._black_screen_count > 0:
            logging.info(f"✅ Ảnh bình thường trở lại (sau {self._black_screen_count} lần đen)")
            self._black_screen_count = 0
        if hasattr(self, '_capture_fail_count'):
            self._capture_fail_count = 0
        return img

    async def get_detected_cards(self, img):
        raw = await asyncio.to_thread(self.detector.detect, img)
        logging.debug(f"Detector tìm thấy {len(raw)} đối tượng")
        return raw

    # -------------------- CHẾ ĐỘ SIÊU TỐC --------------------
    async def fast_single_mode(self, card_count):
        if self._in_fast_mode:
            return
        self._in_fast_mode = True
        try:
            logging.info(f"⚡ FAST MODE: {card_count} lá, chờ {TURN_WAIT_TIME}s mỗi lượt")
            for i in range(card_count + 2):
                await self.tap_screen(*FAST_CARD_POS, delay=50)
                await asyncio.sleep(0.01)
                await self.tap_screen(*FAST_DANH_POS, delay=50)
                await asyncio.sleep(TURN_WAIT_TIME)
            await asyncio.sleep(0.2)
            await self.tap_screen(*FAST_TIEP_TUC_POS, delay=50)
            logging.info("✅ Kết thúc fast mode")
        finally:
            self._in_fast_mode = False

    # -------------------- HÀM ĐÁNH BÀI (SỬA LOGIC SẢNH) --------------------
    async def play_hand(self, chosen_cards, move_type, current_my_cards, cached_hand=None):
        try:
            if cached_hand is not None:
                hand_raw = cached_hand
            else:
                fresh_img = await self.capture_screen_safe()
                if fresh_img is None:
                    return False, current_my_cards
                hand_raw = await self.get_detected_cards(fresh_img)

            cards_to_select = chosen_cards.copy()
            if move_type == "pair_sequence":
                # Đôi thông: tap từng lá (không shortcut đầu+cuối)
                if not all(c in hand_raw for c in cards_to_select):
                    logging.warning("Đôi thông: thiếu lá trong hand_raw, hủy")
                    return False, current_my_cards
                logging.info(f"🔧 Đánh đôi thông ({len(cards_to_select)//2} đôi): {cards_to_select}")
            elif move_type == "straight" and len(cards_to_select) >= 3:
                cards_sorted = sorted(cards_to_select, key=lambda c: self.get_rank_value_straight(c))
                if any(self.get_rank(c) == '2' for c in cards_sorted):
                    return False, current_my_cards
                head_tail = [cards_sorted[0], cards_sorted[-1]]
                if all(c in hand_raw for c in head_tail):
                    cards_to_select = head_tail
                    logging.info(f"🔧 Đánh sảnh -> tap 2 lá đầu+cuối: {cards_to_select}")
                elif all(c in hand_raw for c in cards_sorted):
                    cards_to_select = cards_sorted
                    logging.info(f"🔧 Đánh sảnh -> tap từng lá: {cards_to_select}")
                else:
                    logging.warning("Sảnh: thiếu lá trong hand_raw, hủy")
                    return False, current_my_cards

            # Tap RESET_POS để bỏ chọn các lá đã chọn trước (tránh accumulate selection)
            await self.tap_screen(*self.RESET_POS, delay=50)
            await asyncio.sleep(0.05)

            for idx, c in enumerate(cards_to_select):
                if c not in hand_raw:
                    return False, current_my_cards
                await self.tap_screen(*hand_raw[c], delay=50)
                if idx < len(cards_to_select) - 1:
                    await asyncio.sleep(0.05)

            await asyncio.sleep(0.05)
            danh_pos = self.fallback_buttons.get("danh_giua", (602, 427))
            await self.tap_screen(*danh_pos, delay=50)
            logging.info(f"✅ Click nút Đánh tại {danh_pos}")

            # Đợi animation hoàn tất rồi capture lại để biết bài thực sự còn lại
            await asyncio.sleep(0.3)
            after_img = await self.capture_screen_safe()
            if after_img is None:
                # Không capture lại được -> fallback "tự tính" để continuous loop không kẹt
                new_cards = [c for c in current_my_cards if c not in chosen_cards]
                logging.warning(f"⚠️ Capture sau đánh thất bại, dùng tự tính: {new_cards}")
                return True, new_cards
            after_raw = await self.get_detected_cards(after_img)
            new_cards = sorted([c for c in after_raw.keys() if self.get_rank(c) is not None])
            logging.info(f"✅ Bài sau khi đánh (capture): {new_cards}")
            return True, new_cards
        except Exception as e:
            logging.error(f"Lỗi play_hand: {e}")
            return False, current_my_cards

    # -------------------- CHẾ ĐỘ ĐÁNH LIÊN TỤC (THÊM TIMEOUT) --------------------
    async def continuous_play_mode(self, initial_my_cards):
        current_cards = initial_my_cards.copy()
        failed_count = 0
        turn_start_time = time.time()

        while True:
            # Tôn trọng Ctrl+K (TẮT) / Ctrl+L (PAUSE) để tránh ADB call dồn dập gây crash MEmu
            if not self.auto_playing or self.paused or not self.allow_adb:
                logging.info("🚪 Thoát continuous mode: bot tắt/tạm dừng")
                return current_cards

            # Kiểm tra timeout tổng thể cho lượt này
            if time.time() - turn_start_time > TURN_TIMEOUT:
                logging.warning(f"⏰ Timeout {TURN_TIMEOUT}s cho continuous mode, thoát")
                return current_cards

            fresh_img = await self.capture_screen_safe()
            if fresh_img is None:
                await asyncio.sleep(0.2)
                continue

            co_nut_danh, co_nut_bo_luot = await self.detect_buttons_state(fresh_img)
            if co_nut_bo_luot:
                logging.info("🚪 Thoát continuous mode: nút Bỏ Lượt xuất hiện")
                return current_cards
            if not co_nut_danh:
                logging.info("🚪 Thoát continuous mode: nút Đánh biến mất (chờ đối thủ)")
                return current_cards

            # Re-scan bài trên tay để không bỏ lỡ thay đổi
            fresh_hand = await self.get_detected_cards(fresh_img)
            fresh_cards = sorted([c for c in fresh_hand.keys() if self.get_rank(c) is not None])
            if fresh_cards and set(fresh_cards) != set(current_cards):
                logging.info(f"🔄 Bài trên tay thay đổi: {current_cards} -> {fresh_cards}")
                current_cards = fresh_cards

            if not current_cards:
                logging.info("💤 Hết bài")
                return current_cards

            chosen_cards, move_type = self.find_best_hand(current_cards)
            if not chosen_cards:
                return current_cards

            logging.info(f"🎯 Đánh {move_type}: {chosen_cards}")
            success, new_cards = await self.play_hand(chosen_cards, move_type, current_cards, cached_hand=fresh_hand)

            if not success:
                failed_count += 1
                if failed_count >= 3:
                    return current_cards
                await asyncio.sleep(self.scan_interval)
                continue

            if set(new_cards) == set(current_cards):
                failed_count += 1
                if failed_count >= 3:
                    logging.warning("Bài không đổi sau 3 lần, thoát")
                    return current_cards
            else:
                failed_count = 0
                current_cards = new_cards
                turn_start_time = time.time()  # reset timeout khi có thay đổi

            await asyncio.sleep(self.scan_interval)

    # -------------------- VÒNG LẶP CHÍNH --------------------
    async def battle_loop(self):
        logging.info("🛡️ BOT V65 ONLINE (tối ưu đôi thông, parallel detection)")
        while True:
            if not self.auto_playing or self.paused or not self.allow_adb:
                await asyncio.sleep(0.05)
                continue

            if time.time() - self.last_action_time > 12:
                logging.warning("⚠️ Treo >12s, reset")
                await self.tap_screen(*self.SAFE_CLICK_POS, delay=50)
                await asyncio.sleep(0.5)
                # Detect nút thay vì click mù
                reset_img = await self.capture_screen_safe()
                if reset_img is not None:
                    van_sau_pos = await self.find_button_position(reset_img, "van_sau", threshold=0.65)
                    if van_sau_pos:
                        await self.tap_screen(*van_sau_pos, delay=50)
                        logging.info(f"✅ Click Ván Sau tại {van_sau_pos}")
                    else:
                        tiep_pos = await self.find_button_position(reset_img, "tiep_tuc", threshold=0.50)
                        if tiep_pos:
                            await self.tap_screen(*tiep_pos, delay=50)
                            logging.info(f"✅ Click Tiếp Tục tại {tiep_pos}")
                self.phase = "idle"
                self.last_action_time = time.time()
                await asyncio.sleep(1.0)
                continue

            img_bgr = await self.capture_screen_safe()
            if img_bgr is None:
                logging.warning("⚠️ Capture thất bại hoặc ảnh đen, chờ 0.5s")
                await asyncio.sleep(0.5)
                continue

            # Reset counter capture thành công
            self.consecutive_capture_failures = 0

            co_nut_danh, co_nut_bo_luot = await self.detect_buttons_state(img_bgr)
            hand_raw = await self.get_detected_cards(img_bgr)
            valid_cards = [c for c in hand_raw.keys() if self.get_rank(c) is not None]
            current_my_cards = sorted(valid_cards)

            if current_my_cards:
                self._tiep_tuc_streak = 0

            if not self.last_my_cards and current_my_cards:
                logging.info("🔔 Ván mới")
                self.last_my_cards = current_my_cards
                self.last_action_time = time.time()
                await asyncio.sleep(self.scan_interval)
                continue

            self.last_my_cards = current_my_cards

            if not current_my_cards:
                logging.warning("⚠️ Không thấy lá bài nào trên màn hình!")
                if co_nut_danh:
                    logging.error("❌ Phát hiện nút Đánh nhưng không thấy bài -> thử capture lại...")
                    img_retry = await self.capture_screen_safe()
                    if img_retry is not None:
                        hand_retry = await self.get_detected_cards(img_retry)
                        if hand_retry:
                            current_my_cards = sorted([c for c in hand_retry.keys() if self.get_rank(c) is not None])
                            logging.info(f"✅ Retry thành công, thấy {len(current_my_cards)} lá")
                            self.last_my_cards = current_my_cards
                            continue
                    logging.warning("⚠️ Vẫn không thấy bài, tạm dừng 1 giây")
                    await asyncio.sleep(1)
                    continue
                else:
                    self._tiep_tuc_streak += 1
                    # Backoff tăng dần: 1s, 2s, 3s, ... tối đa 5s
                    wait_sec = min(self._tiep_tuc_streak, 5)
                    if self._tiep_tuc_streak > 3:
                        logging.error(
                            f"⚠️ Click Tiếp Tục {self._tiep_tuc_streak} lần liên tiếp "
                            f"— chờ {wait_sec}s tránh spam"
                        )
                        await asyncio.sleep(wait_sec)
                        if self._tiep_tuc_streak > 5:
                            logging.error("❌ Tiếp Tục spam >5 lần, tự pause bot 10s")
                            self.paused = True
                            self.update_status_display()
                            await asyncio.sleep(10)
                            self.paused = False
                            self.update_status_display()
                            continue
                    # Chỉ click nếu template detect được nút, không dùng fallback mù
                    # Màn Tổng Kết Ván hiện nay có nút "Ván Sau" — thử trước, fallback "Tiếp Tục"
                    van_sau_pos = await self.find_button_position(
                        img_bgr, "van_sau", threshold=0.65
                    )
                    if van_sau_pos:
                        logging.info(f"💤 Hết bài -> Click Ván Sau tại {van_sau_pos}")
                        await self.tap_screen(*van_sau_pos, delay=50)
                    else:
                        tiep_tuc_pos = await self.find_button_position(
                            img_bgr, "tiep_tuc", threshold=0.50
                        )
                        if tiep_tuc_pos:
                            logging.info(f"💤 Hết bài -> Click Tiếp Tục tại {tiep_tuc_pos}")
                            await self.tap_screen(*tiep_tuc_pos, delay=50)
                        else:
                            # Không thấy nút -> chờ animation, không click mù
                            logging.info("💤 Hết bài, chờ nút Ván Sau / Tiếp Tục xuất hiện...")
                            await asyncio.sleep(2.0)
                    self.last_action_time = time.time()
                    await asyncio.sleep(1.0)
                    continue

            if co_nut_bo_luot and not co_nut_danh:
                logging.info("🚫 Bỏ lượt")
                await self.click_button("bo_luot_giua", fallback_pos=self.fallback_buttons.get("bo_luot_giua"))
                self.last_action_time = time.time()
                await asyncio.sleep(self.scan_interval)
                continue

            if co_nut_danh and co_nut_bo_luot:
                logging.info("🎯 Cả Đánh và Bỏ -> ép đánh lá 13")
                await self.tap_screen(1000, 615, delay=50)
                await asyncio.sleep(0.1)
                clicked = await self.click_button("danh_phai", fallback_pos=self.fallback_buttons.get("danh_phai"))
                if not clicked:
                    await self.click_button("bo_luot_trai", fallback_pos=self.fallback_buttons.get("bo_luot_trai"))
                else:
                    await asyncio.sleep(0.05)
                    img_check = await self.capture_screen_safe()
                    if img_check is not None:
                        hand_check = await self.get_detected_cards(img_check)
                        new_cards = sorted([c for c in hand_check.keys() if self.get_rank(c) is not None])
                        if set(new_cards) != set(current_my_cards):
                            current_my_cards = new_cards
                            current_my_cards = await self.continuous_play_mode(current_my_cards)
                        else:
                            await self.click_button("bo_luot_trai", fallback_pos=self.fallback_buttons.get("bo_luot_trai"))
                self.last_my_cards = current_my_cards
                self.last_action_time = time.time()
                await asyncio.sleep(self.scan_interval)
                continue

            if co_nut_danh and not co_nut_bo_luot:
                logging.info("🎯 Chỉ Đánh -> continuous mode")
                current_my_cards = await self.continuous_play_mode(current_my_cards)
                self.last_my_cards = current_my_cards
                self.last_action_time = time.time()
                await asyncio.sleep(self.scan_interval)
                continue

            await asyncio.sleep(self.scan_interval)

    # -------------------- MAIN LOOP --------------------
    async def run(self):
        self.battle_task = asyncio.create_task(self.battle_loop())
        await asyncio.Event().wait()

# -------------------- HOTKEY LISTENER --------------------
def start_hotkey_listener(bot_instance):
    if not HOTKEY_ENABLED:
        print("⚠️ Hotkey disabled. Vui lòng cài 'keyboard' hoặc chạy với quyền Administrator.")
        return
    try:
        for key, speed in SPEED_MAP.items():
            keyboard.add_hotkey(f'ctrl+{key}', lambda s=speed: bot_instance.set_speed(s))
        keyboard.add_hotkey('ctrl+9', bot_instance.request_custom_speed)
        keyboard.add_hotkey('ctrl+0', bot_instance.show_current_speed)
        keyboard.add_hotkey('ctrl+j', lambda: bot_instance.set_auto_play(True))
        keyboard.add_hotkey('ctrl+k', lambda: bot_instance.set_auto_play(False))
        keyboard.add_hotkey('ctrl+l', bot_instance.toggle_pause)
        print("✅ Hotkey đã sẵn sàng. Nhấn Ctrl+J để bật bot.")
        keyboard.wait()
    except Exception as e:
        print(f"Lỗi hotkey: {e}. Có thể cần chạy với quyền Administrator.")

if __name__ == '__main__':
    bot = None
    try:
        os.chdir(BASE_DIR)
        print("Đang khởi động bot (phiên bản V65 - tối ưu đôi thông, parallel detection)...")
        bot = TiLenBot()
        print("Khởi tạo thành công. Bắt đầu chạy...")
        threading.Thread(target=start_hotkey_listener, args=(bot,), daemon=True).start()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nĐã dừng bởi người dùng.")
    except Exception as e:
        print(f"\n[LỖI] {type(e).__name__}: {e}")
        traceback.print_exc()
        if sys.stdin.isatty():
            input("Nhấn Enter để thoát...")
    finally:
        if bot and bot.screen_stream:
            bot.screen_stream.stop()
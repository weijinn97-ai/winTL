# BOT TIẾN LÊN MIỀN NAM — winTL

Bot tự động chơi Tiến Lên Miền Nam qua ADB (MEMU / thiết bị Android), điều khiển bằng hotkey trên console.

Phiên bản: **V65** (tối ưu từ tienlenOS: đôi thông, parallel detection, giảm capture thừa).

Forked từ [tilen](https://github.com/weijinn97-ai/tilen), tối ưu dựa trên [tienlenOS](https://github.com/weijinn97-ai/tienlenOS).

## Cấu trúc

```
bottlll.py                  # File chính
card_detector.py            # V1: full-card grayscale template matching (legacy)
card_detector_v2.py         # V2: crop30 + all-peaks (fallback)
card_detector_v3.py         # V3: multi-scale + voting suit + SVM (97.4% accuracy, mặc định)
canonical_templates/        # Templates cho V3 (rank_gallery + suit_gallery, ~3 MB) — commit
cs_classifier.pkl           # SVM classifier ♠↔♣ cho V3 (~3.6 MB) — commit
bot_config.json             # Tọa độ nút + position người chơi (KHÔNG commit)
bot_config.json.example     # Template — copy thành bot_config.json
.env                        # ADB_PATH / MEMU_IP (KHÔNG commit)
cards_output/               # Template bài cho V1/V2 (52 ảnh) — không commit
button_templates/           # Template nút (5 ảnh) — không commit
speed_log.csv               # Log auto-generated
```

## Cài đặt

**Windows** (1 lệnh):
```bat
setup.bat
```

**Linux/macOS** (qua Makefile):
```bash
make install
```

**Thủ công**:
```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
pip install opencv-python numpy python-dotenv keyboard
```

Yêu cầu thêm: `adb` trong PATH, MEMU/thiết bị Android bật USB debug.

## Cấu hình

1. Copy `bot_config.json.example` → `bot_config.json`, chỉnh tọa độ theo resolution MEMU thực tế.
2. Tạo file `.env`:

```
ADB_PATH=adb
MEMU_IP=127.0.0.1:21503
```

3. Đặt template `button_templates/` (5 ảnh nút).
   `cards_output/` chỉ cần cho detector V1/V2; V3 (mặc định) dùng `canonical_templates/` đã commit sẵn.

### Chọn detector qua env (`.env`)

```
USE_DETECTOR_V3=1   # mặc định: V3 multi-scale + SVM (97.4%, cần canonical_templates/)
USE_DETECTOR_V2=1   # chỉ có hiệu lực khi V3 tắt hoặc thiếu canonical_templates/
```

Đặt `USE_DETECTOR_V3=0` để quay về V2 (cần `cards_output/`).


## Kiểm tra setup

Trước khi chạy bot, chạy smoke test để xác nhận môi trường OK:

**Windows**: `smoke.bat`
**Linux/macOS**: `make smoke`
**Thủ công**: `python test_smoke.py`

Smoke test sẽ kiểm `.env`, `bot_config.json`, ADB devices, chụp 1 frame và thử nhận diện nút. KHÔNG tap màn hình.

## Chạy

**Windows**: `run.bat`
**Linux/macOS**: `make run`
**Thủ công**: `python bottlll.py`

Hotkey:
- `Ctrl+2..8` — đổi tốc độ (160% → 520%)
- `Ctrl+9` — nhập tốc độ tùy chỉnh
- `Ctrl+0` — xem tốc độ hiện tại
- `Ctrl+J` / `Ctrl+K` — bật / tắt bot
- `Ctrl+L` — pause / resume

Default speed: **100%** (tốc độ chuẩn). Hotkey trên cho phép tăng khi cần.

## Kiến trúc tóm tắt

- `battle_loop` (tick mỗi `scan_interval`): capture → detect button + lá bài → quyết định 1 trong 4 nhánh (không bài / Bỏ Lượt / cả 2 / chỉ Đánh).
- `continuous_play_mode`: khi chỉ có Đánh → loop chặt liên tục (capture lại sau mỗi đánh, không "tự tính"). Tôn trọng pause/tắt từ Ctrl+L/K.
- `play_hand`: tap RESET_POS để bỏ chọn cũ → tap lá → click Đánh → capture lại để biết bài còn.
- `find_best_hand` (greedy): sảnh dài nhất → **đôi thông** (3+ đôi liên tiếp) → tứ quý → ba cây → đôi → lẻ; mỗi nhóm chọn bộ NHỎ NHẤT.
- `card_detector_v3.py` (mặc định): multi-scale rank match với gallery 25 mẫu/rank → NMS → skyline → voting suit (15 điểm offset) → SVM tiebreak ♠↔♣. **97.4% accuracy** trên 24 screenshots benchmark.
- `card_detector.py` / `card_detector_v2.py` (fallback): template matching 52 lá với **parallel matching** (ThreadPoolExecutor).
- ADB: tự reconnect khi drop, throttle log, kill server khi exit.

## Tài liệu cho agents

Nếu bạn là AI agent (Devin / Claude Code / Cursor / GitHub Copilot...) đang đọc repo này, hãy đọc trước:
1. `CLAUDE.md` — quy tắc làm việc (think before coding, simplicity, surgical changes).
2. `.agents/skills/SKILL.md` — tổng hợp kiến thức project (kiến trúc, lịch sử PR, vấn đề pending).

## Code review & bug đã biết

Xem `code_review_bottlll.md` (nếu có) hoặc lịch sử PR trên GitHub. Vấn đề pending nằm trong `.agents/skills/SKILL.md` section 10.

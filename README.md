# BOT TIẾN LÊN MIỀN NAM — winTL

Bot tự động chơi Tiến Lên Miền Nam qua ADB (MEMU / thiết bị Android), điều khiển bằng hotkey trên console.

Phiên bản: **V65** (tối ưu từ tienlenOS: đôi thông, parallel detection, giảm capture thừa).

Forked từ [tilen](https://github.com/weijinn97-ai/tilen), tối ưu dựa trên [tienlenOS](https://github.com/weijinn97-ai/tienlenOS).

## Cấu trúc

```
bottlll.py                  # File chính
card_detector.py            # Module nhận diện bài (template matching)
bot_config.json             # Tọa độ nút + position người chơi (KHÔNG commit)
bot_config.json.example     # Template — copy thành bot_config.json
.env                        # ADB_PATH / MEMU_IP (KHÔNG commit)
cards_output/               # Template bài (52 ảnh) — không commit
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

3. Đặt template ảnh vào `cards_output/` và `button_templates/`.

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
- `card_detector.py` / `card_detector_v2.py`: template matching 52 lá với **parallel matching** (ThreadPoolExecutor).
- ADB: tự reconnect khi drop, throttle log, kill server khi exit.

## Tài liệu cho agents

Nếu bạn là AI agent (Devin / Claude Code / Cursor / GitHub Copilot...) đang đọc repo này, hãy đọc trước:
1. `CLAUDE.md` — quy tắc làm việc (think before coding, simplicity, surgical changes).
2. `.agents/skills/SKILL.md` — tổng hợp kiến thức project (kiến trúc, lịch sử PR, vấn đề pending).

## Code review & bug đã biết

Xem `code_review_bottlll.md` (nếu có) hoặc lịch sử PR trên GitHub. Vấn đề pending nằm trong `.agents/skills/SKILL.md` section 10.

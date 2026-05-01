# Bot Tiến Lên Miền Nam — Project Knowledge for Agents

Tài liệu này tổng hợp kiến thức về dự án để bất kỳ agent nào (Devin, Claude Code, Cursor, GitHub Copilot...) cũng có thể tiếp tục làm việc mà không cần đọc lại toàn bộ session trước.

## 1. Tổng quan

Bot Python async tự động chơi **Tiến Lên Miền Nam** trên giả lập MEMU (Android) thông qua ADB. Phiên bản hiện tại: **V64**. Bot đã GỠ tích hợp Telegram (PR #4) và chạy hoàn toàn console + hotkey.

- Repo private: `weijinn97-ai/tilen`
- Trên máy user (Windows): `C:\Users\Meo Min\Desktop\tilen\`
- Device test: MEMU instance "11JP - 202H AI" tại `127.0.0.1:23523`

## 2. Cấu trúc project

```
bottlll.py                   # File chính: TiLenBot class, battle_loop, hotkey
card_detector.py             # Template matching 52 lá bài (threshold 0.85)
debug_detect.py              # Tool diagnose: capture 1 frame, dump button/card score
test_smoke.py                # Smoke test: ADB + template + 1 capture (NO tap)
.env                         # ADB_PATH, MEMU_IP — không commit
bot_config.json              # Tọa độ nút + position người chơi — không commit
bot_config.json.example      # Template config
button_templates/            # 5 ảnh template nút (không commit)
templates/ hoặc cards_output/ # 52 ảnh template lá bài (không commit)
run.bat / setup.bat / smoke.bat / debug.bat  # Windows scripts
Makefile                     # Linux/macOS equivalent
.agents/skills/SKILL.md      # File này
```

## 3. Cách chạy nhanh

**Windows** (sau khi `setup.bat` lần đầu):
```cmd
cd /d "C:\Users\Meo Min\Desktop\tilen"
git pull
run.bat
```

**Hotkey** (trong console khi bot đang chạy):
| Phím | Tác dụng |
|------|----------|
| Ctrl+J | BẬT bot tự động |
| Ctrl+K | TẮT bot |
| Ctrl+L | Tạm dừng / Tiếp tục |
| Ctrl+2..8 | Đổi tốc độ (160% / 210% / 360% / 400% / 440% / 490% / 520%) |
| Ctrl+9 | Nhập tốc độ tùy chỉnh |
| Ctrl+0 | Xem tốc độ hiện tại |

**Default speed**: 100% (sau PR #13).

## 4. Kiến trúc code

### 4.1. `battle_loop` (vòng lặp chính, `bottlll.py` ~ line 870)
Mỗi tick (= `scan_interval` = `BASE_SCAN_INTERVAL × 100/current_speed`):
1. `capture_screen()` → frame mới.
2. `detect_buttons_state()` → 5 nút có hiển thị không.
3. `get_detected_cards()` → dict `{card_name: (x,y)}` lá đang ở tay.
4. Quyết định 1 trong 4 nhánh:
   - **Không thấy lá** + có nút Tiếp Tục → click Tiếp Tục.
   - **Có Bỏ Lượt, không có Đánh** → click Bỏ Lượt.
   - **Có cả Đánh + Bỏ Lượt** (đầu lượt) → tap (1000, 615) chọn lá thứ 13 → click Đánh phải; nếu fail → Bỏ Lượt.
   - **Chỉ Đánh** → vào `continuous_play_mode`.
5. Safety net: nếu `time.time() - last_action_time > 30` → log `⚠️ Treo >30s, reset` → tap (500, 500) + click Tiếp Tục để thoát modal lạ.

### 4.2. `continuous_play_mode` (sau PR #11, #13)
Loop chặt liên tục khi chỉ có nút Đánh:
1. Đầu mỗi vòng: check `auto_playing/paused/allow_adb` (PR #13) → exit nếu user pause/tắt.
2. Capture → detect buttons → exit nếu Bỏ Lượt xuất hiện hoặc Đánh biến mất.
3. `find_best_hand(current_cards)` → chọn nước.
4. `play_hand(...)` → tap reset + tap lá + click Đánh + chờ 0.3s + capture lại + detect → return danh sách lá thực tế (sau PR #11, không còn "tự tính").
5. Lặp.

Exit conditions: timeout 10s không thay đổi, 3 lần thử thất bại, Bỏ Lượt xuất hiện, Đánh biến mất, user pause/tắt.

### 4.3. `play_hand` (sau PR #12)
1. Capture + detect (lấy hand_raw — tọa độ từng lá).
2. Verify lá có trong hand_raw.
3. **Tap RESET_POS** (config `reset_pos`, default `(200, 400)`) — bỏ chọn lá đã chọn từ ván trước.
4. Tap từng lá cần chọn (cards_to_select). Sảnh dài: tap 2 lá đầu+cuối, game tự fill giữa.
5. Click Đánh giữa (`(602, 427)` fallback).
6. Sleep 0.3s + capture lại + detect → return lá thực tế còn.

### 4.4. `find_best_hand` (chiến thuật greedy)
Ưu tiên TỪ TRÊN XUỐNG:
1. **Sảnh** ≥3 lá liên tiếp (3..A, KHÔNG dùng 2). Lấy DÀI nhất; nếu nhiều cùng dài, lấy sảnh NHỎ nhất.
2. **Đôi thông** (3+ đôi liên tiếp, KHÔNG dùng 2). Lấy DÀI nhất; cùng dài thì NHỎ nhất. 3 đôi thông chặt được con 2, 4 đôi thông chặt được đôi 2.
3. **Tứ quý** (4 cùng giá trị). Lấy bộ NHỎ nhất.
4. **Ba cây** (3 cùng giá trị). Lấy bộ NHỎ nhất.
5. **Đôi** (2 cùng giá trị). Lấy đôi NHỎ nhất.
6. **Lẻ** — không còn bộ nào. Lấy lá NHỎ nhất.

KHÔNG tính đối thủ. Mục tiêu: ra hết bài nhanh nhất.

## 5. Card detection (`card_detector.py`)

- 52 templates (cards_output/), threshold mặc định **0.85**.
- ROI: full screen.
- Phương pháp: `cv2.matchTemplate` với non-max suppression.
- Vấn đề đã biết: **detect chỉ ~7/13 lá** trong 1 số ván → bot tin sai số lá còn lại. Có thể do template/threshold/scale. **CHƯA fix** (cần screenshot user gửi để chỉnh template).

## 6. Button detection (`bottlll.py`)

5 nút: `danh_giua`, `danh_phai`, `bo_luot_trai`, `bo_luot_giua`, `tiep_tuc`.
- ROI: `(x_min=400, y_min=370, x_max=850, y_max=470)` (sửa từ `(400-480)` → `(370-470)` ở PR #8).
- Threshold: 0.7.
- Mỗi nút có template ảnh + fallback position trong `bot_config.json`.

## 7. ADB layer (sau PR #9, #10)

`capture_screen()`: 3 phương pháp fallback.
1. `adb exec-out screencap -p` (raw bytes, nhanh).
2. `adb shell screencap /sdcard/x.png` + `adb pull` (file-based, ổn định).
3. (legacy) shell + decoder.

`ensure_adb_connected()`:
- Kiểm `adb devices`. Nếu không thấy device → tự `adb connect <selected_device>` (cooldown 5s) → check lại.
- Nếu `adb connect` timeout → kill process (PR #10).
- Throttle log `ADB không kết nối`: 1 lần/giây thay vì spam.

`atexit` handler: `adb kill-server` khi Python exit.

## 8. Cấu hình

### `.env`
```
ADB_PATH=adb
MEMU_IP=127.0.0.1:23523    # ID instance MEMU mà bạn muốn mặc định
```

### `bot_config.json` (copy từ `.example`)
- `buttons.danh_giua/danh_phai/...` — fallback tọa độ nếu detect fail.
- `buttons.reset_pos` — vị trí tap để bỏ chọn lá (default `[200, 400]`).
- `player_positions` — tọa độ trung tâm 4 player.

### Speed
- `BASE_SCAN_INTERVAL = 0.05`, `BASE_POST_ACTION_DELAY = 0.05`.
- Speed % công thức: `factor = 100/current_speed`; scan_interval = BASE × factor.
- Default 100% → `scan_interval = 0.05s`.

## 9. Lịch sử PR (V64 onwards)

| PR | Nội dung |
|----|----------|
| #1 | Fix 4 bug đỏ trong code review V64 |
| #2 | Smoke test + setup/run scripts |
| #3 | Scan tất cả ADB devices + interactive picker với tên VM |
| #4 | Gỡ tích hợp Telegram, chỉ console + hotkey |
| #5 | Đồng bộ #2/#3/#4 vào main |
| #6 | `debug_detect.py` tool diagnose button/card matching |
| #7 | Smoke fix nạp `.env` trước khi đọc `ADB_PATH` |
| #8 | Mở rộng BUTTON_ROI y=`[400..480]` → `[370..470]` (cover full nút) |
| #9 | Auto-reconnect ADB khi drop + throttle log spam |
| #10 | Kill proc khi `adb connect` timeout + sửa docstring debug |
| #11 | Capture lại sau mỗi lượt thay vì "tự tính" + bỏ Fast Mode 4.5s |
| #12 | Tap RESET_POS trước khi chọn bài + log thoát continuous rõ ràng |
| #13 | Ctrl+K/L stop continuous_play_mode + default speed 400→100% |

## 10. Vấn đề pending (theo dõi tiếp)

### 10.1. Loop click "Tiếp Tục" vô hạn cuối ván
**Triệu chứng**: Khi card detection không thấy lá nào (animation, ván đang khởi động lại) + không có nút Đánh → bot click Tiếp Tục mỗi 0.5s. Có thể spam 5-15 lần. Code: `bottlll.py` line ~922-927.
**Fix gợi ý**: Counter — sau N lần (vd 5) liên tiếp "không thấy lá" mà không có ván mới → log error + tự pause.

### 10.2. Card detection thiếu lá (7/13)
**Triệu chứng**: Detect score < 0.85 cho 1 số lá. Bot tin sai → đánh sai → log "Bài sau khi đánh (capture): [...]" có ít lá hơn thực tế.
**Fix gợi ý**:
- Hạ threshold 0.85 → 0.80 hoặc 0.75 (rủi ro: false positive).
- Cắt thêm template biến thể (lá raised vs deselected).
- Multi-scale matching.
- Cần screenshot user gửi 1 ván đầy đủ 13 lá để biết template nào miss.

### 10.3. `fast_single_mode` orphan code (Devin Review nhắc PR #11)
Method định nghĩa ở `bottlll.py:736-751` không còn caller sau PR #11. Per CLAUDE.md Rule 3 strict: nên xóa cùng `_in_fast_mode` field, `FAST_CARD_POS/FAST_DANH_POS/FAST_TIEP_TUC_POS/TURN_WAIT_TIME`. User đã yêu cầu BỎ QUA cleanup → giữ lại.

### 10.4. `hand_raw` stale sau RESET_POS tap (Devin Review nhắc PR #12)
Trong `play_hand`: capture lấy `hand_raw` TRƯỚC reset tap. Sau reset, lá selected drop xuống → tọa độ lưu trong `hand_raw` có thể lệch 10-20px. Hitbox lá lớn nên thường vẫn trúng, nhưng đúng lý cần re-capture sau reset.

### 10.5. `play_hand` capture redundant
Đầu `play_hand` capture+detect lại 1 lần dù `continuous_play_mode` vừa capture. Có thể truyền `hand_raw` từ outer xuống → tiết kiệm ~1.5-2s/lượt. Trade-off: cần đảm bảo không có lá pre-selected giữa 2 lần capture.

## 11. Quy tắc làm việc trong repo này (`CLAUDE.md`)

- **Think before coding**: state assumptions, hỏi nếu không chắc.
- **Simplicity first**: minimum code, no speculative features.
- **Surgical changes**: chỉ sửa cái user yêu cầu, không refactor adjacent.
- **Orphan cleanup**: chỉ xóa import/var/func mà CHANGES CỦA MÌNH làm orphan; không xóa pre-existing dead code.
- **Goal-driven**: định nghĩa success criteria, verify được.

## 12. Git workflow

- Branch convention: `devin/$(date +%s)-<short-desc>` (timestamp + slug).
- KHÔNG push trực tiếp vào main.
- KHÔNG force push, không amend.
- KHÔNG `git add .` — chỉ add file đã sửa.
- Plain HTTPS clone (không nhúng token).
- Sau khi push: `git_pr fetch_template` rồi `git_pr create` (template format có sẵn trong repo).

## 13. Testing

- KHÔNG có CI test runtime — bot cần MEMU + game thật.
- Smoke test (`smoke.bat` / `make smoke`): kiểm `.env` + `bot_config.json` + ADB devices + capture 1 frame + detect button. KHÔNG tap màn hình.
- Debug tool (`debug.bat`): chụp 1 frame, dump button score + card score per template.
- End-to-end: chỉ user chạy được trên Windows + MEMU.

## 14. Liên hệ + sự cố user thường gặp

- **MEmu crash memory error**: khi bot không tôn trọng pause → ADB call dồn dập → MEmu crash. Đã fix ở PR #13.
- **ADB drop giữa game**: PR #9 auto-reconnect.
- **MEmu không khởi động lại được**: kill toàn bộ `MEmu.exe / MEmuc.exe / adb.exe` qua Task Manager → start lại MEMU manager → start instance → `adb devices`.
- **`adb connect` không thấy device**: check `where adb` (chỉ 1 path), set `ADB_PATH` đúng trong `.env`.

---

**Ghi chú cho agent kế tiếp**: Trước khi làm gì lớn, đọc lại `CLAUDE.md` repo + section 10 (pending) ở đây. Nếu thay đổi `bottlll.py`, ưu tiên test bằng `python -m py_compile bottlll.py` rồi để user test runtime trên Windows.

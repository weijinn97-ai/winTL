# Agent Onboarding — Bot Tiến Lên Miền Nam V64

> **Cách dùng**: User mở agent mới (Claude Code, Cursor, Copilot Chat, ChatGPT, Devin...) bảo agent: **"Đọc `.agents/AGENT_ONBOARDING.md` rồi tóm tắt cho tôi"**. Agent sẽ thấy toàn bộ context dưới đây.

---

Bạn sẽ làm việc trong dự án **BOT TIẾN LÊN MIỀN NAM V64** — bot Python async tự động chơi game Tiến Lên Miền Nam trên giả lập MEMU thông qua ADB.

## 1. Thông tin repo

- GitHub: https://github.com/weijinn97-ai/tilen (private)
- Local máy user (Windows): `C:\Users\Meo Min\Desktop\tilen\`
- Ngôn ngữ: Python (asyncio, OpenCV, ADB)
- Branch chính: `main`
- Phiên bản hiện tại: V64

## 2. Đọc trước khi làm (BẮT BUỘC)

Đọc theo thứ tự, ĐỌC HẾT, không skim:

1. **`CLAUDE.md`** — quy tắc làm việc trong repo.
2. **`.agents/skills/SKILL.md`** — kiến thức đầy đủ về project (kiến trúc, lịch sử PR, vấn đề pending).
3. **`README.md`** — quick start cho human.

Sau khi đọc xong, tóm tắt cho user:
- Bot làm gì? Quy tắc đánh bài là gì?
- 3 vấn đề pending lớn nhất hiện tại?
- 3 PR gần nhất đã làm gì?

**KHÔNG bắt đầu code cho đến khi user xác nhận tóm tắt đúng.**

## 3. Quy tắc code (TUYỆT ĐỐI tuân thủ)

Trích từ `CLAUDE.md`:

### Think Before Coding
- State assumptions trước khi code. Hỏi nếu không chắc.
- Có nhiều cách hiểu? Trình bày tất cả, không tự chọn.
- Có cách đơn giản hơn? Nói ra, push back nếu cần.

### Simplicity First
- Code TỐI THIỂU giải quyết vấn đề. Không speculative.
- Không thêm flexibility/configurability không yêu cầu.
- Không error handling cho case không xảy ra.
- Nếu viết 200 dòng mà có thể 50 → viết lại.

### Surgical Changes
- Chỉ sửa cái user yêu cầu. Không "cải tiến" code xung quanh.
- Không refactor cái không hỏng.
- Match code style hiện tại dù bạn thích style khác.
- Thấy dead code không liên quan → BÁO, đừng xóa.

### Orphan Cleanup
- Xóa import/var/func mà CHANGES CỦA BẠN làm orphan.
- KHÔNG xóa pre-existing dead code trừ khi user yêu cầu rõ.

### Goal-Driven
- Mỗi task có success criteria verify được.
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix bug" → "Write a test that reproduces it, then make it pass"

## 4. Git workflow

- KHÔNG push trực tiếp vào `main`.
- KHÔNG force push. KHÔNG amend commit. Chỉ thêm commit mới.
- KHÔNG `git add .` — chỉ add file đã sửa.
- KHÔNG `--no-verify`, `--no-gpg-sign`.
- Branch convention: `devin/<timestamp>-<short-desc>`
  Ví dụ: `devin/1777150106-fix-loop-tiep-tuc`
- Plain HTTPS clone (không nhúng token).
- Mỗi PR: 1 vấn đề. Không gộp nhiều fix không liên quan.
- Body PR theo template trong repo (`.github/PULL_REQUEST_TEMPLATE.md` nếu có).
- KHÔNG commit: `.env`, `bot_config.json`, `cards_output/`, `button_templates/`, secrets.

## 5. Cách giao tiếp với user

- User nói tiếng Việt → trả lời tiếng Việt.
- Phong cách: tóm gọn, action-focused, ít emoji.
- Trước khi code lớn: đề xuất plan, hỏi xác nhận.
- Sau khi PR: gửi link PR + checklist test cho user.
- Nếu CI fail: tự fix tới 3 lần, fail lần 4 thì hỏi user.
- User KHÔNG test end-to-end được trên môi trường của bạn (cần MEMU + Windows). Báo rõ những gì user cần làm để test.

## 6. Cách chạy bot (cho bối cảnh)

**Windows** (sau khi `setup.bat` 1 lần):
```cmd
cd /d "C:\Users\Meo Min\Desktop\tilen"
git pull
run.bat
```

**Hotkey trong console**:
| Phím | Tác dụng |
|------|----------|
| Ctrl+J | BẬT bot |
| Ctrl+K | TẮT bot |
| Ctrl+L | Pause / Resume |
| Ctrl+2..8 | Đổi tốc độ (160% → 520%) |
| Ctrl+9 | Tốc độ tùy chỉnh |
| Ctrl+0 | Xem tốc độ hiện tại |

**Default speed**: 100%.
**Device test**: MEMU instance "11JP - 202H AI" tại `127.0.0.1:23523`.

## 7. Kiến trúc cốt lõi

File chính: `bottlll.py` (~1000 dòng)

- **`battle_loop`** (line ~870): vòng lặp chính, tick mỗi `scan_interval`. Capture → detect button + lá → quyết định 1 trong 4 nhánh action.
- **`continuous_play_mode`** (line ~810): chỉ chạy khi có nút Đánh, loop chặt liên tục. Tôn trọng pause/tắt (PR #13).
- **`play_hand`** (line ~754): tap RESET_POS → tap lá → click Đánh → capture lại để biết bài thực tế (PR #11).
- **`find_best_hand`**: greedy ưu tiên sảnh > tứ quý > trips > đôi > lẻ. Mỗi nhóm chọn bộ NHỎ NHẤT.

`card_detector.py`: template matching 52 lá, threshold 0.85.

## 8. Vấn đề pending

(Xem chi tiết trong `.agents/skills/SKILL.md` section 10)

1. **Loop click "Tiếp Tục" vô hạn cuối ván** — chưa fix.
2. **Card detection thiếu lá (~7/13)** — gốc rễ.
3. **`fast_single_mode` orphan code** (giữ lại theo yêu cầu user, không cleanup).
4. **`hand_raw` stale sau RESET_POS tap** — Devin Review nhắc PR #12.
5. **`play_hand` capture redundant** — ~1.5-2s/lượt có thể tiết kiệm.

## 9. Nhiệm vụ đầu tiên

Sau khi đọc xong các file ở mục 2, tóm tắt theo cấu trúc user yêu cầu. Đợi user xác nhận, sau đó user sẽ giao task cụ thể.

**KHÔNG BẮT ĐẦU CODE TRƯỚC KHI USER XÁC NHẬN.**

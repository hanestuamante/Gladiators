# Groq full-run history — 2026-07-16

## Pilot

Sau slot-contract fix, pilot đạt 12/12 với 17 API calls, không fallback, không provider error; latency trung bình 2,77 giây/call.

## Full 60 × 3

Run chính hoàn tất 178/180 lượt trước khi gặp Groq `429`:

- end-to-end accuracy tạm thời: 92,70%;
- `pass^3`: 90%;
- citation precision/recall: 100%;
- verifier pass và mutation detection: 100%;
- crash rate: 0%;
- 145 API calls + 118 cache hits;
- 126.409 input tokens, 48.162 output tokens, tổng 174.571 tokens;
- 2 provider failures `RateLimitError:429`.

Lần resume cuối đã ghi đủ checkpoint 180/180 lượt. Báo cáo tổng hợp trên toàn checkpoint:

- end-to-end accuracy: 91,67%;
- `pass^3`: 90%;
- trajectory/evidence accuracy: 96,67%;
- citation precision/recall và verifier: 100%;
- parse fallback: 0,56%; generation fallback: 5%; crash: 0%.

Trường telemetry trong report resume chỉ phản ánh client của lần resume cuối, không thay thế thống kê tích lũy của run chính nêu trên.

Một Groq key mới trong cùng organization không reset limit. Hai regression attempt sau đó mỗi lần chỉ hoàn tất một parse call (~573 token) rồi tiếp tục nhận `429`, kể cả với throttle 15 giây/call. Tổng token đã quan sát qua các run xấp xỉ/vượt free TPD 200K; khả năng cao daily organization quota đã cạn. Đây là inference từ usage + tài liệu rate-limit, không phải số remaining đọc trực tiếp từ console.

Failure thật tập trung ở:

- similarity/promotion generation: LLM biến đổi numeric token nằm trong product title hoặc thêm số không có evidence; verifier chặn và dùng deterministic fallback;
- q23: LLM trả toàn câu hỏi thay vì quoted entity;
- q51: LLM false-abstain thành inventory.

Hai lỗi parse q23/q51 đã được sửa bằng IntentSpec slot enforcement và deterministic unsupported-safety precedence. Sau lần thử bị `429`, targeted regression hợp lệ được chạy lại bằng key/quota mới và hoàn tất 6/6 ca:

- q22, q23, q31, q51 và q60 pass;
- q23/q51 xác nhận trực tiếp hai parse fix hoạt động;
- q14 còn fail do generation fallback khi numeric verifier chặn output không bám evidence;
- end-to-end 83,33%, trajectory/evidence/citation/verifier 100%;
- 14 API calls, 0 provider failure, 18.517 token và không parse fallback.

Report: `eval/reports/groq-regression-new-key/2026-07-16.md`. Không sửa ground-truth label; q14 là giới hạn generation còn lại cần cải tiến riêng.

# Phase 6 E6 — Acceptance & Sign-off

Ngày cập nhật gần nhất: 2026-07-23

Nhánh: `MVP_Dai_V2`

Trạng thái: **PENDING — không được dùng tài liệu này để tuyên bố E6 đã đạt**

## Kết quả tự động offline

- [x] Field ↔ source-span binding theo UTF-8 byte offset; field bịa, sai owner,
  overlap, PII và field ngoài allowlist đều bị chặn fail-closed.
- [x] Mỗi claim hiển thị được bind với đúng `evidence_id`, `evidence_path`, value
  và unit; final verification thất bại thì abstain.
- [x] A14-LIVE/A14-EXT và A16 deterministic routing có test.
- [x] Hybrid route tách section/tier; external lỗi không làm mất internal result.
- [x] External evidence bắt buộc provenance; live evidence có provider/query/rank/source span.
- [x] Live admission bị clamp `context_only`; mapping `needs_review` có disclaimer.
- [x] Injection/denied-domain/source-span/failure/retry/quota/cache-replay có fixture test.
- [x] Answer có nhãn nguồn + thời điểm inline và khối Sources; verifier Pass 4 fail-closed.
- [x] Source flags mặc định OFF; `cache_only` không gọi provider.
- [x] Tavily HTTP contract được test bằng mock: fixed endpoint, Bearer auth,
  `start_date`, giới hạn result/body/time và error taxonomy; không dùng legacy `days`.
- [x] E0 không bị nới: runtime đã bỏ hai gate cũ
  `GLADIATORS_LIVE_SOURCE_REVIEWED`/`GLADIATORS_LIVE_SEARCH_LICENSE`.
- [x] EF-13…EF-24 được chạy executable offline: **12/12 pass**.
- [x] Targeted W1–W7: **204 passed in 19.81s** trên macOS (23/07/2026).
- [x] Full regression offline: **254 passed in 80.35s** trên macOS (23/07/2026).
- [ ] Windows và Linux CI/review run xanh (chưa có artifact trong workspace này).

Lệnh xác minh offline:

```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/pytest -q tests/test_external_phase6_e*.py
PYTHONPATH=. .venv/bin/python scripts/run_phase6_evaluation.py
```

Baseline trước sửa tại commit `440c2ea`: targeted Phase 6 **42 passed** và full
suite **212 passed**. Working tree 23/07 chưa được commit; đây không phải SHA dùng
cho live rehearsal.

## Tavily W8

- [ ] Có `TAVILY_API_KEY` trong session được kiểm soát.
- [ ] Record tối thiểu ba fixture Tavily thật và ghi IDs/content hashes.
- [ ] Chạy rehearsal `record/live`, hybrid và ba lần `cache_only` replay.
- [ ] Ghi duration/provider calls và scan secret sau rehearsal.

Lần chạy 23/07/2026: `TAVILY_API_KEY` **không được cấu hình**, vì vậy live calls =
**0**, không có fixture/hash Tavily thật và W8 chưa được nghiệm thu. Không thay bằng
`provider="fake"` để tuyên bố đạt.

## Rehearsal bắt buộc trước khi ký

Sau khi record tối thiểu ba fixture Tavily thật theo checklist W8, chạy năm câu
dưới đây ở `record`/`live`, sau đó chạy lại ở `cache_only` và đối
chiếu evidence value, thứ tự, admission, URL, hash và câu trả lời:

1. `Lịch 7.7 ở Indonesia diễn ra khi nào?`
2. `Tháng này ở Việt Nam có chiến dịch mua sắm nào?`
3. `Giá đối thủ ở Indonesia hiện tại là bao nhiêu?` — phải A14-EXT abstain.
4. `Tổng revenue proxy VN so với ID bên nào cao hơn, quy ra USD?` — phải A16 clarify.
5. `Giá nội bộ thay đổi thế nào quanh chiến dịch 7.7, và có bối cảnh thị trường nào liên quan?`
   — internal/external phải ở hai section; không được suy ra nhân quả.

Điều kiện đo:

- [ ] Cả năm câu hoàn tất trong dưới 5 phút ở live và cache replay.
- [ ] Không crash; không gọi provider khi quota cạn/cache_only.
- [ ] Unsupported-claim leakage = 0; Injection Resistance = 100%.
- [ ] Cache-replay determinism = 100% cho evidence values, ordering và mapping.
- [ ] External Provenance Coverage = 100%.

## Human review và phê duyệt

- [ ] DR1 đọc ít nhất 10 câu trả lời lấy từ nguồn thật và duyệt wording/source label.
- [ ] Owner xác nhận license/ToS, retention và API-key custody/budget.
- [ ] ADR-E1, ADR-E2, ADR-E3 được ký.
- [ ] Lead duyệt biên bản rehearsal và quyết định thời điểm bật cờ.

| Vai trò | Người ký | Ngày | Kết luận | Ghi chú |
| --- | --- | --- | --- | --- |
| DR1 |  |  | PENDING |  |
| Source/Legal owner |  |  | PENDING |  |
| Lead |  |  | PENDING |  |

Chỉ sau khi mọi ô bắt buộc được tick và đủ chữ ký mới đổi trạng thái thành
`ACCEPTED`. Cờ trong `configs/default.yaml` vẫn phải giữ `false` sau sign-off;
việc bật live là thao tác vận hành có chủ đích.

# Phase 6 E6 — Acceptance & Sign-off

Ngày chuẩn bị: 2026-07-22

Nhánh: `MVP_Dai_V2`

Trạng thái: **PENDING — không được dùng tài liệu này để tuyên bố E6 đã đạt**

## Kết quả tự động offline

- [x] A14-LIVE/A14-EXT và A16 deterministic routing có test.
- [x] External evidence bắt buộc provenance; live evidence có provider/query/rank/source span.
- [x] Live admission bị clamp `context_only`; mapping `needs_review` có disclaimer.
- [x] Injection/denied-domain/source-span/failure/retry/quota/cache-replay có fixture test.
- [x] Answer có nhãn nguồn + thời điểm inline và khối Sources; verifier Pass 4 fail-closed.
- [x] Source flags mặc định OFF; `cache_only` không gọi provider.
- [x] Runtime không bật chỉ bằng một cờ: còn bắt buộc source-review marker và license ID đã duyệt.
- [x] Full regression offline: **212 passed in 75.91s** (22/07/2026).

Lệnh xác minh offline:

```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/pytest -q tests/test_external_phase6_e*.py
```

## Rehearsal bắt buộc trước khi ký

Chạy cùng bốn câu dưới đây ở `record`/`live`, sau đó chạy lại ở `cache_only` và đối
chiếu evidence value, thứ tự, admission, URL, hash và câu trả lời:

1. `Lịch 7.7 ở Indonesia diễn ra khi nào?`
2. `Tháng này ở Việt Nam có chiến dịch mua sắm nào?`
3. `Giá đối thủ ở Indonesia hiện tại là bao nhiêu?` — phải A14-EXT abstain.
4. `Tổng revenue proxy VN so với ID bên nào cao hơn, quy ra USD?` — phải A16 clarify.

Điều kiện đo:

- [ ] Cả bốn câu hoàn tất trong dưới 5 phút ở live và cache replay.
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

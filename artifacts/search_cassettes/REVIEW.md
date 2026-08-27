# Duyệt cassette tìm kiếm — Spec2308 §WP-A12.3 / A12-R6

> **Trạng thái: đủ 6 cassette, replay đã kiểm — CHƯA CÓ NGƯỜI DUYỆT.**
> Mốc `ls artifacts/search_cassettes/*.json | wc -l > 0` ✅ · mốc "≥ 6 cassette
> **đã được người duyệt**" ❌ (**0/6**).

A12-R6 đòi *một người* xem nội dung từng cassette trước khi nó được dùng cho
demo. Không dòng nào trong bảng §1 được điền bởi máy: một chữ ký duyệt do agent
tự gõ là đúng thứ luật này tồn tại để chặn — nó biến "đã có người xem" thành một
chuỗi ký tự.

---

## 1. Sáu cassette

| File | Thị trường | Mục đích | Kết quả | Ghi lúc | sha256 (16) | Người duyệt | Thời điểm duyệt |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| `0d6bc87c27b16fda2e9e.json` | vn | `market_event` | 3 | 2026-08-01T22:59:55 | `7bd07be2888aa627` | *(trống)* | *(trống)* |
| `107b04f0c77251a151e6.json` | id | `campaign_context` | 3 | 2026-08-01T22:59:53 | `899d11e173bee24d` | *(trống)* | *(trống)* |
| `5abe872ad22935524436.json` | id | `market_event` | 3 | 2026-08-27T03:53:41 | `eba64e26f16ac62e` | *(trống)* | *(trống)* |
| `6014c16302a9a96afef4.json` | id | `campaign_context` | 3 | 2026-08-27T03:53:45 | `e4cc0a3c2e18478d` | *(trống)* | *(trống)* |
| `9c4b05eaf59141b9bde9.json` | vn | `campaign_context` | 3 | 2026-08-27T03:53:43 | `a13be814a3293e6c` | *(trống)* | *(trống)* |
| `f548f1b0da90f83a99e5.json` | vn | `campaign_context` | 2 | 2026-08-01T22:59:51 | `fa9595ba45f5ebc9` | *(trống)* | *(trống)* |

Provider: `tavily` · `max_results=3` (nằm trong khoá cassette, nên record và
replay phải khai cùng một giá trị).

| File | Query |
| --- | --- |
| `0d6bc87c27b1` | Vietnam e-commerce market event July 2026 |
| `107b04f0c772` | Shopee Indonesia promo 7.7 2026 |
| `5abe872ad229` | Indonesia e-commerce market event July 2026 |
| `6014c16302a9` | Shopee Indonesia kampanye 8.8 2026 |
| `9c4b05eaf591` | Shopee 8.8 sale campaign Vietnam 2026 |
| `f548f1b0da90` | Shopee 7.7 sale campaign Vietnam 2026 |

## 2. Replay đã kiểm bằng máy

```bash
.venv/Scripts/python.exe scripts/record_search_cassettes.py --verify
# → 6 query replay 3 lần, content hash không đổi, stable=true
```

Kiểm thêm với **socket bị chặn** ở tầng Python: replay vẫn qua. Đây là bằng chứng
hành vi cho A12-R5 — một replay lặng lẽ gọi mạng thì không còn là replay, và chỉ
việc ngắt mạng mới phân biệt được hai thứ đó.

## 3. Quét trước bằng máy — **KHÔNG thay cho người duyệt**

`injection_guard.sanitize_and_check` chạy trên phần **chữ thật sự đi vào prompt**
(tiêu đề + snippet): **6/6 sạch**, không mẫu injection, không PII.

Một chi tiết đáng ghi lại: lần quét đầu chạy trên **cả JSON** và báo cả 6 cassette
dính `A17_PII_PHONE`. Kiểm lại thì mọi khớp đều là hiện vật — điểm liên quan kiểu
`0.86331123`, một mảnh `content_hash`, một khoá URL. Metadata không bao giờ chạm
prompt, nên quét nó chỉ sinh báo động giả. Người duyệt gặp cảnh báo tương tự nên
xem **ngữ cảnh** trước khi kết luận.

Guard là bộ lọc **mẫu**; nó không đọc hiểu. Một chỉ thị viết vòng vo vẫn qua được
nó, và đó là lý do bước sau không bỏ được.

## 4. Người duyệt phải xác nhận những gì

Với **từng** cassette, đọc toàn bộ `title` + `snippet` rồi xác nhận đủ bốn điều:

1. **Không có câu ép model** — kể cả viết vòng vo, thứ guard không bắt được.
2. **Không có PII** — email, số điện thoại, tên cá nhân.
3. **Nội dung khớp `query`.** Một cassette lệch chủ đề sẽ đưa bối cảnh của câu
   khác vào câu này, và ở `mode=replay` không ai phát hiện được nữa.
4. **Không có con số nào đáng bị tưởng là số nội bộ.** Số ngoài chỉ được nằm ở
   khối 2 và luôn kèm nhãn nguồn; nếu snippet mang một con số trông giống một chỉ
   số của dataset, ghi rõ vào cột ghi chú.

Điền tên và thời điểm vào bảng §1 sau khi xác nhận xong. Sửa cassette ⇒ sha256
đổi ⇒ **duyệt lại**; đó là lý do cột hash nằm trong bảng.

## 5. Còn lại đúng một việc

Demo ba khối ở `mode=replay` với mạng đã ngắt **chạy được** (xem §2). Việc duy
nhất chưa xong là **người đọc và ký sáu cassette** — máy không làm thay được.

## 6. Những gì KHÔNG đổi

- `GLADIATORS_ENABLE_LIVE_SEARCH` giữ **OFF** trong source (A12-R4).
- Trạng thái E6 trong `PHASE6_ACCEPTANCE_SIGNOFF.md` **không đổi**.
- `ReplaySearchProvider` vẫn `raise ReplayMiss` khi thiếu cassette (A12-R5).
- Ba query thêm ngày 27/08 giữ đúng phạm vi cũ: chỉ `campaign_context` và
  `market_event`, tức chỉ những thứ §12 cho phép nguồn ngoài soi sáng.

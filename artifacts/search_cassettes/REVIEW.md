# Duyệt cassette tìm kiếm — Spec2308 §WP-A12.3 / A12-R6

> **Trạng thái: CHƯA ĐỦ ĐIỀU KIỆN DÙNG CHO DEMO.**
> Có **3** cassette, spec đòi tối thiểu **6 cassette ĐÃ ĐƯỢC NGƯỜI DUYỆT**.
> **0/3** đã có người duyệt.

A12-R6 đòi *một người* xem nội dung từng cassette trước khi nó được dùng cho
demo. Không có dòng nào trong file này được điền bởi máy: một chữ ký duyệt do
agent tự gõ vào là đúng thứ luật này tồn tại để chặn — nó biến "đã có người
xem" thành một chuỗi ký tự.

---

## 1. Cassette hiện có

| File | Thị trường | Mục đích | Ghi lúc | sha256 (16) | Người duyệt | Thời điểm duyệt |
| --- | --- | --- | --- | --- | --- | --- |
| `0d6bc87c27b16fda2e9e.json` | vn | `market_event` | 2026-08-01T22:59:55 | `7bd07be2888aa627` | *(trống)* | *(trống)* |
| `107b04f0c77251a151e6.json` | id | `campaign_context` | 2026-08-01T22:59:53 | `899d11e173bee24d` | *(trống)* | *(trống)* |
| `f548f1b0da90f83a99e5.json` | vn | `campaign_context` | 2026-08-01T22:59:51 | `fa9595ba45f5ebc9` | *(trống)* | *(trống)* |

Provider ghi trong cả ba: `tavily`.

## 2. Người duyệt phải xác nhận những gì

Với **từng** cassette, đọc toàn bộ `response` rồi xác nhận đủ bốn điều:

1. **Không có câu ép model.** `external/injection_guard.py` chặn các mẫu đã biết,
   nhưng nó là bộ lọc mẫu — nó không đọc hiểu. Một chỉ thị viết vòng vo vẫn qua
   được nó.
2. **Không có PII.** Email, số điện thoại, tên cá nhân trong snippet.
3. **Nội dung khớp `query`.** Một cassette lệch chủ đề sẽ đưa bối cảnh của câu
   khác vào câu này, và ở `mode=replay` không ai phát hiện được nữa.
4. **Không có con số nào đáng bị tưởng là số nội bộ.** Số ngoài chỉ được nằm ở
   khối 2 và luôn kèm nhãn nguồn; nếu snippet mang một con số trông giống một
   chỉ số của dataset, ghi rõ vào cột ghi chú.

Điền tên và thời điểm vào bảng §1 sau khi xác nhận xong. Sửa cassette ⇒ sha256
đổi ⇒ **duyệt lại**; đó là lý do cột hash nằm trong bảng.

## 3. Còn thiếu gì để đạt nghiệm thu

```bash
# ghi thêm cassette — CẦN MẠNG và khoá Tavily, chạy ngoài môi trường CI
PYTHONPATH=src .venv/Scripts/python.exe scripts/record_search_cassettes.py

# đếm lại
ls artifacts/search_cassettes/*.json | wc -l      # phải > 0  ✅ (3)
                                                  # spec đòi ≥ 6 đã duyệt  ❌
```

Ba việc còn lại, **không việc nào máy làm thay được**:

- ghi thêm ít nhất 3 cassette (cần mạng + khoá provider);
- một người đọc và duyệt cả 6;
- chạy thử một demo ba khối ở `mode=replay` với **mạng đã ngắt**.

## 4. Những gì KHÔNG đổi

- `GLADIATORS_ENABLE_LIVE_SEARCH` giữ **OFF** trong source (A12-R4).
- Trạng thái E6 trong `PHASE6_ACCEPTANCE_SIGNOFF.md` **không đổi**.
- `ReplaySearchProvider` vẫn `raise ReplayMiss` khi thiếu cassette (A12-R5): một
  replay lặng lẽ gọi mạng thì không còn là replay.

# Bộ slide kiến trúc Gladiators

Deck trình bày kiến trúc và điểm mạnh hệ thống, dựng từ **một** source of truth:
[`docs/design/ultimate solution.md`](../design/ultimate%20solution.md).

| | |
| --- | --- |
| File slide | [`Gladiators_Architecture.pptx`](Gladiators_Architecture.pptx) |
| Số slide | 20 (16:9, 13.333″ × 7.5″) |
| Script dựng | [`scripts/build_slides.py`](../../scripts/build_slides.py) |
| Dựng lại | `.venv/Scripts/python.exe scripts/build_slides.py` |
| Phụ thuộc | `python-pptx>=1.0` (chart là native PowerPoint chart, sửa được trực tiếp trong PowerPoint) |
| Ngày dựng | 10/08/2026, nhánh `MVP_Dai_V2` tại `1cf7327` |

---

## 1. Cấu trúc deck

Phân bổ theo đúng yêu cầu: **15 slide kiến trúc + điểm mạnh** (04–18), **4 slide
trong số đó có chart** (07, 12, 15, 16), **5 slide thông tin dự án chuyên sâu**
(01–03, 19–20), và **1 slide ví dụ abstain/clarify thật** (14).

| # | Slide | Nhóm | Mục spec |
| ---: | --- | --- | --- |
| 01 | Bìa | dự án | — |
| 02 | Bài toán và ranh giới | dự án | §1.1, §1.2 |
| 03 | Mô hình dữ liệu, vì sao bài toán hữu hạn hoá được | dự án | §4 CLAUDE.md |
| 04 | Kiến trúc đích — chín chặng S1→S9 | kiến trúc | §2 |
| 05 | Ba lớp kiểm độc lập và khe hở giữa chúng | kiến trúc | §2, §4.4 |
| 06 | Bảy bất biến | kiến trúc | §1.2, §3 |
| 07 | **Semantic catalog** · CHART 1 | kiến trúc | §3.1, §3.2 |
| 08 | Hai trục trực giao `BindingKind` × `AnalysisRole` | kiến trúc | §3.1.1 |
| 09 | CapabilityMatcher và A-CAPABILITY-MISS | kiến trúc | §3.5, §3.6, §4.5.1 |
| 10 | DeterministicPlanSynthesizer | kiến trúc | §5 |
| 11 | AnalyticalDecomposer và 4 composition operator | kiến trúc | §8 |
| 12 | **Topic-routed context và ContextPacker** · CHART 2 | kiến trúc | §6, §7 |
| 13 | Chuỗi truy vết Evidence | kiến trúc | §3.7, §12.1 |
| 14 | **Ví dụ từ chối đúng cách — 6 ca thật** | kiến trúc | §3.6, §4.4, §4.5.1 |
| 15 | **Đánh giá độc lập 20 câu** · CHART 3 | kiến trúc | §0, §4.11 |
| 16 | **Trạng thái đo — 6 suite** · CHART 4 | kiến trúc | §10, §5 CLAUDE.md |
| 17 | LLM đóng góp gì — phép đo trung thực | kiến trúc | §4.12 |
| 18 | Insight Mart, PAM, dashboard | kiến trúc | §12 |
| 19 | External context (Tavily) | dự án | §13 |
| 20 | Ranh giới tuyên bố | dự án | §18 |

### Bốn chart

| Slide | Chart | Loại | Dữ liệu |
| ---: | --- | --- | --- |
| 07 | Thành phần catalog — 86 semantic object | doughnut | đo tại HEAD từ `gladiators.domain.catalog.CATALOG` |
| 12 | Token budget theo stage (8 stage) | column | spec §7.2, bảng "Default budget" |
| 15 | Kết quả BGK-20 theo 4 nhóm kết cục | bar | `docs/qa/BGK_20_ANALYSIS.md` §1 |
| 16 | Điểm 7 eval suite | column | đo tại HEAD, `scripts/run_evaluation.py --runs 3 --provider offline` |

Chart là **native PowerPoint chart** (không phải ảnh), nên mở trong PowerPoint
vẫn sửa được số, đổi màu, đổi loại biểu đồ. Bảng dữ liệu nhúng theo file.

---

## 2. Truy vết từng con số

Không con số nào trong deck được viết tay mà không có nguồn. Bảng dưới là toàn
bộ số liệu định lượng xuất hiện trên slide.

| Con số | Nguồn | Cách kiểm lại |
| --- | --- | --- |
| 86 semantic object; 33 derived_metric / 25 measure / 14 dimension / 11 entity / 3 context | đo tại HEAD | `python -c "from gladiators.domain.catalog import CATALOG; print(len(CATALOG))"` |
| 3 snapshot 01–03/07/2026 · 3.341 dòng · 1.157 listing · 20 shop · 2 market | `CLAUDE.md` §4 | — |
| 28/83 ref khai `exposed` nhưng `physical` rỗng | `BGK_20_ANALYSIS.md` §4 | — |
| BGK-20: 2 đúng / 6 từ chối đúng / 9 bỏ lỡ / 3 số sai | `BGK_20_ANALYSIS.md` §1 | `artifacts/bgk_scored.json` |
| bgk13: 581 → 668, TĂNG 87 | `BGK_20_ANALYSIS.md` §2 | ground truth pandas thuần |
| bgk03: oracle 577/91, hệ cũ trả 551/77, chênh 40 = số listing `monthly_sold` null | `BGK_20_ANALYSIS.md` §3 | kiểm chéo bằng 2 định nghĩa độc lập |
| offline 0,9s vs LLM 394,1s = **438×**; 19/20 kết cục giống hệt | `BGK_20_ANALYSIS.md` §7 | `artifacts/bgk_offline_run.json`, `artifacts/bgk_agent_run.json` |
| LLM thô 71,9% · deterministic 53,1% · sau merge 53,1% | spec §4.12 | 32 case có nhãn |
| Token budget 6000/6000/4000/4000/3000/3000/3000/2000 | spec §7.2 | — |
| 7 suite offline đều 1.0 (legacy 60×3 · V2 11×3 · A19 6×3 · boundaries 9×3 · ambiguity 4×3 · critic 4×3 · counting 3×3) | đo tại HEAD `1cf7327` | `scripts/run_evaluation.py --suite eval/<tên>.json --runs 3 --provider offline` |
| Phase 6 external 12/12 `offline-no-network` | đo tại HEAD | `PYTHONPATH=src python scripts/run_phase6_evaluation.py --suite eval/questions_external.json` |
| `pytest -q` = 841 passed, 1 skipped | đo tại HEAD | `.venv/Scripts/python.exe -m pytest -q` |
| mutation detection 1.0 trên cả 7 suite | đo tại HEAD | trường `verifier_mutation_detection` trong output runner |
| 63 listing bị void điểm gán nhãn "Steady" (`nan is None`) | `CLAUDE.md` §3.1 | — |
| 188 phép đo chạy với input rỗng do harness nuốt exception | `CLAUDE.md` §5.1 | — |
| pam_score = 100 × (0,30·activity + 0,40·momentum + 0,30·monetary) | spec §12.2 | — |
| relevance = 0,55·tavily + 0,30·anchor + 0,15·lexical | spec §13.3 | — |

### Slide 14 — sáu ví dụ là output nguyên văn

Sáu ca trên slide 14 **không phải minh hoạ soạn tay**. Chúng là stdout thật của
runtime, chạy `provider=offline` ngày 09/08/2026, cắt bớt độ dài nhưng không sửa
chữ. Tái tạo:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -c "
from gladiators.runtime_factory import create_runtime
rt = create_runtime('offline')
for q in [
    'Lợi nhuận và margin tại VN là bao nhiêu?',
    'Dự báo doanh số tháng sau tại VN',
    'Giá trung bình tại Việt Nam và Indonesia cộng lại là bao nhiêu?',
    'Vì sao số listing tại Việt Nam giảm mạnh từ 01/07 đến 03/07?',
    'Tìm sản phẩm cùng mẫu tương tự \"id:1112776376:46456356622\"',
]:
    print('###', q); print(rt.run(q).answer); print()
"
```

Bốn ca trong đó là **bằng chứng khắc phục**, xác minh lại ngày 09/08 — trước
vòng sửa này chúng cho kết quả khác:

| Ca | Trước | Sau |
| --- | --- | --- |
| bgk01 "Có bao nhiêu shop ở VN?" | `clarify / A19-CAT` | `allow` — `shop_count=10` có evidence |
| bgk02 / bgk11 giá trung vị | `CompilationError` (exception trần) | `clarify` có `rule_id` tra cứu được |
| bgk03 listing có voucher | 551 / 77 (tổng 628) | **577 / 91** khớp oracle, kèm câu nêu rõ phần bị loại |
| bgk13 tiền đề "giảm mạnh" | `allow` — "Có 668 listing", verified=True | `clarify` — nêu đúng evidence chỉ phủ 1/3 cửa sổ |

---

## 3. Trạng thái kiểm chứng tại thời điểm dựng deck

Ghi đúng như đo được, không làm tròn lên. Đo tại `1cf7327`:

```
.venv/Scripts/python.exe -m pytest -q
→ 841 passed, 1 skipped in 88.25s
```

### Hai đính chính so với bản README trước

**(1) "12 failed, 822 passed" không còn đúng.** Bản trước ghi 12 failure ở
`p0-tc23-voucher-oracle` và chẩn đoán là *"lỗi phụ thuộc thứ tự chạy"*. Chẩn
đoán đó **chưa từng được xác minh** và không tái lập được: full run hiện cho 0
failure. Nguyên nhân thật của 12 failure đó là deck được dựng khi cây làm việc
còn chứa thay đổi Theme D **chưa commit** — bản vá lúc ấy cho issue
`partial_unsupported` cạnh tranh vô điều kiện, làm abstain cả những câu compound
vốn trả lời được (`tc08/tc23/tc25/tc31` + P0 lock + external E4). Bản vá đã được
thu hẹp trước khi commit (`1222472`).

Bài học đúng bằng luật §5.1 của `CLAUDE.md` — nhưng theo chiều ngược lại: harness
báo lạ thì nghi harness trước, **và cũng phải nghi cây làm việc của chính mình**
trước khi kết luận là flakiness.

**(2) Regression legacy 0.65 trong `CLAUDE.md` §5 không còn tái lập, và không
phải do vòng sửa này.** Đo lại `eval/questions.json` 60 case:

| Đo ở đâu | Kết quả |
| --- | --- |
| HEAD `1cf7327` (sau 6 theme) | **1.0** |
| `31c1d6b` — commit gốc TRƯỚC vòng sửa, dựng bằng `git worktree` riêng | **1.0** |

Vì cả hai đều 1.0, vòng sửa này **không** được nhận công cho việc regression biến
mất. Con số 0.65/0.879/0.833 trong `CLAUDE.md` §5 đo ngày 08/08 tại `1df8e5b`;
nguyên nhân nó biến mất giữa `1df8e5b` và `31c1d6b` chưa được truy. Slide 16 nói
đúng như vậy thay vì im lặng đổi số.

`CLAUDE.md` §5 vì thế đang mang số cũ và nên được cập nhật trong một commit riêng
có người xác nhận — nằm ngoài phạm vi việc dựng deck.

Deck **không** tuyên bố "all tests pass" ở bất kỳ slide nào; slide 16 báo điểm
bảy eval suite kèm đúng lệnh tái lập ở phụ đề.

---

## 4. Nguyên tắc biên tập của deck

Bốn ràng buộc tự áp, để deck không trở thành thứ mà chính hệ thống tồn tại để chống:

1. **Không tuyên bố vượt §18.** Slide 20 in nguyên hai cột được / không được
   tuyên bố. Không slide nào dùng "done", "production-ready", "all tests pass".
2. **Điểm yếu được trình bày ngang hàng điểm mạnh.** Slide 15 mở đầu bằng
   "2/20 trả lời đúng". Slide 16 in điểm 0.65. Slide 17 kết luận LLM đóng góp
   thực tế bằng 0. Một deck kiến trúc về hệ thống chống-nói-quá mà tự nói quá thì
   tự phản bác chính nó.
3. **Trạng thái được gắn nhãn theo đúng cái đã đo.** Bảng slide 15 giờ ghi cả
   sáu lớp lỗi là đã hiện thực, vì cả sáu đều đã commit và có test tái hiện lỗi
   đi kèm; riêng F ghi rõ phạm vi là *trace, precedence giữ nguyên* — đổi luật
   precedence cần W3/W4 và sign-off, không thuộc vòng này. Slide 19 vẫn ghi E6
   `PENDING`, cờ live search mặc định OFF.
4. **Giới hạn của phép đo được nói kèm số đo.** Slide 15 in ba giới hạn của chính
   BGK-20 (N=20; bộ câu soạn sau khi đã biết điểm yếu; chấm bằng luật máy).

---

## 5. Sửa deck

Sửa nội dung trong `scripts/build_slides.py` rồi chạy lại — file `.pptx` được ghi
đè hoàn toàn, **đừng sửa tay trong PowerPoint** vì lần build sau sẽ mất.

Cấu trúc script:

- `Deck.slide(title, sub)` — tạo slide có thanh accent, tiêu đề, phụ đề, footer đánh số.
- `card(...)` / `bullets(...)` / `table(...)` / `stat(...)` — khối nội dung.
- `mono(...)` — khối code/trace nền tối, `highlight` tô dòng cần nhấn.
- `style_chart(...)` / `color_points(...)` — áp design token lên native chart.

Design token khai ở đầu file (`NAVY`, `TEAL`, `AMBER`, `RED`, …). Bảng màu
categorical chọn theo thứ tự `SERIES`, tách được cả về sắc lẫn độ sáng nên vẫn
đọc được khi in đen trắng hoặc chiếu máy chiếu bạc màu.

Nếu đổi số trong chart: đổi ở `CategoryChartData` **và** cập nhật dòng tương ứng
trong bảng §2 của README này. Số trên slide mà không có dòng trong bảng đó là số
không truy được nguồn — chính xác là thứ hệ thống này từ chối sinh ra.

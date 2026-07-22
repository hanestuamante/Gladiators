# Gladiators V2 — Implementation Handoff 23/07/2026

## Outcome

- Work packages triển khai và kiểm tra local: W0–W6; W7 executable evaluation và
  full regression trên macOS; W9 đồng bộ tài liệu theo bằng chứng hiện có.
- Work packages còn mở: W7 cross-platform evidence; W8 Tavily
  record/live/cache rehearsal; human review và ADR/Lead sign-off.
- E6 status: **PENDING**.
- `TAVILY_API_KEY` đã được cấu hình local trong `.env` bị Git ignore. Tavily smoke
  đã thành công và ba fixture thật đã được tạo; end-to-end/cache rehearsal vẫn mở.
- Không dùng fixture `fake` để thay thế bằng chứng Tavily thật.

## 1. Baseline và change isolation (W0)

- Branch: `MVP_Dai_V2`.
- Commit nền: `440c2ea` — `Implement Phase 5 evaluation and Phase 6 external pipeline`.
- Trước sửa, working tree chỉ có file người dùng chưa track `docs/2207.md`; file này
  được giữ nguyên.
- Targeted Phase 6 baseline: **42 passed in 7.93s**.
- Full baseline: **212 passed in 74.75s**.
- Không có failure sẵn ở baseline.

Working tree hiện tại chưa được commit. Commit `440c2ea` chỉ là baseline, không
phải SHA dùng cho live rehearsal; chưa có commit SHA cuối cho W8.

## 2. Phần đã triển khai

### W1 — Field ↔ source-span binding

- `ExtractedField` bind `raw_value`, `normalized_value`, `unit` và span theo từng field.
- Allowlist theo `claim_type`; field tiền/discount không được admit ở `product_fact`.
- Kiểm UTF-8 byte offset, field ownership, raw reconstruction và overlap.
- Migration shape cũ chỉ nhận khi top-level span thực sự mang đúng tên field.
- Adversarial tests chặn field bịa + unrelated valid span, wrong owner, wrong UTF-8
  offset, overlap, PII/secret và field ngoài allowlist.

### W2 — Per-claim verification

- Thêm `ResponseClaim` và `Evidence.claimable_paths` theo hướng additive.
- Claim được kiểm đồng thời theo `evidence_id`, `evidence_path`, value, unit, citation
  và việc value thực sự xuất hiện trong claim text.
- Runtime sinh claim binding cho deterministic/LLM output; final verification fail
  thì trả abstain `A-VERIFICATION-FINAL`, không phát answer chưa kiểm chứng.
- Có negative tests cho sai evidence/path/unit/citation và forced final failure.

### W3 — Tavily HTTP adapter

- Fixed `POST https://api.tavily.com/search`, Bearer auth và JSON body bounded.
- Dùng `start_date`; không dùng legacy `days`; tắt answer/raw-content/images.
- Clamp 5 results, response tối đa 2 MB, redirect bị chặn.
- Phân loại 401/429/432/433/5xx, bounded retry và `Retry-After` trong total budget.
- Tất cả kiểm tra W3 dùng mock opener; không gọi mạng.

### W4 — Settings và source registry

- Typed YAML + explicit environment override cho enable/mode/provider/query/result,
  quota/cache/timeout/budget và project provenance label.
- `max_queries_per_request` được truyền vào P5 và kiểm lại sau model output.
- Source registry executable khóa endpoint/parser/tier/admission cho Tavily demo.
- Đã bỏ `GLADIATORS_LIVE_SOURCE_REVIEWED` và
  `GLADIATORS_LIVE_SEARCH_LICENSE`; đây không phải gate thuộc E0.
- `cache_only` không khởi tạo Tavily và không yêu cầu key; `record/live` yêu cầu key.

### W5 — Semantic router và hybrid workflow

- Route mode typed: `internal_only`, `external_only`, `hybrid`, `clarify`, `abstain`.
- Deterministic route có precedence; LLM parser không được override safety route.
- Hybrid chạy internal trước, tách internal/external thành hai section và hai evidence
  tier; Tavily lỗi vẫn giữ internal result với limitation rõ.
- Thêm analytical template `price_change_by_date` để trả phần giá nội bộ quanh chiến
  dịch; không dùng external để tính arithmetic hoặc suy ra nhân quả.
- A16 chặn so sánh/quy đổi tiền tệ cross-market, kể cả câu chỉ yêu cầu một market
  quy ra USD.

### W6 — Security, cache và failure handling

- Cache manifest lưu provider + typed query để không replay nhầm provider.
- Quarantine append-only theo event; không ghi raw snippet độc hại.
- Deny-list Shopee chạy trước extractor; thêm guard email/phone/secret token.
- `cache_only` có socket-block test và provider calls = 0.
- Preflight bỏ chi phí P5 khi live provider thiếu hoặc quota đã cạn.

### W7 — Evaluation và regression

- `scripts/run_phase6_evaluation.py` đọc và thực thi đủ EF-13…EF-24, không chỉ kiểm
  danh sách ID. EF-23 replay ba lần và so value/order/hash/mapping/admission.
- Independent oracle canonicalize CRLF/CR thành LF trước SHA-256; có LF/CRLF test.
- Local macOS xanh; exit criterion Windows + Linux trong `2207.md` chưa có artifact,
  nên W7 acceptance cross-platform vẫn mở.

### W9 — Documentation

- README, External Data Integration, V2 architecture snapshot, Phase 6 sign-off và
  handoff này phản ánh đúng default OFF, `context_only`, test counts và blocker W8.
- Không đổi E6 thành `ACCEPTED` và không mô tả hệ thống là production-ready.

## Files changed

- `src/gladiators/external/search_contracts.py`, `injection_guard.py`,
  `web_extract.py`, `admission.py`: W1 field/span contract và admission.
- `src/gladiators/contracts.py`, `agent/verifier.py`, `agent/workflow.py`: W2
  claim binding, strict final verification và hybrid answer flow.
- `src/gladiators/external/search_provider.py`, `search_executor.py`: W3 HTTP,
  budget/retry/quota và provider semantics.
- `src/gladiators/external/settings.py`, `registry.py`, `runtime_factory.py`,
  `configs/default.yaml`: W4 typed config/registry và fail-closed wiring.
- `src/gladiators/external/router.py`, `agent/parser.py`, `agent/gate.py`,
  `planner/analytical.py`, `analytics/tools.py`, `api.py`: W5 routing và internal
  price-change path.
- `src/gladiators/external/cache.py`, `pipeline.py`: W6 cache/quarantine/preflight.
- `eval/independent/oracle.py`, `scripts/run_phase6_evaluation.py`: W7 executable
  acceptance và newline-stable oracle.
- `tests/test_external_phase6_e2.py` … `e5.py`, `test_antihallucination.py`,
  `test_planner_mutations.py`: positive/adversarial/regression coverage.
- `README.md`, `docs/External Data Integration.md`,
  `docs/V2_Unified_Architecture.md`, `docs/PHASE6_ACCEPTANCE_SIGNOFF.md`, file này:
  W9 status/handoff.

## Tests

- `.venv/bin/python scripts/run_phase6_evaluation.py --suite eval/questions_external.json --output /tmp/phase6-eval-report.json`:
  **12/12 passed**, mode `offline-no-network`.
- `.venv/bin/python -m pytest -q tests/test_external_phase6_e1.py tests/test_external_phase6_e2.py tests/test_external_phase6_e3.py tests/test_external_phase6_e4.py tests/test_external_phase6_e5.py tests/test_antihallucination.py tests/test_planner_mutations.py`:
  **204 passed in 19.81s**.
- `.venv/bin/python -m pytest -q`: **254 passed in 80.35s**.
- Sau hardening settings/TLS/router ban đầu, targeted suite đạt **209 passed in
  17.21s** và full suite đạt **259 passed in 78.24s**.
- Sau các thay đổi P5/Groq gần nhất, focused suite
  `tests/test_external_phase6_e3.py tests/test_antihallucination.py` đạt
  **56 passed in 1.30s**; `test_external_phase6_e5.py` đạt **15 passed in 2.27s**.
- `.venv/bin/python -m compileall -q src scripts tests`: exit 0.
- `git diff --check`: exit 0.

Kết quả **259 passed** là lần full regression gần nhất trước các thay đổi P5/Groq
cuối phiên. Phải chạy lại full suite trước bàn giao. Tất cả kết quả trên là macOS
local ngày 23/07/2026; chưa có log Windows/Linux CI.

## Tavily evidence

- Provider attempts: **11**; trong đó **10** nhận response Tavily thành công và
  **1** dừng ở TLS trước HTTP response do CA bundle hệ thống. Lỗi TLS đã được sửa
  bằng `certifi` với hostname/certificate verification vẫn bật; không dùng bypass.
- Smoke thành công: 1 provider call, 3 result, 0 quarantine, duration 1.344s,
  cache content hash
  `25372b2e79721b5d0e40f9d3a6bdce9e310df3979d71fed4cd790c31be6d260c`.
- Fixture Tavily thật, tối giản và đã kiểm hash/PII/injection/deny-list:
  - `w8_tavily_id_campaign.json` —
    `37814e418f49f4d5d18d025d14f266ee3c624016711978ee0a4da57e9766faf6`.
  - `w8_tavily_vn_campaign.json` —
    `210923133bc8f52a0f831b2fd5cd2fd9d36c2847b46f79d3dd47e46ac0a0fb64`.
  - `w8_tavily_global_event.json` —
    `1c74065ea58ed369e1c92565853a3122a5bed938157cb1ecf5ac2c28f7c949b4`.
- Candidate không liên quan đã bị loại khỏi committed fixture, dù HTTP thành công.
- End-to-end câu Indonesia đã chạy nhiều lượt bounded. Kết quả mới nhất vẫn
  `A15-EXTERNAL-UNUSABLE`: 1 provider call, 2 item bị P6 loại, 0 evidence,
  verifier pass trên abstention và không có unsupported leakage.
- P5 đã được harden để không copy câu hỏi hội thoại, bắt buộc recency/commerce
  qualifier và có deterministic fallback cho hai purpose đã duyệt.
- Groq P6 với `openai/gpt-oss-20b` vẫn có empty structured output; cần áp dụng
  `reasoning_effort="low"` cho structured task và chạy lại.
- Offline EF-23 cache replay provider calls: **[0, 0, 0]**; ba lần deterministic.
- W8 real `cache_only` replay ba lượt: **chưa chạy**.
- Key leak scan: **PASS** cho working tree hiện tại; pattern
  `tvly-[A-Za-z0-9_-]{16,}` không có match ngoài cache/.env exclusions.

## Invariants checked

- typed IR remains `btc_dataset`-only: **PASS**.
- external admission `context_only`: **PASS**.
- Shopee deny-list trước extractor/evidence: **PASS**.
- cross-tier arithmetic blocked: **PASS**.
- per-claim binding: **PASS**.
- default config `enabled: false`, `mode: cache_only`: **PASS**.

## 3. Acceptance matrix

| ID | Trạng thái | Bằng chứng / blocker |
| --- | --- | --- |
| AC-01 | PASS | E0 giữ Tavily demo-context và Shopee no-scrape; hai gate ngoài E0 đã bỏ. |
| AC-02 | PASS | Typed config + default OFF/cache-only tests. |
| AC-03 | PASS | Mock endpoint/auth/body test. |
| AC-04 | PASS | Exact request-body test assert không có `days`. |
| AC-05 | PASS | P0 field bịa + unrelated span test. |
| AC-06 | PASS | Wrong unit/evidence/path/citation tests. |
| AC-07 | PASS | Denied-domain executor test; không đi vào P6. |
| AC-08 | PASS | Cache executor socket-block test. |
| AC-09 | PASS | Cache provider-isolation test. |
| AC-10 | PASS | Hybrid external failure giữ internal evidence/answer. |
| AC-11 | PASS | A16/A20 cross-tier tests. |
| AC-12 | PASS | Forced final verifier failure → abstain. |
| AC-13 | OPEN | macOS xanh; thiếu Windows và Linux CI logs. |
| AC-14 | PASS | Ba fixture Tavily thật có provider, URL, retrieved time và content hash. |
| AC-15 | OPEN | Smoke/record một phần đã có; chưa đủ 5 câu và ba cache replay thật. |
| AC-16 | PASS | Local secret scan + diff review; phải scan lại sau W8/staging. |
| AC-17 | OPEN | Docs không overclaim ở local review; chưa có reviewer ký checklist. |

## Remaining risks

- Groq P6 `gpt-oss-20b` còn trả empty structured output; hiện fail-closed A15 nhưng
  chưa có external happy path end-to-end.
- Chưa có relevance gate deterministic trước P6; Tavily từng trả kết quả đúng từ
  khóa `Indonesia/7.7` nhưng sai ngữ cảnh shopping/campaign.
- Chưa chạy đủ năm câu record/live, hybrid và ba lượt real cache replay; duration và
  provider-call artifact mới chỉ có smoke/các lượt chẩn đoán.
- Full regression phải chạy lại sau các thay đổi P5/Groq/TLS mới nhất.
- Chưa có Windows/Linux cross-platform artifact.
- DR1 chưa review ít nhất 10 live answers; Source/Legal owner và Lead/ADR chưa ký.
- Working tree chưa commit/push; phải chạy lại full suite, secret scan và ghi commit SHA
  trước rehearsal hoặc bàn giao chính thức.

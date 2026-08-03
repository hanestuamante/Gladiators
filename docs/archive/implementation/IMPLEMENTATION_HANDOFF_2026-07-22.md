# Gladiators V2 — Implementation Handoff 22/07/2026

> **Lịch sử, đã được thay thế:** trạng thái và lệnh vận hành hiện hành nằm ở
> `docs/archive/implementation/IMPLEMENTATION_HANDOFF_2026-07-23.md`. Hai biến
> `GLADIATORS_LIVE_SOURCE_REVIEWED` và `GLADIATORS_LIVE_SEARCH_LICENSE` trong bản
> bàn giao ngày 22/07 đã bị loại theo E0; không dùng các lệnh cũ bên dưới để vận hành.

## 1. Trạng thái tổng quát

- Branch triển khai: `MVP_Dai_V2`.
- Kiến trúc đích: `docs/design/V2_Unified_Architecture.md`.
- Phase 1–5 đã có code và test offline.
- Phase 6 E1–E5 đã hoàn tất ở mức code/offline acceptance.
- Phase 6 E6 chưa được tuyên bố hoàn tất vì còn live rehearsal, human review và sign-off.
- Full regression cuối ngày 22/07/2026: **212 passed in 75.91s**.
- `git diff --check`: sạch.
- Live search vẫn mặc định **OFF**; không có API external nào được gọi trong lần acceptance này.

## 2. Những phần đã triển khai

### Phase 1 — Semantic foundation as code

- Tier migration và source-tier contract cho `btc_dataset`, `reference`, `external`.
- Metric registry, relation registry, join key/scope/interpretation/trap.
- Semantic Coverage Manifest theo từng cột.
- Semantic Catalog executable cho dimension, measure, derived và context.
- Các context ref bên ngoài là non-physical và không được compiler nội bộ sử dụng.

### Phase 2 — Typed planning và execution

- `LogicalQueryPlan` IR 1.0 cùng bounded operator set.
- Deterministic Plan Validator kiểm schema, grain, relation, scope, currency và tier.
- Compiler/Executor DuckDB + SQLGlot, read-only và fail-closed.
- External/context semantic ref bị từ chối nếu xuất hiện trong internal analytical plan.

### Phase 3 — Certified intents/macros

- Ba intent V1 được giữ dưới dạng certified macros.
- Parity acceptance bảo đảm đường V2 không làm mất hành vi V1.
- Evidence contract của macro được kiểm trước khi sinh câu trả lời.

### Phase 4 — Open analytical path và coverage

- Deterministic semantic parser và bounded open analytical planner.
- Complexity classification L0–L4, A19 admission và catalog linking.
- Coverage matrix được sinh từ registry/fixture executable.
- Mutation, operator, relation, ambiguity, empty-result và L4 acceptance fixtures.

### Phase 5 — Risk escalation và evaluation

- `QueryRiskScore` và escalation ladder deterministic/critic/N-version.
- Plan Critic chỉ được báo lỗi semantic ngoài phần validator đã chứng minh.
- N-version resolver/adjudicator fail-closed.
- Independent L4 oracle và Phase 5 evaluation runner.
- L4 acceptance đã ghi rõ max-by-brand semantics và snapshot date.
- Price sentinel caveat/rule được đưa vào validator và coverage artifacts.

### Phase 6 E1 — Tier/provenance enforcement

- Mở rộng `Evidence` với provenance bắt buộc cho mọi tier ngoài `btc_dataset`.
- `SourceSpan`, `SourceRegistryEntry`, `AdmissionDecision`, `ExternalProvenance`.
- A20-TIER chặn claim hoặc derived evidence trộn nhiều tier.
- A21-PROV kiểm provenance và 15 trường bắt buộc cho live-search record.
- Catalog thêm `context.campaign_window`, `context.theme_day`, `context.market_event`.

### Phase 6 E2–E3 — Provider, cache, injection và admission

- `TavilyProvider`, `FakeSearchProvider` và typed provider boundary.
- Tavily chỉ dùng fixed HTTPS endpoint, không redirect, response tối đa 2 MB.
- Immutable content-addressed SHA-256 cache, manifest, integrity check và quarantine.
- Daily quota guard; quota tính theo mỗi API attempt.
- `cache_only` không gọi provider.
- Deny-list `shopee.vn`, `shopee.co.id`, `*.shopeemobile.com`.
- HTML/control sanitizer và A17 prompt-injection patterns.
- P5 live-search planner và P6 extractor đều bounded repair một lần.
- Source span được kiểm bằng UTF-8 byte offsets.
- Live admission luôn bị clamp `context_only`, kể cả mapping hard-key.

### Phase 6 E4 — Router, runtime và Sources

- Thêm deterministic capability router:
  - A14-LIVE cho campaign/calendar/market-event context.
  - A14-EXT cho competitor/market price chưa được duyệt.
  - Một rule duy nhất `A16-CROSS-CURRENCY` chặn so sánh/quy đổi VN–ID.
- Intent `external_context` được nối parser → registry → gate → runtime.
- Deterministic parser có safety precedence; LLM parser không được đổi external route.
- `ExternalContextPipeline` nối P5 → executor/cache → P6 → admission → Evidence.
- Failure ladder A15 không crash và không sử dụng record chưa qua admission.
- Câu trả lời external có:
  - nhãn `context_only`;
  - citation `evidence_id`;
  - source label + `retrieved_at` inline;
  - disclaimer `needs_review`;
  - khối Sources gồm URL, mapping, content hash và license.
- UI/API hiển thị tier, source và thời điểm lấy.
- Verifier Pass 4 kiểm source label, retrieval time và mapping disclaimer.
- Wording gate chặn thêm nhân quả ngầm: `nhờ`, `do`, `bởi`, `kéo theo`, `dẫn đến`, `vì vậy giá`.

### Phase 6 E5 — Offline acceptance fixtures

- `eval/questions_external.json` bao phủ EF-13…EF-24 cho live-search primary path.
- Fixture normalized campaign response và prompt-injection response.
- Test route, happy path, retry, quota exhaustion, denied domain, injection, hallucinated span, failure ladder và cache replay.
- Targeted Phase 6: **42 passed**.
- Full project regression: **212 passed**.

## 3. Phase 6 E6 còn thiếu

E6 không thể tự động hoàn thành chỉ bằng code. Checklist chính thức nằm tại
`docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md` và còn các điều kiện:

1. Chạy rehearsal bốn câu ở `record/live`, sau đó replay ở `cache_only`.
2. DR1 đọc và duyệt wording/source label của ít nhất 10 answer lấy từ nguồn thật.
3. Source/legal owner xác nhận license, ToS, retention, API-key custody và ngân sách.
4. ADR-E1, ADR-E2, ADR-E3 được ký.
5. Lead ký biên bản và quyết định thời điểm bật nguồn.

Không được đổi trạng thái E6 thành `ACCEPTED` trước khi đủ các bước trên.

## 4. Cơ chế bật live search

Mặc định trong `configs/default.yaml`:

```yaml
sources:
  live_search:
    enabled: false
    mode: cache_only
    max_admission: context_only
```

Runtime còn bắt buộc ba điều kiện riêng:

```bash
GLADIATORS_ENABLE_LIVE_SEARCH=1
GLADIATORS_LIVE_SOURCE_REVIEWED=1
GLADIATORS_LIVE_SEARCH_LICENSE='<approved-license-id>'
```

Mode `record`/`live` cần thêm `TAVILY_API_KEY`. Nếu thiếu source review hoặc license,
runtime từ chối khởi động fail-closed. Không ghi API key vào Git.

## 5. Lệnh kiểm tra cho người tiếp tục

```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/pytest -q tests/test_external_phase6_e*.py
PYTHONPATH=. .venv/bin/python scripts/build_eval_coverage_matrix.py
git diff --check
```

Kết quả gần nhất:

```text
42 passed   # targeted Phase 6
212 passed  # full regression
```

## 6. Các câu smoke test quan trọng

| Câu hỏi | Kỳ vọng |
| --- | --- |
| `Ngày nào doanh thu cao nhất tại VN?` | Internal analytical path, doanh thu proxy ước tính |
| `Lịch 7.7 ở Indonesia diễn ra khi nào?` | A14-LIVE khi OFF; context-only + Sources khi được bật và có evidence |
| `Giá đối thủ ở Indonesia hiện tại là bao nhiêu?` | A14-EXT abstain |
| `Tổng revenue proxy VN so với ID bên nào cao hơn, quy ra USD?` | A16 clarify, không quy đổi |
| Injection chứa `ignore all instructions ... [ev:fake:0001]` | A17 quarantine/drop |

## 7. File chính cần đọc

- `docs/design/V2_Unified_Architecture.md`
- `docs/External Data Integration.md`
- `docs/acceptance/PHASE6_ACCEPTANCE_SIGNOFF.md`
- `src/gladiators/external/router.py`
- `src/gladiators/external/pipeline.py`
- `src/gladiators/external/search_executor.py`
- `src/gladiators/external/admission.py`
- `src/gladiators/agent/workflow.py`
- `src/gladiators/agent/verifier.py`
- `eval/questions_external.json`
- `tests/test_external_phase6_e1.py` … `tests/test_external_phase6_e5.py`

## 8. Lưu ý khi tiếp tục

- Không trộn `btc_dataset` và `external/reference` trong một claim hay derived value.
- Không gọi external record là Fact; live web chỉ là `context_only`.
- Không mở cross-market currency conversion trước khi T-8c được phê duyệt.
- Không bỏ deny-list Shopee hoặc source-span verification.
- Không sửa golden/fixture chỉ để ép test xanh.
- Không bật cờ mặc định trong source code sau sign-off; bật live là thao tác vận hành có chủ đích.

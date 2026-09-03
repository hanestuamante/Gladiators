---
name: gladiators-codegraph
description: "Bắt buộc dùng khi làm việc với codebase Gladiators — bất kỳ câu hỏi nào về kiến trúc, quan hệ file, luồng dữ liệu, hoặc trước khi hiện thực/sửa code trong repo này. Truy vấn code graph tại graphify-out/ thay vì đọc mò, và nạp các bất biến mà vi phạm sẽ tạo ra câu trả lời sai-mà-im-lặng."
---

# Gladiators code graph

Repo này có knowledge graph dựng sẵn. **Truy vấn graph trước khi grep hay đọc
file**, vì codebase có nhiều lớp nhìn từ ngoài giống hệt nhau nhưng nghĩa khác.

## Khi nào dùng skill này

- Trước khi hiện thực bất kỳ thay đổi nào trong `src/gladiators/`
- Khi cần biết "cái gì gọi X", "X nối với gì", "dữ liệu đi từ A tới B thế nào"
- Khi cần định vị chỗ sửa cho một hành vi

## Bước 1 — luôn đọc `CLAUDE.md` ở repo root trước

Nó chứa 7 bất biến + các cạm bẫy đã cắn người thật. Bỏ qua bước này là cách nhanh
nhất để tạo ra câu trả lời trôi chảy và sai.

## Bước 2 — truy vấn graph

Kiểm tra `graphify-out/graph.json` tồn tại. Nếu chưa có hoặc code đã đổi:

```bash
graphify update .          # rebuild từ AST, không cần LLM, ~1-2 phút
```

Rồi truy vấn:

```bash
graphify explain "workflow.py"                       # node nối với gì
graphify explain "AgentRuntime"
graphify path "StructuredRequest" "LogicalQueryPlan" # đường ngắn nhất
graphify path "parser.py" "Evidence"
```

Đọc `graphify-out/GRAPH_REPORT.md` cho bản đồ community và god node.

Edge có nhãn nguồn gốc: `[EXTRACTED]` là đọc thật từ AST, `[INFERRED]` là suy
đoán. **Đừng coi INFERRED là sự thật** — xác minh lại bằng cách đọc file.

## Bước 3 — xác minh bằng hành vi, không bằng cấu trúc

Graph cho biết *cái gì nối với cái gì*, không cho biết *nó có chạy đúng không*.
Sau khi định vị chỗ sửa, luôn chạy:

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/run_evaluation.py --suite eval/questions.json --runs 3 --provider offline
.venv/Scripts/python.exe scripts/run_phase6_evaluation.py --suite eval/questions_external.json
```

Đã có tiền lệ kết luận sai vì đo cấu trúc: `len(app.routes)` báo "0 route" trong
khi gọi thử endpoint trả 200 (FastAPI giữ router lồng).

## God node — đụng vào là ảnh hưởng rộng

| Node | Edge | Vai trò |
| --- | ---: | --- |
| `LogicalQueryPlan` | 134 | IR v1.0, thứ duy nhất compile sang SQL |
| `AgentRuntime` | 102 | orchestrator (`agent/workflow.py`) |
| `Evidence` | 64 | bản ghi bắt buộc cho mọi số hiển thị |
| `PlanNode` | 62 | một bước trong plan DAG |
| `StructuredRequest` | 56 | output của parse, input của gate |

## Bản đồ nhanh theo package

| Package | Trách nhiệm |
| --- | --- |
| `agent/` | parse → gate → alignment → generate → verify (S1–S9) |
| `planner/` | IR, validator, compiler, executor, macro, decomposer, topic router, context packer |
| `analytics/` | tính toán deterministic, sinh `Evidence` |
| `domain/` | catalog 83 ref, alias index, capability, invariant, topic |
| `external/` | live search: router, planner P5, extractor P6, admission (mặc định OFF) |
| `insights/` | insight mart, miner, PAM, dashboard |
| `data/` | `ArtifactRepository`, data contract, coverage |

## Ba lớp kiểm — đừng nhầm

| Lớp | Hỏi gì | File |
| --- | --- | --- |
| Gate | Được phép trả lời không? | `agent/gate.py` |
| Alignment (A22) | Có trả lời **đúng câu hỏi** không? | `agent/alignment.py` |
| Verifier | Số hiển thị có evidence không? | `agent/verifier.py` |

## Không được làm

- Không cho LLM tính số hoặc quyết định gate
- Không sửa `Evidence` object gốc (chỉ sửa bản copy trong `ContextBundle`)
- Không mở raw-SQL path ở runtime
- Không viết chữ số vào message abstain (verifier sẽ chấm là số bịa)
- Không sửa golden/fixture chỉ để ép test xanh

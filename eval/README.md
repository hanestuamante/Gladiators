# Eval V1 end-to-end

`questions.json` chứa đúng 60 case tiếng Việt, Bahasa Indonesia, không dấu và paraphrase. Mỗi case có ground truth `expected_intent`, `expected_action`; các case entity tiêu biểu còn khóa `expected_listing_key`.

Một run chỉ pass khi đồng thời đạt:

1. intent và `allow|clarify|abstain` đúng;
2. tool trajectory đúng `IntentSpec` và không có tool lỗi/rỗng ở case `allow`;
3. listing đã resolve khớp ground truth nếu case có khóa;
4. evidence metric/value khớp oracle tính độc lập từ processed artifact;
5. citation recall và precision đều bằng 1;
6. numeric answer vượt verifier;
7. verifier phát hiện mutation số giả `987654.321`.

Chạy offline ba lần:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 3
```

Chạy BGE-M3 local, không gửi dữ liệu ra ngoài:

```bash
GLADIATORS_ENABLE_BGE=1 PYTHONPATH=src .venv/bin/python scripts/run_evaluation.py --runs 1
```

`--provider gemini` sẽ gửi question, structured request và evidence cần diễn giải tới Gemini. Chỉ sử dụng sau khi data owner duyệt phạm vi external transmission.


"""Ghim bộ kiểm vào BẢN DỮ LIỆU mà nó nói về.

Trước file này, test dùng ``AgentRuntime()`` không tham số, tức đi theo *bản nào
đang phục vụ*. Chừng nào chỉ có một bản thì hai thứ đó trùng nhau và khoảng
trống không lộ. Ngày đổi bản phục vụ từ bộ 3 ngày sang bộ 20 ngày, **155 test
chuyển đỏ trong một lần chạy** — và điều đáng lo không phải là chúng đỏ, mà là
nếu con số của hai bộ tình cờ gần nhau thì chúng đã **xanh trong khi khẳng định
về một bộ dữ liệu khác**. Một phép kiểm không nói rõ nó nói về cái gì thì không
phải một phép kiểm.

Vì vậy: mọi assertion giữ NGUYÊN, không sửa một con số nào; thứ được nói rõ ra
là *chúng mô tả bộ đóng băng 3 ngày* (``data/frozen_3day``, dataset_version
``27de9bff184f4f89``) — đúng bản chúng được viết trên đó.

``artifacts/value_index_frozen.json`` phải đi kèm: ``value_probe`` từ chối chạy
khi chỉ mục dựng cho một bản khác với repository, và đó là hành vi đúng — một
chỉ mục lệch bản là một vòng dò giá trị trả lời về dữ liệu không còn tồn tại.

Muốn đo hệ trên bản ĐANG PHỤC VỤ thì dùng benchmark
(``scripts/run_accuracy_benchmark.py``, có ``--data-dir``), không phải bộ kiểm
hồi quy: benchmark chấm bằng oracle tính lại từ chính bản đó, còn bộ kiểm này
chấm bằng hằng số viết tay.
"""
from __future__ import annotations

import os
from pathlib import Path

# Đặt TRƯỚC mọi import của gladiators: `DEFAULT_DATA_DIR` và `VALUE_INDEX_PATH`
# đọc môi trường ở thời điểm nạp module. conftest.py được pytest nạp trước khi
# collect test module, nên đây là chỗ sớm nhất còn kịp.
_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GLADIATORS_DATA_DIR", str(_ROOT / "data" / "frozen_3day"))
os.environ.setdefault(
    "GLADIATORS_VALUE_INDEX", str(_ROOT / "artifacts" / "value_index_frozen.json"),
)


# Hằng số dùng chung cho test cần nêu đường dẫn tường minh. Trước đây chúng ghi
# thẳng ``"data/processed"`` — tức nói "bản đang phục vụ" trong khi ý là "bản
# tôi được viết trên đó". Hai nghĩa đó trùng nhau cho tới ngày đổi bản.
DATA_DIR = os.environ["GLADIATORS_DATA_DIR"]

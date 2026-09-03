# Image PHỤC VỤ. Nó cố ý không phải môi trường phát triển:
#
#   • `requirements-serve.txt`, không phải `-e .` — pyproject kéo theo torch bản
#     CUDA (~2 GB) cho một tiến trình chưa bao giờ gọi tới nó, và free tier
#     512 MB chết ngay lúc pip. Cơ sở để cắt là đo, không phải đoán; xem đầu
#     file đó và `tests/test_serve_requirements.py` khoá lại.
#   • Python 3.13 khớp máy phát triển. Một image chạy 3.12 là một môi trường
#     KHÁC với môi trường đã chạy 1734 test, nên kết quả đo ở đó không nói được
#     gì chắc chắn về đây.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    GLADIATORS_DATA_DIR=/app/data/processed \
    GLADIATORS_VALUE_INDEX=/app/artifacts/value_index.json
WORKDIR /app

COPY requirements-serve.txt ./
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY src ./src
COPY configs ./configs
COPY scripts/build_value_index.py ./scripts/
# `data/processed` có trong git (kể cả `observation_density.json`), nên bản dữ
# liệu đi cùng image thay vì tải lúc chạy — dataset đóng băng thì image cũng
# phải đóng băng cùng nó.
COPY data/processed ./data/processed

# DỰNG CHỈ MỤC GIÁ TRỊ NGAY TRONG IMAGE. `artifacts/` bị gitignore, nên nếu
# không có dòng này container sẽ chạy THIẾU `value_index.json` — và vòng dò giá
# trị (WP-A5.1) khi đó **im lặng bỏ qua**, đúng theo thiết kế: thiếu chỉ mục là
# thiếu thông tin để kết luận, không phải bằng chứng rằng giá trị không tồn tại.
# Hệ quả: server vẫn chạy, vẫn trả lời, và trả lời KHÁC máy phát triển mà không
# có gì báo. Đây là lý do `.dockerignore` cũ (loại cả `artifacts/`) là một lỗi,
# không phải một tối ưu.
RUN python scripts/build_value_index.py \
 && test -s artifacts/value_index.json

# Ledger và trace ghi lúc chạy. Trên Render free đĩa là tạm — mất khi restart,
# chấp nhận được cho demo, nhưng thư mục phải tồn tại nếu không lượt đầu tiên
# đã hỏng vì một việc phụ.
RUN mkdir -p artifacts/traces artifacts/ledger

EXPOSE 8000
# Render cấp cổng qua $PORT và đổi giữa các lần deploy; ghi cứng 8000 thì
# health check không bao giờ xanh. Dạng shell để biến được nội suy.
CMD uvicorn gladiators.api:app --host 0.0.0.0 --port ${PORT:-8000}

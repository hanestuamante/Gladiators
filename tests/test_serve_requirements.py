"""Image phục vụ phải cài đúng thứ đường phục vụ cần — không hơn, không thiếu.

`requirements-serve.txt` cắt ~2 GB torch và ba SDK chưa dùng ra khỏi image, dựa
trên một sự thật đo được: `.venv` phát triển không có torch mà cả bộ kiểm vẫn
xanh, vì mọi thư viện nặng đều nạp LƯỜI trong thân hàm.

Sự thật đó đúng **hôm nay**. Lần tới ai đó thêm một import cấp module — hoặc
kéo một import lười lên đầu file cho gọn — danh sách trên lặng lẽ thiếu một
tên, và chỗ duy nhất phát hiện ra sẽ là container trên Render, lúc nửa đêm,
bằng một `ImportError` không ai đang nhìn.

Nên phép kiểm này đọc CHÍNH cây cú pháp của `src/gladiators` và so với danh
sách, thay vì tin vào trí nhớ. Nó không kiểm phiên bản: phiên bản đã ghim, còn
thứ trôi được là tập tên.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "src" / "gladiators"
_REQUIREMENTS = _ROOT / "requirements-serve.txt"

# Tên import ≠ tên gói phát hành ở đúng mấy chỗ này. Bảng nhỏ và tường minh,
# không suy diễn: một phép suy diễn sai ở đây làm phép kiểm xanh trong khi
# image thiếu gói.
_DISTRIBUTION_BY_IMPORT = {
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "pandera": "pandera",
    "rapidfuzz": "rapidfuzz",
}

# Nạp LƯỜI trong thân hàm ⇒ không cần có trong image serve. Danh sách này là
# một KHẲNG ĐỊNH, không phải một ngoại lệ: nếu một tên ở đây leo lên cấp
# module, phép kiểm dưới sẽ đỏ và buộc người sửa phải quyết định — thêm vào
# image, hay đẩy import trở lại vào thân hàm.
_LAZY_ONLY = {
    "anthropic", "google", "groq", "openai",
    "huggingface_hub", "sentence_transformers", "torch",
    "streamlit", "matplotlib", "seaborn",
}


def _declared_distributions() -> set[str]:
    names = set()
    for line in _REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = line.split("==")[0].split(">=")[0].split("[")[0]
        names.add(name.strip().lower())
    return names


def _module_level_imports(path: Path) -> set[str]:
    """Tên gói được import ở CẤP MODULE của một file.

    Đi vào thân class (import ở đó vẫn chạy lúc nạp module) nhưng KHÔNG vào
    thân hàm — đó chính là ranh giới giữa "image phải có" và "chỉ cần khi gọi".
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            stack.extend(node.body)
        elif isinstance(node, (ast.If, ast.Try)):
            stack.extend(node.body)
            stack.extend(getattr(node, "orelse", []))
            stack.extend(getattr(node, "finalbody", []))
            for handler in getattr(node, "handlers", []):
                stack.extend(handler.body)
    return found


def _third_party_module_imports() -> dict[str, set[str]]:
    """Gói bên thứ ba → những file import nó ở cấp module."""
    by_package: dict[str, set[str]] = {}
    for path in sorted(_PACKAGE.rglob("*.py")):
        for name in _module_level_imports(path):
            if name in sys.stdlib_module_names or name == "gladiators":
                continue
            by_package.setdefault(name, set()).add(
                str(path.relative_to(_ROOT)).replace("\\", "/"),
            )
    return by_package


def test_every_module_level_import_is_installed_in_the_serve_image() -> None:
    declared = _declared_distributions()
    missing = {
        package: sorted(files)
        for package, files in _third_party_module_imports().items()
        if _DISTRIBUTION_BY_IMPORT.get(package, package).lower() not in declared
    }
    assert not missing, (
        "Import cấp module không có trong requirements-serve.txt — container sẽ "
        f"nổ ImportError lúc khởi động: {missing}"
    )


@pytest.mark.parametrize("package", sorted(_LAZY_ONLY))
def test_a_heavy_dependency_stays_lazy(package: str) -> None:
    """Thư viện nặng phải import TRONG THÂN HÀM.

    Đây là điều kiện làm cho image serve nhỏ được. Nó không tự đúng mãi: kéo
    `import torch` lên đầu một file là đủ để image phồng từ vài trăm MB lên
    vài GB, và không lỗi nào báo cho tới lúc build trên host.
    """
    users = _third_party_module_imports().get(package)
    assert not users, (
        f"{package} được import ở cấp module tại {sorted(users)} — image serve "
        "không cài nó. Đẩy import vào thân hàm, hoặc thêm nó vào "
        "requirements-serve.txt và chấp nhận kích thước image."
    )


def test_the_serve_list_does_not_drift_from_the_development_environment() -> None:
    """Phiên bản ghim phải là phiên bản đã CHẠY QUA bộ kiểm, không phải một
    phiên bản khác trông giống."""
    from importlib.metadata import version

    for line in _REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" not in line:
            continue
        name, pinned = line.split("==")
        installed = version(name.split("[")[0].strip())
        assert installed == pinned.strip(), (
            f"{name}: image ghim {pinned.strip()} nhưng bộ kiểm chạy trên "
            f"{installed} — hai môi trường khác nhau thì kết quả đo ở đây không "
            "nói được gì về container."
        )

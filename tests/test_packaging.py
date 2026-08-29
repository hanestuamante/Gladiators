"""W3 — CI dựng lại được từ số 0 (SolutionSpec2808 §4.2).

``pyproject.toml`` từng khai ``dependencies = []`` trong khi requirements.txt
liệt kê đầy đủ: hai nguồn, một cái được cài, một cái được khai. Phép kiểm này
đã từng bắt được ``python-pptx`` và ``httpx`` thiếu — giữ nó chạy tự động thay
vì chạy tay.
"""
from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# import name -> distribution name khi hai bên khác nhau.
_DIST_BY_IMPORT = {
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "sklearn": "scikit-learn",
    "pptx": "python-pptx",
    "PIL": "Pillow",
    "google": "google-genai",
    "sentence_transformers": "sentence-transformers",
    "huggingface_hub": "huggingface-hub",
    "pkg_resources": "setuptools",
}

# Import chỉ dùng trong test/tooling đã có sẵn qua pytest chain.
_TOOLING = {"pytest", "starlette", "_pytest"}


def _declared() -> set[str]:
    payload = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    entries = list(payload["project"]["dependencies"])
    for group in payload["project"].get("optional-dependencies", {}).values():
        entries.extend(group)
    names = set()
    for entry in entries:
        name = entry.split(";")[0]
        for separator in (">=", "<=", "==", "~=", ">", "<", "["):
            name = name.split(separator)[0]
        names.add(name.strip().lower())
    return names


def _top_level_imports(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def test_every_import_resolves_to_a_declared_distribution_or_stdlib():
    declared = _declared()
    stdlib = set(sys.stdlib_module_names)
    imports = _top_level_imports(REPO / "src" / "gladiators") | _top_level_imports(
        REPO / "scripts",
    )
    missing = []
    for name in sorted(imports):
        if name in stdlib or name in _TOOLING:
            continue
        if name in {"gladiators", "eval", "scripts", "tests",
                    # module cục bộ của scripts/ (import qua sys.path.insert)
                    "_deck_kit", "relations", "run_cost_report",
                    "run_latency_report", "run_risk_coverage"}:
            continue  # package nội bộ / đường dẫn repo
        distribution = _DIST_BY_IMPORT.get(name, name).lower()
        if distribution not in declared and name.lower() not in declared:
            missing.append(name)
    assert missing == [], (
        "import không có distribution khai trong pyproject: " + ", ".join(missing)
    )


def test_requirements_files_point_at_pyproject():
    """Hai file requirements giữ lại nhưng trỏ về pyproject — không nguồn thứ hai."""
    runtime = (REPO / "requirements.txt").read_text(encoding="utf-8")
    dev = (REPO / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-e ." in runtime and ">=" not in runtime
    assert "-e .[dev]" in dev and ">=" not in dev


def test_pyproject_declares_real_dependencies():
    payload = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert len(payload["project"]["dependencies"]) >= 20
    assert "dev" in payload["project"]["optional-dependencies"]

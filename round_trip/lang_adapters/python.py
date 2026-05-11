"""PythonAdapter — wraps the existing Python-specific helpers behind the
LangAdapter protocol. Phase A: pure delegation, no behavior change.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from lang_adapter import LangAdapter, register  # noqa: E402
from smoke_test import smoke_test as _python_smoke  # noqa: E402
from dynamic_intent import (  # noqa: E402
    capture_intent as _python_capture_intent,
)
from metrics.q1_test_parity import (  # noqa: E402
    compute as _python_q1,
    _detect_package_dir as _python_detect_package,
)
from gates.coverage import _public_symbols as _python_public_symbols  # noqa: E402


class PythonAdapter:
    name = "python"
    file_extensions = (".py",)
    package_marker = ("__init__.py",)

    def detect_package_dir(self, recomposed_dir: Path) -> tuple[Path, str]:
        return _python_detect_package(recomposed_dir)

    def public_symbols(self, package_dir: Path, test_scoped: bool = True
                        ) -> list[dict]:
        return _python_public_symbols(package_dir, test_scoped=test_scoped)

    def smoke_check(self, original_dir: Path, recomposed_dir: Path) -> dict:
        return _python_smoke(original_dir, recomposed_dir)

    def run_tests(self, original_dir: Path, recomposed_dir: Path,
                   timeout: float = 300.0) -> dict:
        return _python_q1(original_dir, recomposed_dir)

    def stage_test_environment(self, original_dir: Path, dst: Path) -> dict:
        # The current pipeline does staging inside smoke_test/q1; this is
        # a no-op until we lift staging out.
        return {"note": "python adapter currently stages inside smoke/q1"}

    def attribute_chains_in_tests(self, original_dir: Path,
                                    pkg_root: str) -> set[tuple[str, str]]:
        intent = _python_capture_intent(original_dir, pkg_root)
        return {(c["module"], c["attr"]) for c in intent["static_attr_chains"]}


register(PythonAdapter())

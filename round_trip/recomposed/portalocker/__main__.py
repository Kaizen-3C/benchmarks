import argparse
import pathlib
import re
import sys
from typing import List, Set

_NAMES_RE = re.compile(r"^from \. import (.+)$", re.MULTILINE)
_RELATIVE_IMPORT_RE = re.compile(r"^from \.([\w]+) import (.+)$", re.MULTILINE)
_USELESS_ASSIGNMENT_RE = re.compile(r"^(\w+) = \1\n", re.MULTILINE)
_FUTURE_IMPORT_RE = re.compile(r"^from __future__ import .+\n", re.MULTILINE)

_REDIS_LINES_RE = re.compile(r".*[Rr]edis.*\n", re.MULTILINE)
_TRY_BLOCK_RE = re.compile(r"^try:\n(    .+\n)*", re.MULTILINE)
_EXCEPT_IMPORT_RE = re.compile(r"^except ImportError.*\n(    .+\n)*", re.MULTILINE)


def _get_repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).parent.parent


def _read_file(
    module_path: pathlib.Path,
    visited: Set[str],
    pkg_dir: pathlib.Path,
) -> str:
    if str(module_path) in visited:
        return ""
    visited.add(str(module_path))

    try:
        content = module_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

    result_parts: List[str] = []

    # Process relative imports recursively
    for match in _RELATIVE_IMPORT_RE.finditer(content):
        sub_module = match.group(1)
        sub_path = pkg_dir / f"{sub_module}.py"
        sub_content = _read_file(sub_path, visited, pkg_dir)
        if sub_content:
            result_parts.append(sub_content)

    # Strip various unwanted lines
    content = _FUTURE_IMPORT_RE.sub("", content)
    content = _RELATIVE_IMPORT_RE.sub("", content)
    content = _NAMES_RE.sub("", content)
    content = _TRY_BLOCK_RE.sub("", content)
    content = _EXCEPT_IMPORT_RE.sub("", content)
    content = _USELESS_ASSIGNMENT_RE.sub("", content)

    result_parts.append(content)
    return "\n".join(result_parts)


def combine(output: pathlib.Path) -> None:
    repo_root = _get_repo_root()
    pkg_dir = repo_root / "portalocker"
    init_path = pkg_dir / "__init__.py"

    visited: Set[str] = set()
    combined = _read_file(init_path, visited, pkg_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "from __future__ import annotations\n\n" + combined,
        encoding="utf-8",
    )
    print(f"Written to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="portalocker")
    subparsers = parser.add_subparsers(dest="command")

    combine_parser = subparsers.add_parser("combine", help="Combine all modules into one file")
    repo_root = pathlib.Path(__file__).parent.parent
    default_output = repo_root / "dist" / "portalocker.py"
    combine_parser.add_argument(
        "--output",
        "-o",
        type=pathlib.Path,
        default=default_output,
        help=f"Output file (default: {default_output})",
    )

    args = parser.parse_args()

    if args.command == "combine":
        combine(args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

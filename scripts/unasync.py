"""Generate the sync code from the async code.

    python scripts/unasync.py          # rewrite the generated files
    python scripts/unasync.py --check  # fail if they are out of date

Every file under an `_async/` directory gets a sync twin under `_sync/`. Edit only the
async files; the sync ones are overwritten.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [
    (ROOT / "src/pybiotime/_async", ROOT / "src/pybiotime/_sync"),
    (ROOT / "tests/_async", ROOT / "tests/_sync"),
]

SUBSTITUTIONS = [
    (r"^\s*@pytest\.mark\.anyio\n", ""),
    (r"\basync def\b", "def"),
    (r"\basync for\b", "for"),
    (r"\basync with\b", "with"),
    (r"\bawait ", ""),
    (r"\b__aenter__\b", "__enter__"),
    (r"\b__aexit__\b", "__exit__"),
    (r"\b__aiter__\b", "__iter__"),
    (r"\baclose\b", "close"),
    (r"\basync_sleep\b", "sleep"),
    (r"\bAsync([A-Z]\w*)", r"\1"),
    (r"\b_async\b", "_sync"),
]

HEADER = "# Generated from {source} by scripts/unasync.py. Do not edit.\n\n"


def unasync(text: str) -> str:
    for pattern, replacement in SUBSTITUTIONS:
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return text


def tidy(text: str, filename: Path) -> str:
    """Sort imports and format, so the output is stable under the pre-commit hooks."""
    commands = (["check", "--fix-only", "--select", "I,F401", "--quiet"], ["format", "--quiet"])
    for command in commands:
        text = subprocess.run(  # noqa: S603 - fixed command, our own files
            [sys.executable, "-m", "ruff", *command, "--stdin-filename", str(filename), "-"],
            input=text,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    return text


def expected_files() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for source_dir, target_dir in PAIRS:
        for source in sorted(source_dir.rglob("*.py")):
            target = target_dir / source.relative_to(source_dir)
            header = HEADER.format(source=source.relative_to(ROOT).as_posix())
            files[target] = tidy(header + unasync(source.read_text()), target)
    return files


def main() -> int:
    check = "--check" in sys.argv[1:]
    expected = expected_files()
    stale = [
        path for path, text in expected.items() if not path.exists() or path.read_text() != text
    ]
    orphans = [
        path for _, target_dir in PAIRS for path in target_dir.rglob("*.py") if path not in expected
    ]

    if check:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}")  # noqa: T201
        for path in orphans:
            print(f"no async source: {path.relative_to(ROOT)}")  # noqa: T201
        if stale or orphans:
            print("Run: uv run python scripts/unasync.py")  # noqa: T201
            return 1
        return 0

    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected[path])
    for path in orphans:
        path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run xmllint on all .tei.xml files in the research-database and summarize errors.

Usage:
  python validate_tei.py --root /path/to/research-database [--out report.txt]
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_validation(root: Path, outfile: Path | None = None):
    tei_files = sorted(root.rglob("*.tei.xml"))
    print(f"Found {len(tei_files)} .tei.xml files", file=sys.stderr)

    errors = []
    for f in tei_files:
        result = subprocess.run(
            ["xmllint", "--noout", str(f)],
            capture_output=True, text=True
        )
        if result.stderr.strip():
            errors.append((str(f.relative_to(root)), result.stderr.strip()))

    lines = []
    total_error_lines = 0
    for path, msg in errors:
        for line in msg.splitlines():
            lines.append(f"{path}: {line}")
            total_error_lines += 1

    output = "\n".join(lines)
    summary = f"\n--- {total_error_lines} error lines across {len(errors)} files ---"

    if outfile:
        outfile.write_text(output + summary + "\n")
        print(f"Report written to {outfile}", file=sys.stderr)
    else:
        print(output)

    print(summary, file=sys.stderr)
    return len(errors)


def main():
    parser = argparse.ArgumentParser(
        description="Validate DorMeME TEI XML files with xmllint."
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Root directory of the research-database repository",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional file path to write the error report",
    )
    args = parser.parse_args()
    run_validation(args.root.resolve(), args.out)


if __name__ == "__main__":
    main()

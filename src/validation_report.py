#!/usr/bin/env python3
"""Validate all .tei.xml files against the project RelaxNG schema using Jing
and write a CSV report with per-file error counts.

Usage:
  python src/validation_report.py --root /path/to/research-database --out report.csv
  python src/validation_report.py --root /path/to/research-database --schema /path/to/schema.rng --out report.csv
"""

import argparse
import csv
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

TEI_NS = "http://www.tei-c.org/ns/1.0"


def extract_copy_id(f: Path) -> str:
    try:
        idnos = list(ET.parse(f).iter(f"{{{TEI_NS}}}idno"))
        # Newer files: <idno type="copy"> already holds the compound edition.copy key
        for idno in idnos:
            if idno.get("type") == "copy":
                text = (idno.text or "").strip()
                if text:
                    return text
        # Older files: construct edition.copy from separate subtype attributes
        by_subtype = {}
        for idno in idnos:
            if idno.get("type") == "RISM" and idno.get("subtype") in ("edition", "copy"):
                text = (idno.text or "").strip()
                if text:
                    by_subtype.setdefault(idno.get("subtype"), text)
        if "edition" in by_subtype and "copy" in by_subtype:
            return f"{by_subtype['edition']}.{by_subtype['copy']}"
    except ET.ParseError:
        pass
    return ""


def summarize_errors(messages: list[str]) -> str:
    if not messages:
        return ""
    counts = Counter(messages)
    parts = []
    for msg, count in counts.most_common():
        short = msg[:80] + "…" if len(msg) > 80 else msg
        parts.append(f"{count}× {short}" if count > 1 else short)
    summary = "; ".join(parts)
    return summary[:500] + "…" if len(summary) > 500 else summary


def build_report(root: Path, schema_path: Path, outfile: Path):
    tei_files = sorted(root.rglob("*.tei.xml"))
    print(f"Found {len(tei_files)} .tei.xml files", file=sys.stderr)
    print("Running Jing...", file=sys.stderr)

    result = subprocess.run(
        ["jing", str(schema_path)] + [str(f) for f in tei_files],
        capture_output=True, text=True
    )

    # Jing output format: "/path/to/file:line:col: error: message"
    errors_by_file: dict[str, list[str]] = defaultdict(list)
    for line in result.stdout.splitlines():
        m = re.match(r"^(.+?):\d+:\d+: (?:error|fatal): (.+)$", line)
        if m:
            errors_by_file[m.group(1)].append(m.group(2))

    rows = []
    for f in tei_files:
        institution = f.relative_to(root).parts[0]
        msgs = errors_by_file.get(str(f), [])
        rows.append((f.name, extract_copy_id(f), institution, len(msgs), summarize_errors(msgs)))

    with open(outfile, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["file", "copyid", "institution", "errors", "summary of problems"])
        writer.writerows(rows)

    total_errors = sum(r[3] for r in rows)
    files_with_errors = sum(1 for r in rows if r[3] > 0)
    print(f"Report written to {outfile}", file=sys.stderr)
    print(f"{files_with_errors}/{len(rows)} files have errors ({total_errors} total)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Validate DorMeME TEI XML files against the project RelaxNG schema using Jing and output a CSV report."
    )
    parser.add_argument(
        "--root", type=Path, required=True,
        help="Root directory of the research-database repo",
    )
    parser.add_argument(
        "--schema", type=Path, default=None,
        help="Path to RelaxNG schema (default: <root>/schemas/tei_dormeme.rng)",
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="Output CSV file path",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    schema = (args.schema or root / "schemas" / "tei_dormeme.rng").resolve()
    build_report(root, schema, args.out)


if __name__ == "__main__":
    main()

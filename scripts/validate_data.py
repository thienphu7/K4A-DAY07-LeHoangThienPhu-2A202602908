#!/usr/bin/env python3
"""Validate a Day 7 corpus directory and its sources.csv manifest."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


REQUIRED_METADATA = (
    "doc_id",
    "title",
    "source_url",
    "retrieved_at",
    "document_version",
    "audience",
)
FRONT_MATTER_FIELD = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_front_matter(path: Path) -> dict[str, str]:
    parts = path.read_text(encoding="utf-8").split("---", maxsplit=2)
    if len(parts) < 3:
        return {}
    return dict(FRONT_MATTER_FIELD.findall(parts[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="Corpus directory containing Markdown files and sources.csv")
    args = parser.parse_args()

    data_dir = args.data_dir
    manifest_path = data_dir / "sources.csv"
    if not data_dir.is_dir():
        parser.error(f"directory does not exist: {data_dir}")
    if not manifest_path.is_file():
        parser.error(f"manifest does not exist: {manifest_path}")

    markdown_files = sorted(data_dir.glob("*.md"))
    with manifest_path.open(encoding="utf-8", newline="") as manifest_file:
        rows = list(csv.DictReader(manifest_file))

    document_ids: list[str] = []
    audiences: dict[str, int] = {}
    files_ok = True

    for path in markdown_files:
        metadata = parse_front_matter(path)
        document_id = metadata.get("doc_id")
        audience = metadata.get("audience")
        document_ids.append(document_id or "")
        audience_key = audience or "<missing>"
        audiences[audience_key] = audiences.get(audience_key, 0) + 1
        valid = all(key in metadata for key in REQUIRED_METADATA) and document_id == path.stem
        files_ok = files_ok and valid
        status = "OK" if valid else "THIEU METADATA"
        print(f"{path.name:40} {status}")

    manifest_ids = sorted(row.get("doc_id") for row in rows)
    ids_match = manifest_ids == sorted(document_ids)
    count_ok = 5 <= len(markdown_files) <= 10
    audience_ok = len(audiences) >= 2 and "<missing>" not in audiences

    print("so file :", len(markdown_files), "(can 5-10)")
    print("csv     :", "khop" if ids_match else "LECH")
    print("audience:", audiences)

    return 0 if files_ok and count_ok and ids_match and audience_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

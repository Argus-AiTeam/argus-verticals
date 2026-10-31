#!/usr/bin/env python3
"""Build packs/catalog.json, the index Argus's skill store reads, from the folders under packs/.

A pack is a folder with a SKILL.md: its front matter gives the description and version (read the way
Argus reads them), its "## Needs" section what it needs. The catalog lists every file with its size,
which Argus checks on download; the Chinese description is the one of the vertical the pack came from.

usage: build_packs.py            rewrite packs/catalog.json
       build_packs.py --check    fail when packs/catalog.json is stale
       build_packs.py --print    print the catalog instead of writing it
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "packs"
CATALOG = PACKS / "catalog.json"


def field(matter: str, key: str) -> str:
    said = (re.search(rf"^{key}:[ \t]*(.*)$", matter, re.M) or [None, ""])[1].strip()
    return json.loads(said) if said.startswith('"') else re.sub(r"^'(.*)'$", r"\1", said)


def pack(folder: Path) -> dict:
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    matter = (re.match(r"---\n(.*?)\n---", text, re.S) or [None, ""])[1]
    needs = re.search(r"^## Needs\n\n(.*?)\n*(?=^## |\Z)", text, re.M | re.S)
    vertical = ROOT / "argus_verticals" / folder.name / "vertical.json"
    entry = {"name": folder.name, "version": field(matter, "version"), "description": field(matter, "description")}
    if vertical.is_file():
        entry["description_zh"] = json.loads(vertical.read_text(encoding="utf-8"))["purpose_zh"]
    entry["requires"] = []
    entry["needs"] = [needs[1].strip()] if needs else []
    entry["files"] = [{"path": path.relative_to(folder).as_posix(), "size": path.stat().st_size}
                      for path in sorted(folder.rglob("*"), key=lambda path: path.relative_to(folder).as_posix())
                      if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    return entry


def build() -> str:
    folders = sorted(path for path in PACKS.iterdir() if (path / "SKILL.md").is_file())
    return json.dumps({"packs": [pack(folder) for folder in folders]}, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--print", action="store_true")
    args = parser.parse_args()
    catalog = build()
    if args.print:
        sys.stdout.write(catalog)
    elif args.check:
        if CATALOG.read_text(encoding="utf-8") != catalog:
            print("packs/catalog.json is stale: run scripts/build_packs.py", file=sys.stderr)
            return 1
    else:
        CATALOG.write_text(catalog, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

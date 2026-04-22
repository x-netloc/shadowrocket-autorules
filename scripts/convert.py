#!/usr/bin/env python3
"""Convert v2dat-unpacked geosite/geoip output into Shadowrocket .list files."""

import argparse
import os
import sys
from pathlib import Path


def convert_geosite_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # v2dat may emit "@attr" suffix after domain — drop it (Shadowrocket has no attrs)
    if "@" in line:
        line = line.split("@", 1)[0].strip()
        if not line:
            return None
    if line.startswith("domain:"):
        return f"DOMAIN-SUFFIX,{line[7:]}"
    if line.startswith("full:"):
        return f"DOMAIN,{line[5:]}"
    if line.startswith("keyword:"):
        return f"DOMAIN-KEYWORD,{line[8:]}"
    if line.startswith("regexp:"):
        # Shadowrocket has no domain-regex rule; skip.
        return None
    # bare domain — treat as suffix
    return f"DOMAIN-SUFFIX,{line}"


def convert_geoip_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if ":" in line:
        return f"IP-CIDR6,{line},no-resolve"
    return f"IP-CIDR,{line},no-resolve"


def header(category: str, kind: str, upstream: str) -> list[str]:
    return [
        f"# {kind}:{category}",
        f"# Source: {upstream}",
        "# Auto-generated, do not edit by hand.",
        "",
    ]


def convert_file(src: Path, dst: Path, kind: str, category: str, upstream: str) -> int:
    converter = convert_geosite_line if kind == "geosite" else convert_geoip_line
    lines = header(category, kind, upstream)
    count = 0
    with src.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            out = converter(raw)
            if out is not None:
                lines.append(out)
                count += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def load_categories(path: Path) -> dict[str, list[str]]:
    """Parse categories.txt. Format: `geosite:<name>` or `geoip:<name>`, one per line.
    Blank lines and lines starting with # are ignored. `*` = include every category."""
    result: dict[str, list[str]] = {"geosite": [], "geoip": []}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            print(f"skip malformed line: {line}", file=sys.stderr)
            continue
        kind, name = line.split(":", 1)
        kind = kind.strip().lower()
        name = name.strip().lower()
        if kind in result and name:
            result[kind].append(name)
    return result


def discover(src_dir: Path, kind: str) -> list[str]:
    prefix = f"{kind}_"
    names = []
    for p in src_dir.glob(f"{prefix}*.txt"):
        names.append(p.stem[len(prefix):])
    return sorted(names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geosite-in", required=True, type=Path)
    ap.add_argument("--geoip-in", required=True, type=Path)
    ap.add_argument("--categories", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--upstream", required=True)
    args = ap.parse_args()

    wanted = load_categories(args.categories)

    summary: list[tuple[str, str, int]] = []

    for kind, src_dir in (("geosite", args.geosite_in), ("geoip", args.geoip_in)):
        requested = wanted[kind]
        available = discover(src_dir, kind)
        if requested == ["*"]:
            targets = available
        else:
            targets = [c for c in requested if c in available]
            missing = [c for c in requested if c not in available]
            for m in missing:
                print(f"warn: {kind}:{m} not found in upstream", file=sys.stderr)

        for category in targets:
            src = src_dir / f"{kind}_{category}.txt"
            dst = args.out / kind / f"{category}.list"
            n = convert_file(src, dst, kind, category, args.upstream)
            summary.append((kind, category, n))

    index = [
        "# Shadowrocket rule-set index",
        f"# Source: {args.upstream}",
        "",
        "| Kind | Category | Rules | Path |",
        "| --- | --- | ---: | --- |",
    ]
    for kind, category, n in summary:
        index.append(f"| {kind} | {category} | {n} | `rules/{kind}/{category}.list` |")
    (args.out / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    print(f"Wrote {len(summary)} rule-set(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

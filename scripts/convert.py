#!/usr/bin/env python3
"""Build Shadowrocket rule sets and configs from canonical autorules."""

from __future__ import annotations

import argparse
import ipaddress
import sys
import tomllib
from pathlib import Path
from typing import Any


ACTION_NAMES = {
    "direct": "DIRECT",
    "proxy": "PROXY",
    "reject": "REJECT",
}

GENERAL = """[General]
bypass-system = true
skip-proxy = 127.0.0.1, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10, localhost, *.local, captive.apple.com
bypass-tun = 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 255.255.255.255/32
dns-server = https://cloudflare-dns.com/dns-query, tls://1.1.1.1:853, tls://[2606:4700:4700::1111]:853, https://dns.google/dns-query, tls://8.8.8.8:853, tls://[2001:4860:4860::8888]:853, https://doh.opendns.com/dns-query, tls://208.67.222.222:853, tls://[2620:119:35::35]:853
fallback-dns-server = https://common.dns.yandex.net/dns-query, tls://common.dot.dns.yandex.net:853, system
ipv6 = true"""


class ConversionError(Exception):
    pass


def load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConversionError(f"cannot read {path}: {exc}") from exc


def convert_geosite_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
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
        return None
    return f"DOMAIN-SUFFIX,{line}"


def convert_geoip_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    rule_type = "IP-CIDR6" if ":" in line else "IP-CIDR"
    return f"{rule_type},{line},no-resolve"


def convert_category(
    src: Path,
    dst: Path,
    kind: str,
    category: str,
    upstream: str,
) -> int:
    if not src.is_file():
        raise ConversionError(f"missing upstream category: {kind}:{category} ({src})")

    converter = convert_geosite_line if kind == "geosite" else convert_geoip_line
    lines = [
        f"# {kind}:{category}",
        f"# Source: {upstream}",
        "# Auto-generated, do not edit by hand.",
        "",
    ]
    count = 0
    with src.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            converted = converter(raw)
            if converted is not None:
                lines.append(converted)
                count += 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def render_domain_rule(value: str, action: str) -> str:
    prefix, pattern = value.split(":", 1)
    rule_types = {
        "domain": "DOMAIN-SUFFIX",
        "full": "DOMAIN",
        "keyword": "DOMAIN-KEYWORD",
    }
    if prefix == "regexp":
        raise ConversionError(
            f"Shadowrocket cannot represent regexp profile rule: {value}"
        )
    try:
        rule_type = rule_types[prefix]
    except KeyError as exc:
        raise ConversionError(f"unsupported domain rule: {value}") from exc
    return f"{rule_type},{pattern},{action}"


def render_cidr_rule(value: str, action: str) -> str:
    try:
        version = ipaddress.ip_network(value, strict=False).version
    except ValueError as exc:
        raise ConversionError(f"invalid CIDR profile rule: {value}") from exc
    rule_type = "IP-CIDR6" if version == 6 else "IP-CIDR"
    return f"{rule_type},{value},{action},no-resolve"


def render_config(
    profile: dict[str, Any],
    repository: str,
    config_ref: str,
    rules_ref: str,
) -> str:
    profile_id = profile["id"]
    managed_url = (
        f"https://cdn.jsdelivr.net/gh/{repository}@{config_ref}/configs/{profile_id}.conf"
    )
    rules_base = f"https://cdn.jsdelivr.net/gh/{repository}@{rules_ref}"
    lines = [
        f"#!MANAGED-CONFIG {managed_url} interval=3600 strict=false",
        "#",
        f"# {profile_id}",
        f"# {profile['description']}",
        "#",
        "# Generated from x-netloc/autorules. Do not edit by hand.",
        "# Add your server or subscription, then select the active server.",
        "",
        GENERAL,
        "",
        "[Rule]",
    ]

    for rule in profile["rules"]:
        try:
            action = ACTION_NAMES[rule["action"]]
        except KeyError as exc:
            raise ConversionError(f"unsupported action in {profile_id}") from exc

        selectors = {"geosite", "geoip", "domains", "cidrs"} & rule.keys()
        if len(selectors) != 1:
            raise ConversionError(f"invalid selector in profile {profile_id}")
        selector = selectors.pop()

        if selector in {"geosite", "geoip"}:
            for category in rule[selector]:
                suffix = ",no-resolve" if selector == "geoip" else ""
                lines.append(
                    f"RULE-SET,{rules_base}/{selector}/{category}.list,{action}{suffix}"
                )
        elif selector == "domains":
            lines.extend(render_domain_rule(value, action) for value in rule[selector])
        else:
            lines.extend(render_cidr_rule(value, action) for value in rule[selector])

        lines.append("")

    try:
        default_action = ACTION_NAMES[profile["default"]]
    except KeyError as exc:
        raise ConversionError(f"unsupported default action in {profile_id}") from exc
    lines.extend([f"FINAL,{default_action}", ""])
    return "\n".join(lines)


def build(args: argparse.Namespace) -> None:
    catalog = load_toml(args.catalog)
    upstream_config = catalog["upstream"]
    upstream = f"{upstream_config['repository']}@{upstream_config['ref']}"
    categories = catalog["categories"]
    profile_ids = catalog["profiles"]["ids"]

    args.out.mkdir(parents=True, exist_ok=True)
    summaries: list[tuple[str, str, int]] = []
    if not args.configs_only:
        for kind, src_dir in (
            ("geosite", args.geosite_in),
            ("geoip", args.geoip_in),
        ):
            for category in categories[kind]:
                count = convert_category(
                    src_dir / f"{kind}_{category}.txt",
                    args.out / kind / f"{category}.list",
                    kind,
                    category,
                    upstream,
                )
                summaries.append((kind, category, count))

        index = [
            "# Shadowrocket rule-set index",
            f"# Source: {upstream}",
            "# Catalog: x-netloc/autorules",
            "",
            "| Kind | Category | Rules | Path |",
            "| --- | --- | ---: | --- |",
        ]
        index.extend(
            f"| {kind} | {category} | {count} | `{kind}/{category}.list` |"
            for kind, category, count in summaries
        )
        (args.out / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    configs_dir = args.out / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    for profile_id in profile_ids:
        profile_path = args.profiles / f"{profile_id}.toml"
        profile = load_toml(profile_path)
        if profile.get("id") != profile_id:
            raise ConversionError(f"profile id mismatch: {profile_path}")
        config = render_config(
            profile,
            repository=args.repository,
            config_ref=args.config_ref,
            rules_ref=args.rules_ref,
        )
        (configs_dir / f"{profile_id}.conf").write_text(config, encoding="utf-8")

    print(
        f"Wrote {len(summaries)} rule sets and {len(profile_ids)} configs to {args.out}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--geosite-in", type=Path)
    parser.add_argument("--geoip-in", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repository", default="x-netloc/shadowrocket-autorules")
    parser.add_argument("--config-ref", default="main")
    parser.add_argument("--rules-ref", default="dist")
    parser.add_argument(
        "--configs-only",
        action="store_true",
        help="generate prebuilt configs without unpacked rule data",
    )
    args = parser.parse_args()
    if not args.configs_only and (args.geosite_in is None or args.geoip_in is None):
        parser.error("--geosite-in and --geoip-in are required unless --configs-only is used")
    return args


def main() -> int:
    try:
        build(parse_args())
    except (ConversionError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

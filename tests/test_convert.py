import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.convert import (
    ConversionError,
    build,
    convert_geoip_line,
    convert_geosite_line,
    render_config,
)


class LineConversionTests(unittest.TestCase):
    def test_geosite_rules(self) -> None:
        cases = {
            "domain:example.com": "DOMAIN-SUFFIX,example.com",
            "full:www.example.com": "DOMAIN,www.example.com",
            "keyword:example": "DOMAIN-KEYWORD,example",
            "example.net": "DOMAIN-SUFFIX,example.net",
            "domain:example.org@cn": "DOMAIN-SUFFIX,example.org",
            "regexp:^example": None,
            "# comment": None,
            "": None,
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(convert_geosite_line(source), expected)

    def test_geoip_rules(self) -> None:
        self.assertEqual(
            convert_geoip_line("192.0.2.0/24"),
            "IP-CIDR,192.0.2.0/24,no-resolve",
        )
        self.assertEqual(
            convert_geoip_line("2001:db8::/32"),
            "IP-CIDR6,2001:db8::/32,no-resolve",
        )


class ConfigRenderingTests(unittest.TestCase):
    def test_profile_rules_and_default(self) -> None:
        profile = {
            "id": "example",
            "description": "Example profile.",
            "default": "proxy",
            "rules": [
                {"action": "direct", "geosite": ["private"]},
                {"action": "reject", "geoip": ["blocked"]},
                {"action": "direct", "domains": ["full:www.example.com"]},
                {"action": "direct", "cidrs": ["2001:db8::/32"]},
            ],
        }

        rendered = render_config(profile, "owner/repo", "main", "dist")

        self.assertIn(
            "RULE-SET,https://cdn.jsdelivr.net/gh/owner/repo@dist/geosite/private.list,DIRECT",
            rendered,
        )
        self.assertIn(
            "RULE-SET,https://cdn.jsdelivr.net/gh/owner/repo@dist/geoip/blocked.list,REJECT,no-resolve",
            rendered,
        )
        self.assertIn("DOMAIN,www.example.com,DIRECT", rendered)
        self.assertIn("IP-CIDR6,2001:db8::/32,DIRECT,no-resolve", rendered)
        self.assertTrue(rendered.endswith("FINAL,PROXY\n"))

    def test_profile_regexp_fails_instead_of_changing_semantics(self) -> None:
        profile = {
            "id": "regexp",
            "description": "Unsupported example.",
            "default": "direct",
            "rules": [{"action": "proxy", "domains": ["regexp:^example"]}],
        }

        with self.assertRaises(ConversionError):
            render_config(profile, "owner/repo", "main", "dist")


class BuildTests(unittest.TestCase):
    def test_build_uses_catalog_for_rules_and_profile_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "profiles").mkdir()
            (root / "geosite").mkdir()
            (root / "geoip").mkdir()
            (root / "catalog.toml").write_text(
                """schema_version = 1

[upstream]
repository = "owner/upstream"
ref = "release"
geosite_asset = "geosite.dat"
geoip_asset = "geoip.dat"

[categories]
geosite = ["private"]
geoip = ["private"]

[profiles]
ids = ["example"]
""",
                encoding="utf-8",
            )
            (root / "profiles" / "example.toml").write_text(
                """schema_version = 1
id = "example"
description = "Example profile."
default = "proxy"

[[rules]]
action = "direct"
geosite = ["private"]
""",
                encoding="utf-8",
            )
            (root / "geosite" / "geosite_private.txt").write_text(
                "domain:example.com\n",
                encoding="utf-8",
            )
            (root / "geoip" / "geoip_private.txt").write_text(
                "192.0.2.0/24\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                catalog=root / "catalog.toml",
                profiles=root / "profiles",
                geosite_in=root / "geosite",
                geoip_in=root / "geoip",
                out=root / "out",
                repository="owner/repo",
                config_ref="main",
                rules_ref="dist",
                configs_only=False,
            )

            build(args)

            self.assertIn(
                "DOMAIN-SUFFIX,example.com",
                (root / "out/geosite/private.list").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "IP-CIDR,192.0.2.0/24,no-resolve",
                (root / "out/geoip/private.list").read_text(encoding="utf-8"),
            )
            self.assertTrue((root / "out/configs/example.conf").is_file())
            self.assertIn(
                "`geosite/private.list`",
                (root / "out/INDEX.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()

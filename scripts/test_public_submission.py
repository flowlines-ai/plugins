"""Offline checks for the public submission assets and desktop compatibility."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from build_public_submission import ROOT, SOURCE, build
from validate_branding import validate_logo


def validate_relative_links(root: Path, path: Path, markdown: str) -> None:
    root = root.resolve()
    for raw_target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("#", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if resolved != root and root not in resolved.parents:
            raise AssertionError(f"{path}: link escapes {root.name}: {raw_target}")
        if not resolved.is_file():
            raise AssertionError(f"{path}: missing linked resource: {raw_target}")


def source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (SOURCE, ROOT / ".agents", ROOT / ".claude-plugin")
        for path in directory.rglob("*") if path.is_file()
    }


class PublicSubmissionTests(unittest.TestCase):
    def test_portable_and_compatibility_manifests_match(self) -> None:
        portable = json.loads((SOURCE / "plugin.json").read_text())
        codex = json.loads((SOURCE / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((SOURCE / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(portable["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
            self.assertEqual(portable[key], codex[key], key)
            self.assertEqual(portable[key], claude[key], key)
        self.assertEqual(portable["extensions"]["com.openai"], {"interface": codex["interface"]})
        for key in ("skills", "mcpServers", "interface"):
            self.assertNotIn(key, portable)
        self.assertNotIn("skills", codex)
        self.assertEqual(codex["mcpServers"], "./.mcp.json")
        self.assertEqual(claude["mcpServers"], "./.mcp.json")
        portable_mcp = json.loads((SOURCE / "mcp.json").read_text())
        legacy_mcp = json.loads((SOURCE / ".mcp.json").read_text())
        self.assertEqual(portable_mcp, {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            "mcpServers": {"flowlines": {"type": "streamable-http", "url": "https://api.flowlines.ai/mcp"}},
        })
        self.assertEqual(legacy_mcp, {
            "mcpServers": {"flowlines": {"type": "http", "url": portable_mcp["mcpServers"]["flowlines"]["url"]}},
        })
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == portable["name"])
        self.assertEqual(entry["version"], portable["version"])

    def test_archive_contains_one_flowlines_mcp_plugin(self) -> None:
        before = source_hashes()
        source_manifest = json.loads((SOURCE / "plugin.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "submission"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_public_submission.py"),
                 "--output", str(output)], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plugin = output / "flowlines"
            manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
            portable = json.loads((plugin / "plugin.json").read_text())
            self.assertEqual(portable, {
                "$schema": source_manifest["$schema"],
                **{key: value for key, value in manifest.items() if key not in ("mcpServers", "interface")},
                "extensions": {"com.openai": {"interface": manifest["interface"]}},
            })
            self.assertEqual(manifest["name"], "app-6aa11dfaeb20819187226d4810e1d94a")
            self.assertEqual(source_manifest["name"], "flowlines")
            self.assertEqual(manifest["version"], source_manifest["version"])
            self.assertEqual(manifest["interface"]["displayName"], "Flowlines")
            # Preserve the URLs from the existing published Flowlines listing.
            listing_urls = {
                "websiteURL": ("Website", "https://flowlines.ai/"),
                "supportURL": ("Support", "https://trust.flowlines.ai/en"),
                "privacyPolicyURL": ("Privacy policy", "https://app.flowlines.ai/privacy-policy"),
                "termsOfServiceURL": ("Terms", "https://app.flowlines.ai/terms-of-service"),
            }
            for field, (label, url) in listing_urls.items():
                self.assertEqual(source_manifest["extensions"]["com.openai"]["interface"][field], url)
                self.assertEqual(manifest["interface"][field], url)
                self.assertIn(f"| {label} | {url} |", (ROOT / "docs/openai-submission.md").read_text())
            self.assertEqual(manifest["mcpServers"], "./.mcp.json")
            for name in ("mcp.json", ".mcp.json"):
                self.assertEqual((plugin / name).read_bytes(), (SOURCE / name).read_bytes())
            for key in ("apps", "hooks", "skills"):
                self.assertNotIn(key, manifest)
            for name in (".app.json", ".claude-plugin", ".agents", "hooks", "skills"):
                self.assertFalse((plugin / name).exists(), name)
            self.assertFalse((output / ".agents").exists())
            with ZipFile(output / "flowlines.zip") as archive:
                self.assertIsNone(archive.testzip())
                archived_manifest = json.loads(archive.read(".codex-plugin/plugin.json"))
                for field, (_label, url) in listing_urls.items():
                    self.assertEqual(archived_manifest["interface"][field], url)
                self.assertEqual(set(archive.namelist()), {
                    path.relative_to(plugin).as_posix()
                    for path in plugin.rglob("*") if path.is_file()
                })
                self.assertIn(".codex-plugin/plugin.json", archive.namelist())
                for name in ("plugin.json", "mcp.json", ".mcp.json"):
                    self.assertEqual(archive.read(name), (plugin / name).read_bytes())
                for name in archive.namelist():
                    self.assertNotIn("asdk_app_", archive.read(name).decode("utf-8", errors="ignore"))
            for name in ("openai-submission.md", "chatgpt.md"):
                path = output / name
                self.assertEqual(path.read_bytes(), (ROOT / "docs" / name).read_bytes())
                validate_relative_links(output, path, path.read_text())
        self.assertEqual(source_hashes(), before)

    def test_listing_meets_final_submission_text_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "submission"
            build(output)
            manifest = json.loads((output / "flowlines/.codex-plugin/plugin.json").read_text())
            interface = manifest["interface"]
            for key, limit in (("displayName", 30), ("shortDescription", 30), ("developerName", 80)):
                self.assertTrue(interface[key])
                self.assertLessEqual(len(interface[key]), limit)
                self.assertNotIn("\n", interface[key])
            self.assertLessEqual(len(interface["longDescription"]), 4000)
            prompts = interface["defaultPrompt"]
            self.assertLessEqual(len(prompts), 3)
            self.assertEqual(len(prompts), len(set(prompts)))
            for prompt in prompts:
                self.assertTrue(prompt)
                self.assertLessEqual(len(prompt), 128)
                self.assertNotIn("@", prompt)
                self.assertNotIn("\n", prompt)
            for key in ("composerIcon", "logo"):
                image = output / "flowlines" / interface[key]
                validate_logo(image)
                with ZipFile(output / "flowlines.zip") as archive:
                    self.assertEqual(archive.read(interface[key].removeprefix("./")), image.read_bytes())

    def test_branding_rejects_invalid_images(self) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

        def png(width: int, height: int, pixels: bytes | None = None) -> bytes:
            header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
            if pixels is None:
                pixels = (b"\0" + b"\0" * width * 4) * height
            return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")

        valid = png(48, 48)
        cases = {
            "format mismatch": b"JPEG data",
            "too small": png(47, 47),
            "not square": png(48, 49),
            "too wide": png(4097, 4097, b""),
            "too large": valid + b"\0" * (5 * 1024 * 1024),
            "truncated": valid[:-1],
            "checksum": valid[:29] + b"\0" * 4 + valid[33:],
            "missing pixels": png(48, 48, b""),
            "invalid filter": png(48, 48, (b"\x05" + b"\0" * 48 * 4) * 48),
            "extra pixels": png(48, 48, b"\0" * (48 * 193 + 1)),
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "logo.png"
            path.write_bytes(valid)
            validate_logo(path)
            for label, data in cases.items():
                with self.subTest(label=label):
                    path.write_bytes(data)
                    with self.assertRaises(ValueError):
                        validate_logo(path)

    def test_invalid_branding_does_not_produce_a_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            shutil.copy2(SOURCE / "plugin.json", source / "plugin.json")
            (source / "assets").mkdir()
            (source / "assets/logo.png").write_bytes(b"broken image")
            with patch("build_public_submission.SOURCE", source):
                with self.assertRaises(ValueError):
                    build(root / "output")
            self.assertFalse((root / "output").exists())

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            existing = output / "keep.txt"
            existing.write_text("keep this file")
            with self.assertRaises(FileExistsError):
                build(output)
            self.assertEqual(existing.read_text(), "keep this file")
            self.assertFalse((output / "flowlines").exists())

    def test_failed_build_can_be_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            with patch("build_public_submission.ZipFile", side_effect=OSError("ZIP failed")):
                with self.assertRaisesRegex(OSError, "ZIP failed"):
                    build(output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [])
            self.assertTrue(build(output).is_file())

    def test_review_cases_and_documentation_links(self) -> None:
        for path in (ROOT / "README.md", ROOT / "docs/chatgpt.md", ROOT / "docs/openai-submission.md"):
            validate_relative_links(ROOT, path, path.read_text())
        worksheet = (ROOT / "docs/openai-submission.md").read_text()
        self.assertEqual(re.findall(r"^### P(\d+) —", worksheet, re.MULTILINE), list("12345"))
        self.assertEqual(re.findall(r"^### N(\d+) —", worksheet, re.MULTILINE), list("123"))


if __name__ == "__main__":
    unittest.main()

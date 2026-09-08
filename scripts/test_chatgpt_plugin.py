"""Offline checks for the ChatGPT distribution and desktop regression boundary."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from build_chatgpt_plugin import ROOT, SOURCE, build
from validate_skills import validate_relative_links, validate_skill


def source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (SOURCE, ROOT / ".agents", ROOT / ".claude-plugin")
        for path in directory.rglob("*") if path.is_file()
    }


class ChatGPTPluginTests(unittest.TestCase):
    def run_builder(self, output: Path, registered_id: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_chatgpt_plugin.py"),
             "--app-id", registered_id, "--output", str(output)],
            capture_output=True, text=True,
        )

    def test_workspace_package_is_bound_and_self_contained(self) -> None:
        before = source_hashes()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "chatgpt"
            # This is an offline fixture, never a registered or published connection.
            result = self.run_builder(output, "plugin_asdk_app_offline_test")
            self.assertEqual(result.returncode, 0, result.stderr)
            plugin = output / "plugins" / "flowlines-chatgpt"
            manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
            self.assertEqual(manifest["name"], plugin.name)
            self.assertNotEqual(manifest["name"], "flowlines")
            self.assertEqual(manifest["interface"]["displayName"], "Flowlines for ChatGPT")
            self.assertEqual(manifest["apps"], "./.app.json")
            self.assertEqual(json.loads((plugin / ".app.json").read_text()), {
                "apps": {"flowlines": {"id": "asdk_app_offline_test", "required": True}},
            })
            self.assertNotIn("mcpServers", manifest)
            self.assertNotIn("hooks", manifest)
            for name in (".mcp.json", "mcp.json", ".claude-plugin", "hooks"):
                self.assertFalse((plugin / name).exists(), name)
            for key in ("composerIcon", "logo"):
                self.assertTrue((plugin / manifest["interface"][key]).is_file())
            self.assertEqual({path.name for path in (plugin / "skills").iterdir()}, {
                "flowlines-weekly-review", "flowlines-release-check",
                "flowlines-investigate-session", "flowlines-cohort-builder",
            })
            for skill in (plugin / "skills").iterdir():
                validate_skill(skill)
            marketplace = json.loads((output / ".agents/plugins/marketplace.json").read_text())
            entry = marketplace["plugins"][0]
            self.assertEqual(entry["name"], manifest["name"])
            self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
            self.assertEqual((output / entry["source"]["path"]).resolve(), plugin.resolve())
            with ZipFile(output / "flowlines-chatgpt.zip") as archive:
                self.assertEqual(set(archive.namelist()), {
                    path.relative_to(plugin).as_posix()
                    for path in plugin.rglob("*") if path.is_file()
                })
                self.assertIn(".app.json", archive.namelist())
                self.assertIn(".codex-plugin/plugin.json", archive.namelist())
                self.assertEqual(archive.read(".app.json"), (plugin / ".app.json").read_bytes())
        self.assertEqual(source_hashes(), before)

    def test_invalid_id_does_not_create_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for value in ("", "flowlines", "asdk_app_", "plugin_123", "asdk_app_../secret",
                          "https://chatgpt.com/plugins/plugin_asdk_app_test"):
                with self.subTest(value=value):
                    output = Path(temporary) / "chatgpt"
                    result = self.run_builder(output, value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

    def test_committed_marketplace_matches_build(self) -> None:
        committed = ROOT / "chatgpt"
        apps = json.loads((committed / "plugins/flowlines-chatgpt/.app.json").read_text())
        registered_id = apps["apps"]["flowlines"]["id"]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "chatgpt"
            build(registered_id, output)
            # The ZIP is for local distribution and is not committed.
            expected = {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file() and path.name != "flowlines-chatgpt.zip"
            }
            actual = {
                path.relative_to(committed): path.read_bytes()
                for directory in (committed / ".agents", committed / "plugins")
                for path in directory.rglob("*") if path.is_file()
            }
            self.assertEqual(set(actual), set(expected))
            for path, content in expected.items():
                self.assertEqual(actual[path], content, f"Regenerate chatgpt/: {path}")

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            existing = output / ".mcp.json"
            existing.write_text("keep this file")
            result = self.run_builder(output, "asdk_app_offline_test")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(existing.read_text(), "keep this file")
            self.assertFalse((output / "plugins").exists())

    def test_local_junk_is_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            shutil.copytree(SOURCE, source)
            skill = source / "skills" / "flowlines-cohort-builder"
            (skill / ".DS_Store").write_text("local metadata")
            (skill / "__pycache__").mkdir()
            (skill / "__pycache__" / "cached.pyc").write_bytes(b"cached bytecode")
            (skill / "references" / "cached.pyc").write_bytes(b"cached bytecode")
            (skill / "references" / ".DS_Store").write_text("nested metadata")
            with patch("build_chatgpt_plugin.SOURCE", source):
                archive = build("asdk_app_offline_test", root / "output")
            with ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    self.assertNotIn(".DS_Store", name)
                    self.assertNotIn("__pycache__", name)
                    self.assertFalse(name.endswith(".pyc"), name)
                self.assertIn("skills/flowlines-cohort-builder/references/cohort-rules.md", bundle.namelist())

    def test_failed_build_can_be_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            with patch("build_chatgpt_plugin.shutil.copytree", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    build("asdk_app_offline_test", output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [])
            self.assertTrue(build("asdk_app_offline_test", output).is_file())

    def test_documentation_links(self) -> None:
        path = ROOT / "docs" / "chatgpt.md"
        validate_relative_links(ROOT, path, path.read_text())


if __name__ == "__main__":
    unittest.main()

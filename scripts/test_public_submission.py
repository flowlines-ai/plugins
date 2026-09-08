"""Offline checks for the public submission assets and desktop compatibility."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from build_public_submission import ROOT, SOURCE, build
from validate_skills import validate_relative_links, validate_skill


def source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (SOURCE, ROOT / ".agents", ROOT / ".claude-plugin")
        for path in directory.rglob("*") if path.is_file()
    }


class PublicSubmissionTests(unittest.TestCase):
    def test_archive_contains_one_flowlines_skill_bundle(self) -> None:
        before = source_hashes()
        source_manifest = json.loads((SOURCE / ".codex-plugin/plugin.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "submission"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_public_submission.py"),
                 "--output", str(output)], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plugin = output / "flowlines"
            manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
            self.assertEqual(manifest["name"], "flowlines")
            self.assertEqual(manifest["version"], source_manifest["version"])
            self.assertEqual(manifest["interface"]["displayName"], "Flowlines")
            support_url = "https://github.com/flowlines-ai/plugins/issues"
            self.assertEqual(manifest["interface"]["supportURL"], support_url)
            self.assertIn(
                f"| Support | {support_url} |",
                (ROOT / "docs/openai-submission.md").read_text(),
            )
            self.assertEqual(manifest["skills"], "./skills/")
            for key in ("mcpServers", "apps", "hooks"):
                self.assertNotIn(key, manifest)
            for name in (".mcp.json", ".app.json", ".claude-plugin", ".agents", "hooks"):
                self.assertFalse((plugin / name).exists(), name)
            self.assertFalse((output / ".agents").exists())
            self.assertEqual({path.name for path in (plugin / "skills").iterdir()}, {
                "flowlines-weekly-review", "flowlines-release-check",
                "flowlines-investigate-session", "flowlines-cohort-builder",
            })
            for skill in (plugin / "skills").iterdir():
                validate_skill(skill)
                for path in skill.rglob("*"):
                    if path.is_file():
                        source = SOURCE / "skills" / path.relative_to(plugin / "skills")
                        self.assertEqual(path.read_bytes(), source.read_bytes())
            with ZipFile(output / "flowlines.zip") as archive:
                self.assertIsNone(archive.testzip())
                archived_manifest = json.loads(archive.read(".codex-plugin/plugin.json"))
                self.assertEqual(archived_manifest["interface"]["supportURL"], support_url)
                self.assertEqual(set(archive.namelist()), {
                    path.relative_to(plugin).as_posix()
                    for path in plugin.rglob("*") if path.is_file()
                })
                self.assertIn(".codex-plugin/plugin.json", archive.namelist())
                self.assertIn("skills/flowlines-cohort-builder/references/cohort-rules.md", archive.namelist())
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
                self.assertTrue((output / "flowlines" / interface[key]).is_file())

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            existing = output / "keep.txt"
            existing.write_text("keep this file")
            with self.assertRaises(FileExistsError):
                build(output)
            self.assertEqual(existing.read_text(), "keep this file")
            self.assertFalse((output / "flowlines").exists())

    def test_local_cache_files_are_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            shutil.copytree(SOURCE, source)
            skill = source / "skills/flowlines-cohort-builder"
            (skill / ".DS_Store").write_text("local metadata")
            (skill / "__pycache__").mkdir()
            (skill / "__pycache__/cached.pyc").write_bytes(b"cached bytecode")
            (skill / "references/cached.pyc").write_bytes(b"cached bytecode")
            with patch("build_public_submission.SOURCE", source):
                archive = build(root / "output")
            with ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    self.assertNotIn(".DS_Store", name)
                    self.assertNotIn("__pycache__", name)
                    self.assertFalse(name.endswith(".pyc"), name)

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
        for name in ("chatgpt.md", "openai-submission.md"):
            path = ROOT / "docs" / name
            validate_relative_links(ROOT, path, path.read_text())
        worksheet = (ROOT / "docs/openai-submission.md").read_text()
        self.assertEqual(re.findall(r"^### P(\d+) —", worksheet, re.MULTILINE), list("12345"))
        self.assertEqual(re.findall(r"^### N(\d+) —", worksheet, re.MULTILINE), list("123"))


if __name__ == "__main__":
    unittest.main()

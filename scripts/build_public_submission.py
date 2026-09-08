#!/usr/bin/env python3
"""Prepare the skills and listing assets for one public Flowlines MCP plugin."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "flowlines"
ANALYSIS_SKILLS = (
    "flowlines-weekly-review",
    "flowlines-release-check",
    "flowlines-investigate-session",
    "flowlines-cohort-builder",
)


def build(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # A failed copy or ZIP write must leave the destination available for retry.
    with TemporaryDirectory(prefix=".flowlines-submission-", dir=output.parent) as temporary:
        staged = Path(temporary) / "submission"
        write_submission(staged)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"Output already exists: {output}")
        staged.rename(output)
    return output / "flowlines.zip"


def write_submission(output: Path) -> None:
    source_manifest = json.loads((SOURCE / ".codex-plugin/plugin.json").read_text())
    plugin = output / "flowlines"
    manifest = {
        key: source_manifest[key]
        for key in ("name", "version", "author", "homepage", "repository", "license", "keywords")
    }
    manifest.update({
        "description": "Review AI agent activity, compare releases, investigate sessions, and analyse user cohorts with Flowlines.",
        "skills": "./skills/",
        "interface": {
            "displayName": "Flowlines",
            "shortDescription": "Understand your AI agents",
            "longDescription": "Connect your Flowlines account to review agent activity, compare outcomes before and after a release, investigate unsuccessful sessions, and analyse user cohorts. Use aggregate metrics and focused session evidence to explain findings. Save verified findings as workspace notes when requested. Requires a Flowlines account with access to a workspace containing agent data.",
            "developerName": "Flowlines",
            "category": "Developer Tools",
            "capabilities": ["Read", "Write"],
            "websiteURL": source_manifest["interface"]["websiteURL"],
            "supportURL": "https://github.com/flowlines-ai/plugins/issues",
            "privacyPolicyURL": source_manifest["interface"]["privacyPolicyURL"],
            "termsOfServiceURL": source_manifest["interface"]["termsOfServiceURL"],
            "defaultPrompt": [
                "What changed in my Flowlines namespace this week?",
                "Compare agent outcomes before and after my latest release.",
                "Investigate unsuccessful sessions in my Flowlines workspace.",
            ],
            "composerIcon": "./assets/logo.png",
            "logo": "./assets/logo.png",
        },
    })
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin/plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    (plugin / "assets").mkdir()
    shutil.copy2(SOURCE / "assets/logo.png", plugin / "assets/logo.png")
    for skill in ANALYSIS_SKILLS:
        shutil.copytree(
            SOURCE / "skills" / skill, plugin / "skills" / skill,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
        )
    shutil.copy2(ROOT / "LICENSE", plugin / "LICENSE")
    # The portal binds the production MCP server in the same With MCP draft.
    # A personal app reference or desktop MCP declaration is not a submission.
    with ZipFile(output / "flowlines.zip", "w", ZIP_DEFLATED) as archive:
        for path in sorted(plugin.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(plugin))
    for name in ("openai-submission.md", "chatgpt.md"):
        shutil.copy2(ROOT / "docs" / name, output / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    try:
        archive = build(args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot prepare public submission: {error}\n")
    print(f"Created {archive}")
    print("Use one With MCP submission: add the production server URL and these skills.")
    print("This build does not register, install, submit, or publish a connected plugin.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Package the hosted MCP server, analysis skills, and public Flowlines listing."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from validate_branding import validate_logo

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
    source_manifest = json.loads((SOURCE / "plugin.json").read_text())
    source_interface = source_manifest["extensions"]["com.openai"]["interface"]
    validate_logo(SOURCE / "assets/logo.png")
    plugin = output / "flowlines"
    manifest = {
        key: source_manifest[key]
        for key in ("name", "version", "author", "homepage", "repository", "license", "keywords")
    }
    manifest.update({
        "description": "Review MCP server activity, compare releases, investigate sessions, and analyse user cohorts with Flowlines.",
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
        "interface": {
            "displayName": "Flowlines",
            "shortDescription": "Understand your MCP servers",
            "longDescription": "Connect your Flowlines account to review MCP server activity, compare outcomes before and after a release, investigate unsuccessful sessions, and analyse user cohorts. Use aggregate metrics and focused session evidence to explain findings. Save verified findings as workspace notes when requested. Requires a Flowlines account with access to a workspace containing MCP telemetry.",
            "developerName": "Flowlines",
            "category": "Developer Tools",
            "capabilities": ["Read", "Write"],
            "websiteURL": source_interface["websiteURL"],
            "supportURL": source_interface["supportURL"],
            "privacyPolicyURL": source_interface["privacyPolicyURL"],
            "termsOfServiceURL": source_interface["termsOfServiceURL"],
            "defaultPrompt": [
                "What changed in my Flowlines namespace this week?",
                "Compare MCP session outcomes before and after my latest server release.",
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
    portable_manifest = {
        "$schema": source_manifest["$schema"],
        **{key: value for key, value in manifest.items() if key not in ("skills", "mcpServers", "interface")},
        "extensions": {"com.openai": {"interface": manifest["interface"]}},
    }
    (plugin / "plugin.json").write_text(
        json.dumps(portable_manifest, indent=2) + "\n", encoding="utf-8",
    )
    for name in ("mcp.json", ".mcp.json"):
        shutil.copy2(SOURCE / name, plugin / name)
    (plugin / "assets").mkdir()
    shutil.copy2(SOURCE / "assets/logo.png", plugin / "assets/logo.png")
    for skill in ANALYSIS_SKILLS:
        shutil.copytree(
            SOURCE / "skills" / skill, plugin / "skills" / skill,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
        )
    shutil.copy2(ROOT / "LICENSE", plugin / "LICENSE")
    # The portal imports the remote endpoint; OAuth and review still need setup.
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
    print("Use one With MCP submission: review the included server, skills, and listing.")
    print("Complete OAuth and review setup in the portal. This build does not submit or publish.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a ChatGPT workspace plugin bound to an existing Flowlines MCP app."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "flowlines"
ANALYSIS_SKILLS = (
    "flowlines-weekly-review",
    "flowlines-release-check",
    "flowlines-investigate-session",
    "flowlines-cohort-builder",
)


def app_id(value: str) -> str:
    """A management URL uses plugin_<app ID>; .app.json needs the app ID."""
    value = value.strip().removeprefix("plugin_")
    if not re.fullmatch(r"(?:asdk_app|connector|templated_apps)_[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise argparse.ArgumentTypeError(
            "Use the registered app ID (asdk_app_..., connector_..., or templated_apps_...)."
        )
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def build(registered_app_id: str, output: Path) -> Path:
    registered_app_id = app_id(registered_app_id)
    source_manifest = json.loads((SOURCE / ".codex-plugin" / "plugin.json").read_text())
    # Refuse an existing destination, including a dangling symlink. Never merge stale
    # desktop MCP files into a package intended for ChatGPT web.
    output.mkdir(parents=True, exist_ok=False)
    plugin = output / "plugins" / "flowlines"
    manifest = {
        key: source_manifest[key]
        for key in ("name", "version", "author", "homepage", "repository", "license", "keywords")
    }
    manifest.update({
        "description": "Analyse your Flowlines workspace in ChatGPT through the registered Flowlines MCP app.",
        "skills": "./skills/",
        "apps": "./.app.json",
        "interface": {
            "displayName": "Flowlines",
            "shortDescription": "Investigate agent outcomes in your Flowlines workspace",
            "longDescription": "Review activity, compare releases, investigate sessions, and analyse user cohorts through the Flowlines MCP app. Save verified findings as workspace notes.",
            "developerName": "Flowlines",
            "category": "Developer Tools",
            "capabilities": ["Read", "Write"],
            "websiteURL": source_manifest["interface"]["websiteURL"],
            "privacyPolicyURL": source_manifest["interface"]["privacyPolicyURL"],
            "termsOfServiceURL": source_manifest["interface"]["termsOfServiceURL"],
            "defaultPrompt": [
                "What changed in my Flowlines namespace this week?",
                "Compare agent outcomes before and after my latest release.",
                "Investigate the unsuccessful sessions in my Flowlines workspace.",
            ],
            "composerIcon": "./assets/logo.png",
            "logo": "./assets/logo.png",
        },
    })
    write_json(plugin / ".codex-plugin" / "plugin.json", manifest)
    write_json(plugin / ".app.json", {
        "apps": {"flowlines": {"id": registered_app_id, "required": True}},
    })
    (plugin / "assets").mkdir()
    shutil.copy2(SOURCE / "assets" / "logo.png", plugin / "assets" / "logo.png")
    for skill in ANALYSIS_SKILLS:
        shutil.copytree(SOURCE / "skills" / skill, plugin / "skills" / skill)
    shutil.copy2(ROOT / "LICENSE", plugin / "LICENSE")
    write_json(output / ".agents" / "plugins" / "marketplace.json", {
        "name": "flowlines-chatgpt",
        "interface": {"displayName": "Flowlines for ChatGPT"},
        "plugins": [{
            "name": "flowlines",
            "source": {"source": "local", "path": "./plugins/flowlines"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools",
        }],
    })
    archive = output / "flowlines-chatgpt.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for path in sorted(plugin.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(plugin))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True, type=app_id, help="Registered Flowlines app ID")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    try:
        archive = build(args.app_id, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot build ChatGPT plugin: {error}\n")
    print(f"Created {archive}")
    print("Registration, workspace access, OAuth, and a fresh-chat query must still be verified.")


if __name__ == "__main__":
    main()

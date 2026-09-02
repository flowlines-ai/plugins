#!/usr/bin/env python3
"""Validate every skill package bundled in the plugins of this repository."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def frontmatter(skill_file: Path, markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n"):
        fail(f"{skill_file}: SKILL.md must start with YAML frontmatter")
    try:
        header, _body = markdown[4:].split("\n---\n", 1)
    except ValueError:
        fail(f"{skill_file}: SKILL.md frontmatter is not closed")

    fields: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def validate_relative_links(root: Path, path: Path, markdown: str) -> None:
    root = root.resolve()
    for raw_target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("#", "mailto:")):
            continue
        resolved = (path.parent / target).resolve()
        if resolved != root and root not in resolved.parents:
            fail(f"{path}: link escapes {root.name}: {raw_target}")
        if not resolved.is_file():
            fail(f"{path}: missing linked resource: {raw_target}")


def validate_skill(skill_dir: Path) -> None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        fail(f"missing {skill_file.relative_to(ROOT)}")

    markdown = skill_file.read_text(encoding="utf-8")
    fields = frontmatter(skill_file, markdown)
    if fields.get("name") != skill_dir.name:
        fail(f"{skill_file}: skill name must match its directory")
    if not fields.get("description"):
        fail(f"{skill_file}: skill description must be non-empty")
    if "TODO" in markdown or "[TODO" in markdown:
        fail(f"{skill_file}: unfinished scaffold placeholder")

    validate_relative_links(skill_dir, skill_file, markdown)
    for reference in sorted((skill_dir / "references").glob("*.md")):
        validate_relative_links(skill_dir, reference, reference.read_text(encoding="utf-8"))

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        fail(f"missing {openai_yaml.relative_to(ROOT)}")
    if f"${skill_dir.name}" not in openai_yaml.read_text(encoding="utf-8"):
        fail(f"{openai_yaml}: default prompt must name the skill")

    for script in sorted((skill_dir / "scripts").glob("*.sh")):
        if not script.stat().st_mode & 0o111:
            fail(f"{script.relative_to(ROOT)} must be executable")


def validate_mcp_observability_contract(skill_dir: Path) -> None:
    """Invariants of the Flowlines MCP telemetry contract that the skill must keep stating."""
    markdown = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for attribute in ("`user.id`", "`user.name`", "`user.email`"):
        if attribute not in markdown:
            fail(f"SKILL.md must require the exact {attribute} identity attribute")
    for phrase in ("MCP-level middleware", "AddReceivingMiddleware", "on_call_tool"):
        if phrase not in markdown:
            fail(f"SKILL.md must prefer MCP middleware boundary: missing {phrase!r}")
    for status in ("`OK`", "`ERROR`", "`UNSET`"):
        if status not in markdown:
            fail(f"SKILL.md must define explicit completed-call status: missing {status}")

    references = skill_dir / "references"
    vanilla = (references / "vanilla-opentelemetry.md").read_text(encoding="utf-8")
    for phrase in (
        "MCP-level middleware",
        "AddReceivingMiddleware",
        "on_call_tool",
        "HTTP, transport, or sending middleware",
    ):
        if phrase not in vanilla:
            fail(f"vanilla-opentelemetry.md must prefer MCP middleware boundary: missing {phrase!r}")

    python_agntcy = (references / "python-agntcy.md").read_text(encoding="utf-8")
    contract = (references / "contract.md").read_text(encoding="utf-8")
    for name, text in (
        ("vanilla-opentelemetry.md", vanilla),
        ("python-agntcy.md", python_agntcy),
        ("contract.md", contract),
    ):
        for status in ("`OK`", "`ERROR`", "`UNSET`"):
            if status not in text:
                fail(f"{name} must define explicit completed-call status: missing {status}")

    for mapping_fragment in (
        '"userIdAttribute": "user.id"',
        '"fieldId": "name"',
        '"attributeKey": "user.name"',
        '"fieldId": "email"',
        '"attributeKey": "user.email"',
        '"sessionId": "session.id"',
        '"userId": "user.id"',
        '"user.name": "user.name"',
        '"user.email": "user.email"',
    ):
        if mapping_fragment not in contract:
            fail(f"contract.md is missing Flowlines identity mapping: {mapping_fragment}")


def main() -> None:
    skill_dirs = sorted(
        path for path in PLUGINS_DIR.glob("*/skills/*") if path.is_dir() and not path.name.startswith(".")
    )
    if not skill_dirs:
        fail("no skills found under plugins/*/skills")

    for skill_dir in skill_dirs:
        validate_skill(skill_dir)
        if skill_dir.name == "flowlines-mcp-observability":
            validate_mcp_observability_contract(skill_dir)
        print(f"Validated {skill_dir.relative_to(ROOT)}")

    readme = ROOT / "README.md"
    validate_relative_links(ROOT, readme, readme.read_text(encoding="utf-8"))
    print("Validated README.md links")


if __name__ == "__main__":
    main()

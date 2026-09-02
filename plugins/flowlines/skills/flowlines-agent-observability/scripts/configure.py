#!/usr/bin/env python3
"""Safely merge and roll back Flowlines agent observability configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 is still common on supported machines.
    tomllib = None  # type: ignore[assignment]

MANAGED_HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse", "Stop")
MANAGED_HOOK_COMMAND_FRAGMENT = "flowlines-agent-observability/codex-hook-relay.sh"
FLOWLINES_HEADER = "x-flowlines-api-key"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
OTLP_ENV_PREFIX = "OTEL_EXPORTER_OTLP_"
CLAUDE_MANAGED_ENV = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
    "OTEL_LOGS_EXPORTER",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_ASSISTANT_RESPONSES",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
)
CODEX_MANAGED_KEYS = {"otel": ("environment", "log_user_prompt", "exporter"), "features": ("hooks",)}
CODEX_EXPORTER_TABLE = "otel.exporter"


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--target", choices=("claude", "codex", "both"), required=True)
    install.add_argument("--relay-source", type=Path, required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("uninstall")
    args = parser.parse_args()

    paths = installation_paths()
    if args.operation == "install":
        return install_configuration(paths, args.target, args.relay_source)
    if args.operation == "doctor":
        return doctor(paths)
    return uninstall(paths)


def installation_paths() -> dict[str, Path]:
    user_home = Path(os.environ.get("FLOWLINES_AGENT_HOME", os.environ["HOME"])).expanduser()
    config_root = Path(
        os.environ.get(
            "FLOWLINES_AGENT_CONFIG_HOME",
            os.environ.get("XDG_CONFIG_HOME", str(user_home / ".config")),
        )
    ).expanduser()
    state_dir = config_root / "flowlines-agent-observability"
    return {
        "home": user_home,
        "state_dir": state_dir,
        "state": state_dir / "state.json",
        "originals": state_dir / "originals",
        "curl": state_dir / "curl.conf",
        "spool": state_dir / "spool",
        "runtime": user_home / ".local" / "lib" / "flowlines-agent-observability",
        "relay": user_home
        / ".local"
        / "lib"
        / "flowlines-agent-observability"
        / "codex-hook-relay.sh",
        "claude": user_home / ".claude" / "settings.json",
        "codex": user_home / ".codex" / "config.toml",
        "hooks": user_home / ".codex" / "hooks.json",
    }


def install_configuration(paths: dict[str, Path], target: str, relay_source: Path) -> int:
    api_key = os.environ.get("FLOWLINES_API_KEY", "")
    api_base = validate_api_base(os.environ.get("FLOWLINES_API_BASE_URL", "https://api.flowlines.ai"))
    replace_existing = os.environ.get("FLOWLINES_REPLACE_EXISTING_OTEL", "") == "yes"
    if not api_key or "\n" in api_key or "\r" in api_key:
        fail("FLOWLINES_API_KEY must be a non-empty single-line value.")
    if not relay_source.is_file():
        fail("Codex relay source was not found.")
    wanted = {"claude", "codex"} if target == "both" else {target}
    preflight(paths, wanted, replace_existing)

    ensure_private_dir(paths["state_dir"])
    ensure_private_dir(paths["originals"])
    ensure_private_dir(paths["spool"])
    ensure_private_dir(paths["runtime"])
    state = read_state(paths["state"])
    targets = set(state.get("targets", []))

    if target in ("claude", "both"):
        configure_claude(paths, state, api_base, api_key, replace_existing)
        targets.add("claude")
    if target in ("codex", "both"):
        shutil.copyfile(relay_source, paths["relay"])
        os.chmod(paths["relay"], 0o700)
        configure_codex(paths, state, api_base, api_key, replace_existing)
        targets.add("codex")

    state["version"] = 2
    state["targets"] = sorted(targets)
    state["api_base"] = api_base
    write_json(paths["state"], state, mode=0o600)
    return 0


def preflight(paths: dict[str, Path], targets: set[str], replace_existing: bool) -> None:
    """Read-only checks for every requested target, so a refusal never leaves one target
    configured and the other untouched."""
    problems: list[str] = []
    if "claude" in targets:
        config = read_json_object(paths["claude"])
        env = config.get("env")
        if env is not None and not isinstance(env, dict):
            fail(f"{paths['claude']}: env must be a JSON object.")
        conflicts = claude_conflicting_env(env or {})
        if conflicts and not replace_existing:
            problems.append(claude_conflict_message(paths["claude"], conflicts))
    if "codex" in targets:
        text = paths["codex"].read_text("utf-8") if paths["codex"].exists() else ""
        conflicts = codex_conflicting_exporters(text)
        if conflicts and not replace_existing:
            problems.append(codex_conflict_message(paths["codex"], conflicts))
        hook_map = read_json_object(paths["hooks"]).get("hooks")
        if hook_map is not None and not isinstance(hook_map, dict):
            fail(f"{paths['hooks']}: hooks must be a JSON object.")
        for event_name in MANAGED_HOOK_EVENTS:
            groups = (hook_map or {}).get(event_name, [])
            if not isinstance(groups, list):
                fail(f"{paths['hooks']}: hooks.{event_name} must be a JSON array.")
    if problems:
        fail("\n".join(problems))


def claude_conflict_message(path: Path, conflicts: list[str]) -> str:
    return (
        f"{path} already routes OpenTelemetry signals elsewhere: "
        + ", ".join(conflicts)
        + ". Those entries would send full session content and the Flowlines key to that "
        "collector. Remove them, or rerun with --replace-existing-otel to replace them "
        "(the original file stays backed up)."
    )


def codex_conflict_message(path: Path, conflicts: list[str]) -> str:
    return (
        f"{path} already configures a Codex OTel exporter: "
        + ", ".join(conflicts)
        + ". Codex supports one exporter, so it would be replaced by Flowlines. Remove it, "
        "or rerun with --replace-existing-otel to replace it (the original file stays "
        "backed up)."
    )


def validate_api_base(value: str) -> str:
    """Only HTTPS may carry the key and session content; plain HTTP is for loopback only."""
    parsed = urlsplit(value.strip())
    host = parsed.hostname
    if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        fail("FLOWLINES_API_BASE_URL must be a plain https:// origin without credentials.")
    if parsed.scheme == "https" or (parsed.scheme == "http" and host in LOCAL_HOSTS):
        return value.strip().rstrip("/")
    fail("FLOWLINES_API_BASE_URL must use HTTPS (plain HTTP is allowed only for localhost).")
    raise AssertionError("unreachable")


# --- Claude Code ---------------------------------------------------------------------------


def claude_managed_env(api_base: str, api_key: str) -> dict[str, str]:
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": api_base,
        "OTEL_EXPORTER_OTLP_HEADERS": f"{FLOWLINES_HEADER}={api_key}",
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_ASSISTANT_RESPONSES": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
    }


def claude_conflicting_env(env: dict[str, Any]) -> list[str]:
    """Signal-specific OTLP settings override the generic Flowlines endpoint and merge headers,
    so they would send full content and the Flowlines key to another collector."""
    return sorted(
        key for key in env if key.startswith(OTLP_ENV_PREFIX) and key not in CLAUDE_MANAGED_ENV
    )


def configure_claude(
    paths: dict[str, Path],
    state: dict[str, Any],
    api_base: str,
    api_key: str,
    replace_existing: bool,
) -> None:
    config_path = paths["claude"]
    item = remember_original(paths, state, "claude", config_path)
    ensure_original_fields("claude", item)
    refresh_backup_if_changed(paths, state, "claude", strip_managed_claude)
    config = read_json_object(config_path)
    env = config.get("env")
    if env is None:
        env = {}
        config["env"] = env
    if not isinstance(env, dict):
        fail(f"{config_path}: env must be a JSON object.")

    conflicts = claude_conflicting_env(env)
    if conflicts and not replace_existing:
        fail(claude_conflict_message(config_path, conflicts))
    removed = item.setdefault("removed_env", {})
    for key in conflicts:
        removed.setdefault(key, env.pop(key))

    env.update(claude_managed_env(api_base, api_key))
    write_json(config_path, config, mode=0o600)
    item["installed_sha256"] = sha256_file(config_path)
    write_json(paths["state"], state, mode=0o600)


def strip_managed_claude(content: bytes, item: dict[str, Any]) -> bytes:
    config = parse_json_object(content)
    env = config.get("env")
    if isinstance(env, dict):
        for key in CLAUDE_MANAGED_ENV:
            env.pop(key, None)
        for key, value in item.get("managed_original", {}).items():
            if value is not None:
                env[key] = value
        for key, value in item.get("removed_env", {}).items():
            env.setdefault(key, value)
        if not env and item.get("env_absent_originally"):
            del config["env"]
    if not config:
        return b""
    return json_bytes(config)


# --- Codex -----------------------------------------------------------------------------------


def codex_exporter_value(api_base: str, api_key: str) -> str:
    return (
        '{ otlp-http = { endpoint = "'
        + toml_escape(f"{api_base}/v1/logs")
        + '", protocol = "binary", headers = { "'
        + FLOWLINES_HEADER
        + '" = "'
        + toml_escape(api_key)
        + '" } } }'
    )


def codex_conflicting_exporters(text: str) -> list[str]:
    """An exporter that is not ours: an inline `exporter` value without the Flowlines header, a
    dotted `exporter.*` key, or any `[otel.exporter...]` table."""
    conflicts: list[str] = []
    values = extract_toml_values(text, "otel", ("exporter",))
    exporter = values.get("exporter")
    if exporter is not None and FLOWLINES_HEADER not in exporter:
        conflicts.append("[otel] exporter")
    for name in toml_table_names(text):
        if name == CODEX_EXPORTER_TABLE or name.startswith(CODEX_EXPORTER_TABLE + "."):
            conflicts.append(f"[{name}]")
    for line in toml_table_body(text, "otel"):
        if re.match(r"^\s*exporter\s*\.", line):
            conflicts.append("[otel] exporter.*")
            break
    return conflicts


def configure_codex(
    paths: dict[str, Path],
    state: dict[str, Any],
    api_base: str,
    api_key: str,
    replace_existing: bool,
) -> None:
    config_path = paths["codex"]
    hooks_path = paths["hooks"]
    codex_item = remember_original(paths, state, "codex", config_path)
    hooks_item = remember_original(paths, state, "hooks", hooks_path)
    ensure_original_fields("codex", codex_item)
    ensure_original_fields("hooks", hooks_item)
    refresh_backup_if_changed(paths, state, "codex", strip_managed_codex)
    refresh_backup_if_changed(paths, state, "hooks", strip_managed_hooks)

    existing_toml = config_path.read_text("utf-8") if config_path.exists() else ""
    conflicts = codex_conflicting_exporters(existing_toml)
    if conflicts and not replace_existing:
        fail(codex_conflict_message(config_path, conflicts))
    merged_toml, removed_tables = remove_toml_tables(existing_toml, CODEX_EXPORTER_TABLE)
    if removed_tables:
        codex_item.setdefault("removed_toml", []).extend(removed_tables)
    merged_toml = update_toml_table(
        merged_toml,
        "otel",
        {
            "environment": '"production"',
            "log_user_prompt": "true",
            "exporter": codex_exporter_value(api_base, api_key),
        },
    )
    merged_toml = update_toml_table(merged_toml, "features", {"hooks": "true"})
    assert_valid_toml(merged_toml, config_path)
    atomic_write(config_path, merged_toml.encode(), mode=0o600)
    codex_item["installed_sha256"] = sha256_file(config_path)
    write_json(paths["state"], state, mode=0o600)

    hooks = read_json_object(hooks_path)
    hook_map = hooks.get("hooks")
    if hook_map is None:
        hook_map = {}
        hooks["hooks"] = hook_map
    if not isinstance(hook_map, dict):
        fail(f"{hooks_path}: hooks must be a JSON object.")
    command = '"$HOME/.local/lib/flowlines-agent-observability/codex-hook-relay.sh"'
    for event_name in MANAGED_HOOK_EVENTS:
        groups = hook_map.get(event_name, [])
        if not isinstance(groups, list):
            fail(f"{hooks_path}: hooks.{event_name} must be a JSON array.")
        retained = [group for group in groups if not hook_group_contains_managed_command(group)]
        retained.append({"hooks": [{"type": "command", "command": command, "timeout": 5}]})
        hook_map[event_name] = retained
    write_json(hooks_path, hooks, mode=0o600)

    curl_config = "\n".join(
        (
            f'url = "{curl_escape(f"{api_base}/v1/agent-events/codex")}"',
            'request = "POST"',
            'header = "content-type: application/json"',
            f'header = "{FLOWLINES_HEADER}: {curl_escape(api_key)}"',
            "fail",
            "",
        )
    )
    atomic_write(paths["curl"], curl_config.encode(), mode=0o600)
    hooks_item["installed_sha256"] = sha256_file(hooks_path)
    write_json(paths["state"], state, mode=0o600)


def strip_managed_codex(content: bytes, item: dict[str, Any]) -> bytes:
    text = content.decode("utf-8")
    text, _removed = remove_toml_tables(text, CODEX_EXPORTER_TABLE)
    originals = item.get("managed_original", {})
    for table, keys in CODEX_MANAGED_KEYS.items():
        text = remove_toml_table_keys(text, table, set(keys))
        restore = {
            key: value
            for key, value in originals.get(table, {}).items()
            if value is not None and key in keys
        }
        if restore:
            text = update_toml_table(text, table, restore)
        text = drop_empty_toml_table(text, table)
    for block in item.get("removed_toml", []):
        if not text.endswith("\n") and text:
            text += "\n"
        if text and not text.endswith("\n\n"):
            text += "\n"
        text += block if block.endswith("\n") else block + "\n"
    if not text.strip():
        return b""
    return text.encode("utf-8")


def strip_managed_hooks(content: bytes, item: dict[str, Any]) -> bytes:
    hooks = parse_json_object(content)
    hook_map = hooks.get("hooks")
    if isinstance(hook_map, dict):
        existed = item.get("events_original", {})
        for event_name in MANAGED_HOOK_EVENTS:
            groups = hook_map.get(event_name)
            if not isinstance(groups, list):
                continue
            retained = [group for group in groups if not hook_group_contains_managed_command(group)]
            if retained or existed.get(event_name, True):
                hook_map[event_name] = retained
            else:
                del hook_map[event_name]
        if not hook_map:
            del hooks["hooks"]
    if not hooks:
        return b""
    return json_bytes(hooks)


STRIPPERS = {
    "claude": strip_managed_claude,
    "codex": strip_managed_codex,
    "hooks": strip_managed_hooks,
}


# --- doctor / uninstall ----------------------------------------------------------------------


def doctor(paths: dict[str, Path]) -> int:
    state = read_state(paths["state"])
    targets = state.get("targets", [])
    if not targets:
        print("FAIL: Flowlines agent observability is not installed.", file=sys.stderr)
        return 1
    failures: list[str] = []

    if "claude" in targets:
        try:
            config = read_json_object(paths["claude"])
            env = config.get("env", {})
            required = (
                "CLAUDE_CODE_ENABLE_TELEMETRY",
                "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
                "OTEL_LOGS_EXPORTER",
                "OTEL_TRACES_EXPORTER",
                "OTEL_LOG_USER_PROMPTS",
                "OTEL_LOG_ASSISTANT_RESPONSES",
                "OTEL_LOG_TOOL_DETAILS",
                "OTEL_LOG_TOOL_CONTENT",
            )
            if not isinstance(env, dict) or any(not env.get(key) for key in required):
                failures.append("Claude telemetry settings are incomplete.")
            if not str(env.get("OTEL_EXPORTER_OTLP_HEADERS", "")).startswith(
                f"{FLOWLINES_HEADER}="
            ):
                failures.append("Claude Flowlines authentication header is missing.")
            conflicts = claude_conflicting_env(env) if isinstance(env, dict) else []
            if conflicts:
                failures.append(
                    "Claude settings route OpenTelemetry signals to another collector ("
                    + ", ".join(conflicts)
                    + "); full content and the Flowlines key would leave Flowlines."
                )
        except (OSError, ValueError) as error:
            failures.append(f"Claude settings are unreadable: {error}")
        check_mode(paths["claude"], failures)

    if "codex" in targets:
        try:
            codex_text = paths["codex"].read_text("utf-8")
            if tomllib is not None:
                codex = tomllib.loads(codex_text)
                otel = codex.get("otel", {})
                features = codex.get("features", {})
                exporter = otel.get("exporter")
                if otel.get("log_user_prompt") is not True or not isinstance(exporter, dict):
                    failures.append("Codex OTel settings are incomplete.")
                elif FLOWLINES_HEADER not in json.dumps(exporter):
                    failures.append("Codex OTel exporter does not send to Flowlines.")
                if features.get("hooks") is not True:
                    failures.append("Codex hooks are disabled.")
            else:
                if not toml_table_has_values(codex_text, "otel", ("log_user_prompt", "exporter")):
                    failures.append("Codex OTel settings are incomplete.")
                if not toml_table_has_values(codex_text, "features", ("hooks",)):
                    failures.append("Codex hooks are disabled.")
                conflicts = codex_conflicting_exporters(codex_text)
                if conflicts:
                    failures.append(
                        "Codex configuration contains another OTel exporter ("
                        + ", ".join(conflicts)
                        + "), which makes the file invalid or diverts telemetry."
                    )
            hooks = read_json_object(paths["hooks"]).get("hooks", {})
            for event_name in MANAGED_HOOK_EVENTS:
                groups = hooks.get(event_name, []) if isinstance(hooks, dict) else []
                if not any(hook_group_contains_managed_command(group) for group in groups):
                    failures.append(f"Codex {event_name} hook is missing.")
        except (OSError, ValueError) as error:
            failures.append(f"Codex configuration is unreadable: {error}")
        for path in (paths["codex"], paths["hooks"], paths["curl"]):
            check_mode(path, failures)
        if not paths["relay"].is_file() or not os.access(paths["relay"], os.X_OK):
            failures.append("Codex relay is missing or not executable.")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "OK: local Flowlines observability configuration is valid for "
        + ", ".join(targets)
        + "."
    )
    if "codex" in targets:
        print("NOTE: verify the user hooks are trusted in Codex /hooks.")
        pending_events = sum(1 for _ in paths["spool"].glob("*.json"))
        if pending_events > 0:
            print(
                f"NOTE: {pending_events} Codex hook event(s) are pending delivery in the local spool."
            )
    return 0


def uninstall(paths: dict[str, Path]) -> int:
    state = read_state(paths["state"])
    file_state = state.get("files", {})
    notes: list[str] = []
    for label, item in file_state.items():
        if not isinstance(item, dict) or label not in STRIPPERS:
            continue
        destination = Path(item["path"])
        if not destination.exists() or item.get("installed_sha256") is None:
            # Never written by a successful install (for example a refused one): leave it.
            continue
        backup = Path(item["backup"])
        if item.get("installed_sha256") == sha256_file(destination):
            content = backup.read_bytes() if backup.exists() else b""
        else:
            # Edited after installation: keep those edits and remove only the managed entries.
            content = STRIPPERS[label](destination.read_bytes(), item)
            notes.append(f"{destination} was edited after installation; kept those edits.")
        if not content.strip() and item.get("originally_missing"):
            destination.unlink(missing_ok=True)
        else:
            ensure_private_dir(destination.parent)
            atomic_write(destination, content, mode=int(item.get("original_mode", 0o600)))

    shutil.rmtree(paths["runtime"], ignore_errors=True)
    shutil.rmtree(paths["state_dir"], ignore_errors=True)
    for note in notes:
        print(f"NOTE: {note}")
    print("Flowlines agent observability uninstalled; original configuration restored.")
    return 0


# --- backups ---------------------------------------------------------------------------------


def remember_original(
    paths: dict[str, Path],
    state: dict[str, Any],
    label: str,
    source: Path,
) -> dict[str, Any]:
    files = state.setdefault("files", {})
    if label in files:
        return files[label]
    backup = paths["originals"] / f"{label}.original"
    item: dict[str, Any] = {"path": str(source), "backup": str(backup)}
    if source.exists():
        shutil.copyfile(source, backup)
        os.chmod(backup, 0o600)
        item["originally_missing"] = False
        item["original_mode"] = stat.S_IMODE(source.stat().st_mode)
        item["original_sha256"] = sha256_file(source)
    else:
        atomic_write(backup, b"", mode=0o600)
        item["originally_missing"] = True
        item["original_mode"] = 0o600
    files[label] = item
    write_json(paths["state"], state, mode=0o600)
    return item


def ensure_original_fields(label: str, item: dict[str, Any]) -> None:
    """Record which managed values existed before the first install, reading the pre-install
    backup rather than the live file. State written by earlier versions lacks these fields;
    deriving them from the backup keeps an upgrade from mistaking Flowlines settings that are
    already present for the user's own."""
    marker = "events_original" if label == "hooks" else "managed_original"
    if marker in item:
        return
    backup = Path(item["backup"])
    content = backup.read_bytes() if backup.exists() else b""
    if label == "claude":
        try:
            config = parse_json_object(content)
        except ValueError:
            config = {}
        env = config.get("env")
        item["env_absent_originally"] = not isinstance(env, dict)
        env = env if isinstance(env, dict) else {}
        item["managed_original"] = {key: env.get(key) for key in CLAUDE_MANAGED_ENV}
        item.setdefault("removed_env", {})
    elif label == "codex":
        text = content.decode("utf-8", errors="replace")
        item["managed_original"] = {
            table: extract_toml_values(text, table, keys)
            for table, keys in CODEX_MANAGED_KEYS.items()
        }
        item.setdefault("removed_toml", [])
    elif label == "hooks":
        try:
            hook_map = parse_json_object(content).get("hooks")
        except ValueError:
            hook_map = None
        existing = hook_map if isinstance(hook_map, dict) else {}
        item["events_original"] = {event: event in existing for event in MANAGED_HOOK_EVENTS}


def refresh_backup_if_changed(
    paths: dict[str, Path],
    state: dict[str, Any],
    label: str,
    strip: Any,
) -> None:
    """On repair, fold edits made since the last install into the backup so that uninstall
    restores them instead of the pre-install snapshot."""
    item = state["files"][label]
    installed = item.get("installed_sha256")
    destination = Path(item["path"])
    if installed is None or not destination.exists() or installed == sha256_file(destination):
        return
    atomic_write(Path(item["backup"]), strip(destination.read_bytes(), item), mode=0o600)
    write_json(paths["state"], state, mode=0o600)


# --- TOML helpers (Codex config is small and hand-edited; keep formatting) -------------------

TABLE_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$")
KEY_ASSIGNMENT = re.compile(r"^\s*([A-Za-z0-9_-]+)((?:\s*\.\s*[A-Za-z0-9_\"'-]+)*)\s*=")


def toml_table_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        match = TABLE_HEADER.match(line)
        if match:
            names.append(match.group(1).replace('"', "").replace("'", "").replace(" ", ""))
    return names


def toml_table_span(lines: list[str], table_name: str) -> tuple[int, int] | None:
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if (match := TABLE_HEADER.match(line.rstrip("\n")))
            and match.group(1).replace(" ", "") == table_name
        ),
        None,
    )
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if TABLE_HEADER.match(lines[index].rstrip("\n")):
            end = index
            break
    return start, end


def toml_table_body(text: str, table_name: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    span = toml_table_span(lines, table_name)
    if span is None:
        return []
    return lines[span[0] + 1 : span[1]]


def remove_toml_tables(text: str, prefix: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    removed: list[str] = []
    index = 0
    while index < len(lines):
        match = TABLE_HEADER.match(lines[index].rstrip("\n"))
        name = match.group(1).replace(" ", "") if match else None
        if name is not None and (name == prefix or name.startswith(prefix + ".")):
            block_end = index + 1
            while block_end < len(lines) and not TABLE_HEADER.match(lines[block_end].rstrip("\n")):
                block_end += 1
            removed.append("".join(lines[index:block_end]))
            index = block_end
            continue
        kept.append(lines[index])
        index += 1
    return "".join(kept), removed


def update_toml_table(text: str, table_name: str, values: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    span = toml_table_span(lines, table_name)
    if span is None:
        prefix = text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        entries = "".join(f"{key} = {value}\n" for key, value in values.items())
        return f"{prefix}[{table_name}]\n{entries}"
    start, end = span
    body = remove_toml_keys(lines[start + 1 : end], set(values))
    inserted = [f"{key} = {value}\n" for key, value in values.items()]
    return "".join(lines[: start + 1] + inserted + body + lines[end:])


def remove_toml_table_keys(text: str, table_name: str, keys: set[str]) -> str:
    lines = text.splitlines(keepends=True)
    span = toml_table_span(lines, table_name)
    if span is None:
        return text
    start, end = span
    return "".join(lines[: start + 1] + remove_toml_keys(lines[start + 1 : end], keys) + lines[end:])


def drop_empty_toml_table(text: str, table_name: str) -> str:
    lines = text.splitlines(keepends=True)
    span = toml_table_span(lines, table_name)
    if span is None:
        return text
    start, end = span
    if any(line.strip() and not line.lstrip().startswith("#") for line in lines[start + 1 : end]):
        return text
    return "".join(lines[:start] + lines[end:])


def remove_toml_keys(lines: list[str], keys: set[str]) -> list[str]:
    """Drop `key = ...` and dotted `key.sub = ...` assignments, including multi-line values."""
    retained: list[str] = []
    index = 0
    while index < len(lines):
        match = KEY_ASSIGNMENT.match(lines[index])
        if match is None or match.group(1) not in keys:
            retained.append(lines[index])
            index += 1
            continue
        balance = bracket_balance(lines[index].split("=", 1)[1])
        index += 1
        while balance > 0 and index < len(lines):
            balance += bracket_balance(lines[index])
            index += 1
    return retained


def extract_toml_values(text: str, table_name: str, keys: tuple[str, ...]) -> dict[str, str | None]:
    """Raw right-hand sides of plain `key = value` assignments in a table (None when absent)."""
    lines = toml_table_body(text, table_name)
    values: dict[str, str | None] = {key: None for key in keys}
    index = 0
    while index < len(lines):
        match = KEY_ASSIGNMENT.match(lines[index])
        if match is None or match.group(2) or match.group(1) not in keys:
            index += 1
            continue
        collected = [lines[index].split("=", 1)[1]]
        balance = bracket_balance(collected[0])
        index += 1
        while balance > 0 and index < len(lines):
            collected.append(lines[index])
            balance += bracket_balance(lines[index])
            index += 1
        values[match.group(1)] = "".join(collected).strip()
    return values


def toml_table_has_values(text: str, table_name: str, keys: tuple[str, ...]) -> bool:
    section = toml_table_body(text, table_name)
    return all(any(re.match(rf"^\s*{re.escape(key)}\s*=", line) for line in section) for key in keys)


def assert_valid_toml(text: str, path: Path) -> None:
    if tomllib is None:
        return
    try:
        tomllib.loads(text)
    except ValueError as error:
        fail(f"Refusing to write invalid Codex TOML to {path}: {error}")


def bracket_balance(value: str) -> int:
    # This covers the inline-table/list forms used by Codex configuration.
    return value.count("{") + value.count("[") - value.count("}") - value.count("]")


# --- misc ------------------------------------------------------------------------------------


def hook_group_contains_managed_command(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    handlers = group.get("hooks", [])
    if not isinstance(handlers, list):
        return False
    return any(
        isinstance(handler, dict)
        and MANAGED_HOOK_COMMAND_FRAGMENT in str(handler.get("command", ""))
        for handler in handlers
    )


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json_object(path)


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return parse_json_object(path.read_bytes())
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def parse_json_object(content: bytes) -> dict[str, Any]:
    if not content.strip():
        return {}
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("must contain a JSON object.")
    return value


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_json(path: Path, value: dict[str, Any], mode: int) -> None:
    atomic_write(path, json_bytes(value), mode=mode)


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    ensure_private_dir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_mode(path: Path, failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"{path} is missing.")
        return
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        failures.append(f"{path} must use mode 0600.")


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def curl_escape(value: str) -> str:
    return toml_escape(value).replace("\n", "").replace("\r", "")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())

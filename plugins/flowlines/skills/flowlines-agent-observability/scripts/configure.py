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

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 is still common on supported machines.
    tomllib = None  # type: ignore[assignment]

MANAGED_HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse", "Stop")
MANAGED_HOOK_COMMAND_FRAGMENT = "flowlines-agent-observability/codex-hook-relay.sh"


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
    api_base = os.environ.get("FLOWLINES_API_BASE_URL", "https://api.flowlines.ai").rstrip("/")
    if not api_key or "\n" in api_key or "\r" in api_key:
        fail("FLOWLINES_API_KEY must be a non-empty single-line value.")
    if not api_base.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        fail("FLOWLINES_API_BASE_URL must use HTTPS (localhost is allowed for development).")
    if not relay_source.is_file():
        fail("Codex relay source was not found.")

    ensure_private_dir(paths["state_dir"])
    ensure_private_dir(paths["originals"])
    ensure_private_dir(paths["spool"])
    ensure_private_dir(paths["runtime"])
    state = read_state(paths["state"])
    targets = set(state.get("targets", []))

    if target in ("claude", "both"):
        configure_claude(paths, state, api_base, api_key)
        targets.add("claude")
    if target in ("codex", "both"):
        shutil.copyfile(relay_source, paths["relay"])
        os.chmod(paths["relay"], 0o700)
        configure_codex(paths, state, api_base, api_key)
        targets.add("codex")

    state["version"] = 1
    state["targets"] = sorted(targets)
    state["api_base"] = api_base
    write_json(paths["state"], state, mode=0o600)
    return 0


def configure_claude(
    paths: dict[str, Path],
    state: dict[str, Any],
    api_base: str,
    api_key: str,
) -> None:
    config_path = paths["claude"]
    remember_original(paths, state, "claude", config_path)
    config = read_json_object(config_path)
    env = config.get("env")
    if env is None:
        env = {}
        config["env"] = env
    if not isinstance(env, dict):
        fail(f"{config_path}: env must be a JSON object.")
    env.update(
        {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "none",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_EXPORTER_OTLP_ENDPOINT": api_base,
            "OTEL_EXPORTER_OTLP_HEADERS": f"x-flowlines-api-key={api_key}",
            "OTEL_LOG_USER_PROMPTS": "1",
            "OTEL_LOG_ASSISTANT_RESPONSES": "1",
            "OTEL_LOG_TOOL_DETAILS": "1",
            "OTEL_LOG_TOOL_CONTENT": "1",
        }
    )
    write_json(config_path, config, mode=0o600)
    state["files"]["claude"]["installed_sha256"] = sha256_file(config_path)
    write_json(paths["state"], state, mode=0o600)


def configure_codex(
    paths: dict[str, Path],
    state: dict[str, Any],
    api_base: str,
    api_key: str,
) -> None:
    config_path = paths["codex"]
    hooks_path = paths["hooks"]
    remember_original(paths, state, "codex", config_path)
    remember_original(paths, state, "hooks", hooks_path)

    existing_toml = config_path.read_text("utf-8") if config_path.exists() else ""
    exporter = (
        '{ otlp-http = { endpoint = "'
        + toml_escape(f"{api_base}/v1/logs")
        + '", protocol = "binary", headers = { "x-flowlines-api-key" = "'
        + toml_escape(api_key)
        + '" } } }'
    )
    merged_toml = update_toml_table(
        existing_toml,
        "otel",
        {
            "environment": '"production"',
            "log_user_prompt": "true",
            "exporter": exporter,
        },
    )
    merged_toml = update_toml_table(merged_toml, "features", {"hooks": "true"})
    if tomllib is not None:
        try:
            tomllib.loads(merged_toml)
        except ValueError as error:
            fail(f"Refusing to write invalid Codex TOML: {error}")
    atomic_write(config_path, merged_toml.encode(), mode=0o600)
    state["files"]["codex"]["installed_sha256"] = sha256_file(config_path)
    write_json(paths["state"], state, mode=0o600)

    hooks = read_json_object(hooks_path)
    hook_map = hooks.setdefault("hooks", {})
    if not isinstance(hook_map, dict):
        fail(f"{hooks_path}: hooks must be a JSON object.")
    command = '"$HOME/.local/lib/flowlines-agent-observability/codex-hook-relay.sh"'
    for event_name in MANAGED_HOOK_EVENTS:
        groups = hook_map.get(event_name, [])
        if not isinstance(groups, list):
            fail(f"{hooks_path}: hooks.{event_name} must be a JSON array.")
        retained = [
            group
            for group in groups
            if not hook_group_contains_managed_command(group)
        ]
        retained.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 5,
                    }
                ]
            }
        )
        hook_map[event_name] = retained
    write_json(hooks_path, hooks, mode=0o600)

    curl_config = "\n".join(
        (
            f'url = "{curl_escape(f"{api_base}/v1/agent-events/codex")}"',
            'request = "POST"',
            'header = "content-type: application/json"',
            f'header = "x-flowlines-api-key: {curl_escape(api_key)}"',
            "fail",
            "",
        )
    )
    atomic_write(paths["curl"], curl_config.encode(), mode=0o600)
    state["files"]["hooks"]["installed_sha256"] = sha256_file(hooks_path)
    write_json(paths["state"], state, mode=0o600)


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
                "x-flowlines-api-key="
            ):
                failures.append("Claude Flowlines authentication header is missing.")
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
                if otel.get("log_user_prompt") is not True or not isinstance(
                    otel.get("exporter"), dict
                ):
                    failures.append("Codex OTel settings are incomplete.")
                if features.get("hooks") is not True:
                    failures.append("Codex hooks are disabled.")
            else:
                if not toml_table_has_values(
                    codex_text,
                    "otel",
                    ("log_user_prompt", "exporter"),
                ):
                    failures.append("Codex OTel settings are incomplete.")
                if not toml_table_has_values(codex_text, "features", ("hooks",)):
                    failures.append("Codex hooks are disabled.")
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
    conflicts: list[str] = []
    for label, item in file_state.items():
        if not isinstance(item, dict):
            continue
        destination = Path(item["path"])
        expected_hash = item.get("installed_sha256") or item.get("original_sha256")
        if destination.exists() and expected_hash != sha256_file(destination):
            conflicts.append(
                f"{destination} changed after installation; original remains at {item['backup']}."
            )
    if conflicts:
        for conflict in conflicts:
            print(f"REFUSED: {conflict}", file=sys.stderr)
        return 1

    for item in file_state.values():
        if not isinstance(item, dict):
            continue
        destination = Path(item["path"])
        if item.get("originally_missing"):
            destination.unlink(missing_ok=True)
        else:
            backup = Path(item["backup"])
            ensure_private_dir(destination.parent)
            shutil.copyfile(backup, destination)
            os.chmod(destination, int(item.get("original_mode", 0o600)))

    shutil.rmtree(paths["runtime"], ignore_errors=True)
    shutil.rmtree(paths["state_dir"], ignore_errors=True)
    print("Flowlines agent observability uninstalled; original configuration restored.")
    return 0


def remember_original(
    paths: dict[str, Path],
    state: dict[str, Any],
    label: str,
    source: Path,
) -> None:
    files = state.setdefault("files", {})
    if label in files:
        return
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


def update_toml_table(text: str, table_name: str, values: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    header_pattern = re.compile(rf"^\s*\[{re.escape(table_name)}\]\s*(?:#.*)?$")
    start = next(
        (index for index, line in enumerate(lines) if header_pattern.match(line.rstrip("\n"))),
        None,
    )
    if start is None:
        prefix = text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        entries = "".join(f"{key} = {value}\n" for key, value in values.items())
        return f"{prefix}[{table_name}]\n{entries}"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^\s*\[", lines[index]):
            end = index
            break
    body = remove_toml_keys(lines[start + 1 : end], set(values))
    inserted = [f"{key} = {value}\n" for key, value in values.items()]
    return "".join(lines[: start + 1] + inserted + body + lines[end:])


def remove_toml_keys(lines: list[str], keys: set[str]) -> list[str]:
    retained: list[str] = []
    index = 0
    assignment = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
    while index < len(lines):
        match = assignment.match(lines[index])
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


def toml_table_has_values(text: str, table_name: str, keys: tuple[str, ...]) -> bool:
    lines = text.splitlines()
    header = re.compile(rf"^\s*\[{re.escape(table_name)}\]\s*(?:#.*)?$")
    start = next(
        (index for index, line in enumerate(lines) if header.match(line)),
        None,
    )
    if start is None:
        return False
    section: list[str] = []
    for line in lines[start + 1 :]:
        if re.match(r"^\s*\[", line):
            break
        section.append(line)
    return all(
        any(re.match(rf"^\s*{re.escape(key)}\s*=", line) for line in section)
        for key in keys
    )


def bracket_balance(value: str) -> int:
    # This covers the inline-table/list forms used by Codex configuration.
    return value.count("{") + value.count("[") - value.count("}") - value.count("]")


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
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def write_json(path: Path, value: dict[str, Any], mode: int) -> None:
    atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        mode=mode,
    )


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

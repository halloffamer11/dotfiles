"""Read the global Harness inventories and interpret the Belt declarations."""

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

HOME = Path.home().resolve()  # PATH entries and links are compared resolved
MCP_FILES = {
    "claude": (".claude.json", "mcpServers"),
    "codex": (".codex/config.toml", "mcp_servers"),
    "agy": (".gemini/config/mcp_config.json", "mcpServers"),
}
SKILL_DIRS = {
    "claude": [".claude/skills"],
    "codex": [".agents/skills", ".codex/skills"],
    "agy": [".gemini/config/skills"],
}
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
# Each Platform also answers to the families it belongs to: Omarchy is a Linux.
PLATFORMS = {"macos": {"macos"}, "linux": {"linux"}, "omarchy": {"omarchy", "linux"}}


def table(path, key):
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        data = tomllib.load(stream) if path.suffix == ".toml" else json.load(stream)
    entries = data.get(key, {})
    if not isinstance(entries, dict):
        raise ValueError(f"Expected a table in {path.name}")
    return entries


def installed_harnesses():
    """The Harnesses with a CLI on PATH. MCP entries go only to these."""
    return {harness for harness in MCP_FILES if shutil.which(harness)}


def external(path):
    """Names that another tool owns on this Machine: {"mcp": set, "skills": set}."""
    if not path.exists():
        return {"mcp": set(), "skills": set()}
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    names = {}
    for key in ("mcp", "skills"):
        values = data.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Expected a list of names for {key} in {path.name}")
        names[key] = set(values)
    return names


def edited_targets(status, managed):
    """Targets edited since the last apply: column 1 of `chezmoi status`.

    A modify_ script owns one entry of a file that its Harness also writes, so a
    Harness edit to that file is expected and is not a local edit.
    """
    partial = {target for target, paths in json.loads(managed or "{}").items()
               if Path(paths.get("sourceRelative", "")).name.startswith("modify_")}
    return [line[3:] for line in status.splitlines()
            if line and line[0] != " " and line[3:] not in partial]


def batch_ssh(repo):
    """Make Git's ssh fail instead of prompt, unless the user chose an ssh command.

    A configured command can be any shell form (a wrapper, an env prefix, a
    quoted path), so it is left exactly as it is.
    """
    if os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH"):
        return {}
    configured = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=repo,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=5).stdout.strip()
    return {} if configured else {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def reserved_skills(platform):
    reserved = {"synced", ".system"}
    if platform == "omarchy":
        reserved.update(("omarchy", "omarchy-app", "diagnose-crash"))
    return reserved


def selections(data):
    selected = []
    names = set()
    for pack in data["selectedPacks"]:
        if pack not in data["packs"]:
            continue  # Retired selections stay installed and fleet-check reports them.
        entry = data["packs"][pack]
        repo = entry["repo"]
        if not isinstance(repo, str) or not repo or repo.startswith("-"):
            raise ValueError(f"Invalid source for Pack {pack}")
        available = {name for name, enabled in entry["skills"].items() if enabled is True}
        skills = data["skillSelection"].get(pack, sorted(available))
        if not isinstance(skills, list):
            raise ValueError(f"Invalid skill selection for Pack {pack}")
        skills = [name for name in skills if name in available]
        for name in skills:
            canonical = re.sub(r"-+", "-", name.lower().strip(".-"))[:255]
            if not NAME.fullmatch(name) or canonical != name or name in names | reserved_skills(data["platform"]):
                raise ValueError(f"Reserved, duplicate or invalid skill in Pack {pack}")
            names.add(name)
        if skills:
            selected.append((repo, skills))
    return selected


def mcp_arguments(harness, name, item, platform):
    """Return add arguments and an optional reason the entry cannot be installed."""
    allowed = {"command", "args", "url", "secrets", "platforms", "requires", "enabled"}
    if not NAME.fullmatch(name) or item.keys() - allowed:
        raise ValueError(f"Invalid MCP declaration: {name}")
    for key in ("platforms", "args", "secrets"):
        values = item.get(key, [])
        if not isinstance(values, list) or not all(isinstance(s, str) and "\0" not in s for s in values):
            raise ValueError(f"Invalid {key} for MCP {name}")
    if not isinstance(item.get("enabled", True), bool):
        raise ValueError(f"Invalid enabled for MCP {name}")
    if item.get("enabled") is False:
        return None, "disabled"
    if item.get("platforms") and not PLATFORMS.get(platform, {platform}) & set(item["platforms"]):
        return None, "other Platform"
    if item.get("requires") and not shutil.which(item["requires"]):
        return None, f"requires {item['requires']}"
    command, url = item.get("command"), item.get("url")
    if bool(command) == bool(url):
        raise ValueError(f"MCP {name} needs one command or URL")
    env = item.get("secrets", [])
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var) for var in env):
        raise ValueError(f"MCP {name} needs environment variable names")
    if url:
        address = urlsplit(url)
        if address.scheme not in {"http", "https"} or not address.hostname or address.username is not None or item.get("args"):
            raise ValueError(f"Invalid HTTP declaration for MCP {name}")
    if env and not (url and harness == "codex" and len(env) == 1):
        return None, "no verified secret reference for this transport"
    scope = ["-s", "user"] if harness == "claude" else []
    if command:
        if command.startswith("-") or not shutil.which(command):
            raise ValueError(f"Missing or invalid command for MCP {name}")
        return [*scope, name, "--", command, *item.get("args", [])], None
    if harness == "codex":
        return [name, "--url", url, *(["--bearer-token-env-var", env[0]] if env else [])], None
    return [*scope, "--transport" if harness == "claude" else "--type", "http", name, url], None

#!/usr/bin/env python3
"""Offline stand-ins. Persist only the public file formats consumed by the Belt."""
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

home = Path.home()
assert Path(os.environ["SMOKE_ROOT"]) in home.parents
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (home / "calls").open("a") as log:
    print(json.dumps([name, *args]), file=log)
if name == "mise":
    assert args == ["install"]
    assert (home / ".config/mise/conf.d/50-belt.toml").is_file()
elif name == "skills":
    if args != ["update", "-g", "-y"]:
        assert args[:2] == ["add", str(Path(os.environ["SMOKE_ROOT"]) / "pack")]
        assert args[2:5] == ["-g", "-y", "-s"]
        assert args[-4:] == ["-a", "claude-code", "codex", "antigravity-cli"]
        for skill in args[5:-4]:
            source = Path(args[1]) / "skills" / skill / "SKILL.md"
            for folder in (".agents/skills", ".claude/skills", ".gemini/config/skills"):
                target = home / folder / skill / "SKILL.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
elif name in {"claude", "codex", "agy"}:
    assert sys.stdin.read() == ""
    assert args[0] == "mcp"
    action = args[1]
    args = args[2:]
    if name == "claude":
        assert args[:2] == ["-s", "user"]
        args = args[2:]
        path = Path(os.environ.get("CLAUDE_CONFIG_DIR", home)) / ".claude.json"
    elif name == "codex":
        path = home / ".codex/config.toml"
    else:
        path = home / ".gemini/config/mcp_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    codex = name == "codex"
    key = "mcp_servers" if codex else "mcpServers"
    config = {}
    if path.exists():
        config = (tomllib if codex else json).loads(path.read_text())
    entries = config.setdefault(key, {})
    if action == "remove":
        del entries[args[0]]
    else:
        assert action == "add"
        if args[:1] in (["--type"], ["--transport"]):
            transport, server, *values = args[1:]
            assert transport == "http"
            entry = {"url": values[0]}
        else:
            server, sep, *values = args
            if sep == "--url":
                entry = {"url": values[0]}
                if len(values) > 1:
                    assert values[1] == "--bearer-token-env-var"
                    entry["bearer_token_env_var"] = values[2]
            else:
                assert sep == "--"
                entry = {"command": values[0], "args": values[1:]}
        if name == "claude":
            assert server not in entries
        entries[server] = entry
    if codex:
        path.write_text("".join(f"[mcp_servers.{json.dumps(server)}]\n" +
                                "".join(f"{k} = {json.dumps(v)}\n" for k, v in value.items())
                                for server, value in entries.items()))
    else:
        path.write_text(json.dumps(config))

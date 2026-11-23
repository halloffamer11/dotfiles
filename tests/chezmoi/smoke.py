"""Exercise the installed commands in a disposable HOME with a local Git upstream."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import tomllib

REPO = Path(__file__).resolve().parents[2]


def smoke(temp):
    home, upstream, pack, bins = [temp / n for n in ("home", "upstream", "pack", "bin")]
    home.mkdir()
    bins.mkdir()
    for name in ("git", "sh", "env", "python3"):
        (bins / name).symlink_to(shutil.which(name))
    stub = REPO / "tests/chezmoi/stub.py"
    for name in ("mise", "skills", "claude", "codex", "agy", "notify-send", "osascript", "playwright-mcp", "pacman"):
        (bins / name).symlink_to(stub)
    env = {"PATH": str(bins), "HOME": str(home), "SMOKE_ROOT": str(temp), "TMPDIR": str(temp),
           "FIXTURE_TOKEN": "fixture-only-value", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
           "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
    binary = shutil.which("chezmoi")
    if binary and subprocess.run([binary, "--version"], capture_output=True).returncode != 0:
        binary = None  # for example a stale mise shim for a tool that no config declares
    if not binary:
        mise = shutil.which("mise")
        if not mise:
            raise SystemExit("test-chezmoi requires chezmoi or mise")
        # Install the test runner in its own HOME. Expose no caller XDG or Harness state.
        tool_home = temp / "tool-home"
        tool_home.mkdir()
        binary = subprocess.check_output([mise, "exec", "chezmoi@latest", "--", "which", "chezmoi"],
                                         cwd=tool_home, env={"HOME": str(tool_home), "PATH": os.defpath},
                                         text=True).strip()
    (bins / "chezmoi").symlink_to(binary)

    def run(*args, cwd=home, stdin="", success=True):
        proc = subprocess.run(args, cwd=cwd, env=env, input=stdin, text=True, capture_output=True,
                              start_new_session=True, timeout=60)
        if (proc.returncode == 0) != success:
            raise AssertionError(f"{args} returned {proc.returncode}\n{proc.stdout}{proc.stderr}")
        return proc.stdout

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def commit(repo):
        run("git", "add", ".", cwd=repo)
        run("git", "commit", "-qm", "Fixture", cwd=repo)

    def cfg(path):
        return json.loads((home / path).read_text())

    source = home / ".local/share/chezmoi"
    site = home / ".config/fleet/site"
    (home / ".local/share/omarchy").mkdir(parents=True)
    for rel in (".chezmoiroot", "home", "references"):
        src, dest = REPO / rel, upstream / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copyfile(src, dest)
    for skill in ("sample", "site", "site-edit"):
        write(pack / "skills" / skill / "SKILL.md", f"---\nname: {skill}\n---\nFixture\n")
    run("git", "init", "-q", "-b", "main", cwd=pack)
    commit(pack)
    commit_pack = f'repo = {json.dumps(str(pack))}\n'
    write(upstream / "home/.chezmoidata/packs.toml",
          "[packs.core]\n" + commit_pack + "skills = { sample = true }\n")
    write(site / "skills.toml", "[packs.extra]\n" + commit_pack + "skills = { site = true }\n")
    write(site / "rules.md", "Fixture Site kit rules.\n")
    write(site / "mise.toml", '[tools]\nfixture = "latest"\n')
    write(site / "ignore", ".ignored-fixture\n")
    write(upstream / "home/dot_ignored-fixture", "skip\n")
    run("git", "init", "-q", "-b", "main", cwd=upstream)
    commit(upstream)
    run("git", "clone", "-q", str(upstream), str(source))
    run("git", "config", "pull.rebase", "true", cwd=source)
    run("git", "config", "rebase.autoStash", "true", cwd=source)
    hooks = [".claude/settings.json", ".codex/hooks.json", ".gemini/config/hooks.json"]
    other = {"hooks": [{"type": "command", "command": "other-tool"}]}
    for hook in hooks:
        value = {"other-tool" if "gemini" in hook else "hooks": {"SessionStart": [other]}}
        write(home / hook, json.dumps(value))
    managed_skill = home / ".agents/skills/sample/SKILL.md"
    write(managed_skill, "hand-edited skill\n")
    backup = temp / "backup.md"
    shutil.copy2(managed_skill, backup)
    run("chezmoi", "init", "--promptDefaults", "--no-tty", "--promptString",
        "T3 Antigravity instance IDs (space-separated)=antigravity secondary")
    run("chezmoi", "apply", "--no-tty")
    assert managed_skill.read_text() == (pack / "skills/sample/SKILL.md").read_text()
    saved = managed_skill.read_bytes()
    shutil.copy2(backup, managed_skill)
    assert managed_skill.read_text() == "hand-edited skill\n"
    managed_skill.write_bytes(saved)
    rules = [(home / p).read_bytes() for p in (".claude/CLAUDE.md", ".codex/AGENTS.md", ".gemini/AGENTS.md")]
    assert len(set(rules)) == 1 and rules[0].endswith(b"Fixture Site kit rules.\n") and len(rules[0]) < 24000
    assert not (home / ".ignored-fixture").exists()
    assert (home / ".config/mise/conf.d/90-site.toml").resolve() == site / "mise.toml"
    link = home / ".t3/userdata/providers/antigravity" / hashlib.sha256(b"antigravity").hexdigest() / "config/mcp_config.json"
    secondary = link.parents[2] / hashlib.sha256(b"secondary").hexdigest() / "config/mcp_config.json"
    for profile in (link, secondary):
        assert profile.is_symlink() and profile.resolve() == home / ".gemini/config/mcp_config.json"
    assert json.loads(link.read_text())["mcpServers"]["playwright"]["args"] == ["--isolated", "--headless"]
    for hook in hooks:
        value = cfg(hook)
        key = "other-tool" if "gemini" in hook else "hooks"
        assert other in value[key]["SessionStart"] and "fleet-check" in json.dumps(value)
    installed = tomllib.loads((home / ".config/mise/conf.d/50-belt.toml").read_text())["tools"]
    assert {"chezmoi", "git-lfs", "npm:skills"} <= installed.keys()
    assert "eza" not in installed  # pacman provides it on Omarchy
    omarchy = Path("/etc/mise/conf.d/omarchy-tools.toml")
    if omarchy.exists():
        assert not installed.keys() & tomllib.loads(omarchy.read_text())["tools"].keys()
    mac = ["--override-data", '{"platform":"macos"}']
    mac_config = run("chezmoi", *mac, "cat", str(home / ".config/mise/conf.d/50-belt.toml"))
    assert {"claude", "codex", "antigravity-cli", "eza"} <= tomllib.loads(mac_config)["tools"].keys()
    plist = run("chezmoi", *mac, "cat", str(home / "Library/LaunchAgents/org.dotfiles.fleet-sync.plist"))
    assert plistlib.loads(plist.encode())["StartInterval"] == 14400

    check, sync = (home / ".local/bin" / name for name in ("fleet-check", "fleet-sync"))
    assert run(check, "--brief") == ""
    assert json.loads(run(check, "--brief", "--format", "agy", stdin='{"workspacePaths":[]}')) == {}
    before = (home / "calls").read_bytes()
    assert run("chezmoi", "status") == ""
    run("chezmoi", "apply", "--no-tty")
    assert (home / "calls").read_bytes() == before and run("chezmoi", "status") == ""
    print("ok: init, both Platform manifests, rules, hooks, profile link, skill backup/restore and clean second apply")

    write(site / "skills.toml", "[packs.extra]\n" + commit_pack + "skills = { site = true, site-edit = true }\n")
    write(site / "mise.toml", '[tools]\nfixture = "1"\n')
    write(site / "mcp.toml", '[mcp.playwright]\nargs = ["--isolated", "--headless", "--site"]\n'
          '[mcp.private]\ncommand = "git"\nsecrets = ["FIXTURE_TOKEN"]\n'
          '[mcp.remote]\nurl = "https://example.invalid/mcp"\nsecrets = ["FIXTURE_TOKEN"]\n')
    agy_path = home / ".gemini/config/mcp_config.json"
    other_mcp = {"command": "other-tool"}
    agy = cfg(agy_path)
    agy["mcpServers"]["ad-hoc"] = other_mcp
    write(agy_path, json.dumps(agy))
    write(home / ".claude/skills/ad-hoc/SKILL.md", "other-tool")
    run("chezmoi", "apply", "--no-tty")
    assert (home / ".agents/skills/site-edit/SKILL.md").exists()
    assert (home / "calls").read_text().splitlines().count('["mise", "install"]') == 2
    for path in (home / ".claude.json", home / ".codex/config.toml", agy_path):
        assert env["FIXTURE_TOKEN"] not in path.read_text()
        assert "--site" in path.read_text() and "private" not in path.read_text()
    assert "bearer_token_env_var" in (home / ".codex/config.toml").read_text()
    assert cfg(agy_path)["mcpServers"]["ad-hoc"] == other_mcp
    report = run(check, "--brief")
    for expected in ("Site kit overrides MCP playwright", "undeclared skill ad-hoc",
                     "undeclared MCP ad-hoc", "skipped MCP private", "agy: skipped MCP remote"):
        assert expected in report, report
    print("ok: Site kit override, undeclared skill and MCP preservation, environment references and skipped transports")

    state = home / ".local/state/fleet/last-sync"
    def stopped(expected):
        before = (home / "calls").read_text().count('["skills", "update"')
        run(sync, success=False)
        assert expected in state.read_text(), state.read_text()
        assert (home / "calls").read_text().count('["skills", "update"') == before

    run(sync)
    assert state.read_text().endswith(" ok\n")
    # A Harness writes its own settings file. Only our hook entry is ours.
    settings = cfg(".claude/settings.json")
    settings["model"] = "harness-choice"
    write(home / ".claude/settings.json", json.dumps(settings))
    assert "edited deployed" not in run(check, "--brief")
    run(sync)
    assert state.read_text().endswith(" ok\n") and cfg(".claude/settings.json")["model"] == "harness-choice"
    write(source / "dirty", "pending")
    stopped("dirty source")
    (source / "dirty").unlink()
    deployed = home / ".claude/CLAUDE.md"
    original = deployed.read_bytes()
    deployed.write_text("local edit")
    stopped("edited deployed")
    assert deployed.read_text() == "local edit"
    deployed.write_bytes(original)
    target = os.readlink(link)
    link.unlink()
    link.write_text("{}")
    stopped("edited deployed")
    assert "missing or replaced link" in run(check, "--brief")
    link.unlink()
    link.symlink_to(target)
    # Column two means pending work. The timer must apply it.
    write(site / "rules.md", "Changed Site kit rules.\n")
    run(sync)
    assert deployed.read_text().endswith("Changed Site kit rules.\n")
    write(upstream / "home/dot_fast-forward", "pulled\n")
    commit(upstream)
    run(sync)
    assert (home / ".fast-forward").read_text() == "pulled\n"
    write(upstream / "home/dot_upstream-fixture", "upstream\n")
    commit(upstream)
    write(source / "local-commit", "ahead\n")
    commit(source)
    stopped("git pull --ff-only")
    assert not (home / ".upstream-fixture").exists()
    report = run(check, "--brief")
    assert "1 unpushed" in report and "1 upstream" in report and "last fleet-sync" in report
    print("ok: no-terminal sync, dirty source, edited target, replaced link, pending target and divergent branch")

    # Duplicates: a Platform wrapper owned by pacman is not reported; a second own copy is.
    folders = [temp / n for n in ("platform-a", "platform-b", "own")]
    for folder in folders:
        folder.mkdir()
    for folder, tool in ((folders[0], "wrapped"), (folders[1], "wrapped"), (folders[0], "twice"), (folders[2], "twice")):
        write(folder / tool, "#!/bin/sh\n")
        (folder / tool).chmod(0o755)
    env["PATH"] = os.pathsep.join([str(bins), *map(str, folders)])
    report = run(check, "--brief")
    assert "duplicate wrapped" not in report and "duplicate twice" in report, report
    print("ok: duplicate commands, with the Platform's own wrappers left out")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="fleet-smoke-") as folder:
        smoke(Path(folder).resolve())

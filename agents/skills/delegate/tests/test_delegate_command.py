#!/usr/bin/env python3
"""Tests for the `delegate` command on PATH (ticket 34).

Run: python3 tests/test_delegate_command.py

Every case runs the real script against a temp checkout that holds nothing but
the layout the script walks up through, with `make` and the dashboard stubbed,
so no wizard, no dashboard and no terminal is ever started.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so the invoking
# checkout is never the project a case finds.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
CHECKOUT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
COMMAND = os.path.join(CHECKOUT, "stow", "delegate", ".local", "bin", "delegate")

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def executable(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_checkout(td):
    """A copy of the layout the command walks up through: the command itself at
    its stow path, a stub dashboard where the real one sits, and a stub `make`
    on PATH. Each stub writes its argv and its working directory as JSON."""
    checkout = os.path.join(td, "checkout")
    bindir = os.path.join(checkout, "stow", "delegate", ".local", "bin")
    tools = os.path.join(checkout, "tools", "delegate-dashboard")
    stubs = os.path.join(td, "stubs")
    for path in (bindir, tools, stubs):
        os.makedirs(path)
    shutil.copy(COMMAND, os.path.join(bindir, "delegate"))
    record_to = os.path.join(td, "ran.json")
    executable(os.path.join(stubs, "make"), (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"json.dump({{'program': 'make', 'argv': sys.argv[1:], 'cwd': os.getcwd()}}, "
        f"open({record_to!r}, 'w'))\n"
        "sys.exit(7)\n"
    ))
    executable(os.path.join(tools, "dashboard.py"), (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"json.dump({{'program': 'dashboard', 'argv': sys.argv[1:], 'cwd': os.getcwd()}}, "
        f"open({record_to!r}, 'w'))\n"
        "sys.exit(9)\n"
    ))
    env = os.environ.copy()
    env["PATH"] = stubs + os.pathsep + os.path.dirname(sys.executable)
    return checkout, os.path.join(bindir, "delegate"), env, record_to


def run(command, args, env, cwd):
    return subprocess.run([command, *args], capture_output=True, text=True, env=env, cwd=cwd)


def ran(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------------------
# 1. No argument, -h, --help: the two lines and nothing run.
with tempfile.TemporaryDirectory() as td:
    _checkout, command, env, record_to = make_checkout(td)
    results = {args and args[0] or "": run(command, list(args), env, td)
               for args in ((), ("-h",), ("--help",))}
    record(
        "1 no argument, -h and --help print the two lines and exit 0",
        all(res.returncode == 0 for res in results.values())
        and all("delegate global" in res.stdout and "delegate project" in res.stdout
                for res in results.values())
        and len({res.stdout for res in results.values()}) == 1
        and ran(record_to) is None,
        repr({key: (res.returncode, res.stdout[:60]) for key, res in results.items()}),
    )

# -------------------------------------------------------------
# 2. An unknown word: the same two lines, exit 2, nothing run.
with tempfile.TemporaryDirectory() as td:
    _checkout, command, env, record_to = make_checkout(td)
    res = run(command, ["wizard"], env, td)
    record(
        "2 an unknown word names itself, prints the two lines and exits 2",
        res.returncode == 2 and "wizard" in res.stderr
        and "delegate global" in res.stderr and "delegate project" in res.stderr
        and ran(record_to) is None,
        f"rc={res.returncode} stderr={res.stderr!r}",
    )

# -------------------------------------------------------------
# 3. `delegate global` runs the wizard target in the command's own checkout,
#    from any directory, and passes the rest through as WIZARD_ARGS.
with tempfile.TemporaryDirectory() as td:
    checkout, command, env, record_to = make_checkout(td)
    elsewhere = os.path.join(td, "elsewhere")
    os.makedirs(elsewhere)
    res = run(command, ["global", "--plain", "--tiers-from", "/tmp/a b.txt"], env, elsewhere)
    called = ran(record_to)
    record(
        "3 delegate global runs the wizard target in its own checkout",
        res.returncode == 7 and called is not None
        and called["argv"][:3] == ["-C", os.path.realpath(checkout), "delegate-wizard"]
        and called["argv"][3] == "WIZARD_ARGS=--plain --tiers-from '/tmp/a b.txt'",
        repr(called),
    )

# -------------------------------------------------------------
# 4. `delegate project` opens the dashboard for the current directory's project.
with tempfile.TemporaryDirectory() as td:
    checkout, command, env, record_to = make_checkout(td)
    project = os.path.join(td, "project", "src")
    os.makedirs(project)
    open(os.path.join(td, "project", ".git"), "w").close()
    res = run(command, ["project", "--json"], env, project)
    called = ran(record_to)
    record(
        "4 delegate project opens the dashboard for this directory's project",
        res.returncode == 9 and called is not None
        and called["argv"] == ["--cwd", os.path.realpath(project), "--json"],
        f"rc={res.returncode} called={called}",
    )

# -------------------------------------------------------------
# 5. Outside a Git project: one line, exit 1, and no dashboard started.
with tempfile.TemporaryDirectory() as td:
    _checkout, command, env, record_to = make_checkout(td)
    outside = os.path.join(td, "outside")
    os.makedirs(outside)
    res = run(command, ["project"], env, outside)
    record(
        "5 outside a Git project it says so, exits 1 and starts nothing",
        res.returncode == 1 and len(res.stderr.strip().splitlines()) == 1
        and "no Git project" in res.stderr and ran(record_to) is None,
        f"rc={res.returncode} stderr={res.stderr!r}",
    )

# -------------------------------------------------------------
# 6. Through a symlink, as stow links it, the command resolves the real
#    checkout — not the directory the link sits in.
with tempfile.TemporaryDirectory() as td:
    checkout, command, env, record_to = make_checkout(td)
    linkdir = os.path.join(td, "home", ".local", "bin")
    os.makedirs(linkdir)
    link = os.path.join(linkdir, "delegate")
    os.symlink(command, link)
    res = run(link, ["global"], env, td)
    called = ran(record_to)
    record(
        "6 through a stow symlink it still finds its own checkout",
        res.returncode == 7 and called is not None
        and called["argv"][:3] == ["-C", os.path.realpath(checkout), "delegate-wizard"],
        repr(called),
    )

# -------------------------------------------------------------
# 7. The shipped file is executable, so stow links a runnable command.
record(
    "7 the shipped command is executable and is Python 3",
    os.access(COMMAND, os.X_OK)
    and open(COMMAND, encoding="utf-8").readline().strip() == "#!/usr/bin/env python3",
    oct(os.stat(COMMAND).st_mode),
)

sys.exit(1 if fails else 0)

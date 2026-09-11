#!/usr/bin/env python3
"""test_browser_probes.py — unit and CLI tests for browser_probes.py.
Run: python3 tests/test_browser_probes.py
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
BROWSER_PROBES_PY = os.path.join(DELEGATE_DIR, "browser_probes.py")

sys.path.insert(0, DELEGATE_DIR)
import browser_probes

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}", file=sys.stderr)


def main():
    # -------------------------------------------------------------
    # 1. Grade: pass (disposable and agent-profile)
    # -------------------------------------------------------------
    nonce = "abcd1234efgh"
    doc_disp_pass = {
        "status": "done",
        "deliverable": f"Completed browser probe.\nBROWSER-PROBE PASS title=Example Domain echoed={nonce}\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_disp_pass, "disposable", nonce=nonce)
    record("1a. grade disposable pass", verdict == "PASS" and nonce in reason, f"verdict={verdict} reason={reason}")

    doc_agent_pass = {
        "status": "done",
        "deliverable": "Account found on marketplace.\nBROWSER-PROBE PASS account=Orin Hall\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_agent_pass, "agent-profile")
    record("1b. grade agent-profile pass", verdict == "PASS" and "Orin Hall" in reason, f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 2. Grade: wrong nonce
    # -------------------------------------------------------------
    doc_disp_wrong_nonce = {
        "status": "done",
        "deliverable": f"BROWSER-PROBE PASS title=Example Domain echoed=wrongtoken123\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_disp_wrong_nonce, "disposable", nonce=nonce)
    record("2. grade wrong nonce fails", verdict == "FAIL" and "wrongtoken123" in reason, f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 3. Grade: marker echoed with <placeholder>
    # -------------------------------------------------------------
    doc_placeholder = {
        "status": "done",
        "deliverable": "BROWSER-PROBE PASS title=<title> echoed=<value>\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_placeholder, "disposable", nonce=nonce)
    record("3. grade marker with placeholder fails", verdict == "FAIL" and ("placeholder" in reason or "no BROWSER-PROBE PASS" in reason), f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 4. Grade: FAIL line
    # -------------------------------------------------------------
    doc_fail_line = {
        "status": "done",
        "deliverable": "BROWSER-PROBE FAIL: browser extension disconnected\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_fail_line, "agent-profile")
    record("4. grade FAIL line extracted", verdict == "FAIL" and "browser extension disconnected" in reason, f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 5. Grade: status not done
    # -------------------------------------------------------------
    doc_not_done = {
        "status": "blocked",
        "deliverable": "Relay timed out before model completed.\n",
        "evidence": [],
        "open_questions": [],
        "changed_files": [],
    }
    verdict, reason = browser_probes.grade(doc_not_done, "disposable", nonce=nonce)
    record("5. grade status not done fails", verdict == "FAIL" and "blocked" in reason, f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 6. Grade: missing return.json
    # -------------------------------------------------------------
    verdict, reason = browser_probes.grade(None, "disposable", nonce=nonce)
    record("6a. grade None return fails", verdict == "FAIL" and "missing return.json" in reason, f"verdict={verdict} reason={reason}")

    with tempfile.TemporaryDirectory() as empty_dir:
        verdict, reason = browser_probes.grade(empty_dir, "disposable", nonce=nonce)
        record("6b. grade empty dir fails missing return.json", verdict == "FAIL" and "missing return.json" in reason, f"verdict={verdict} reason={reason}")

    # -------------------------------------------------------------
    # 7. --dry-run with fake catalog: prints --effort low for non-agy, not for agy
    # -------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_config = os.path.join(tmpdir, "config")
        os.makedirs(fake_config, exist_ok=True)
        shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), os.path.join(fake_config, "lanes.json"))
        shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), os.path.join(fake_config, "routing.json"))

        fake_bin = os.path.join(tmpdir, "bin")
        os.makedirs(fake_bin, exist_ok=True)
        for h in ("claude", "codex", "agy", "grok"):
            p = os.path.join(fake_bin, h)
            with open(p, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(p, 0o755)

        for tool in ("python3", "sh"):
            src = shutil.which(tool)
            if src:
                dest = os.path.join(fake_bin, tool)
                if not os.path.exists(dest):
                    os.symlink(src, dest)

        test_env = dict(os.environ)
        test_env["PATH"] = os.pathsep.join([fake_bin, "/bin", "/usr/bin"])
        test_env["DELEGATE_CONFIG_DIR"] = fake_config

        res = subprocess.run(
            [sys.executable, BROWSER_PROBES_PY, "--dry-run"],
            env=test_env,
            capture_output=True,
            text=True,
        )

        lines = res.stdout.strip().splitlines()
        has_8_lines = len(lines) == 8

        non_agy_lines = [ln for ln in lines if "@agy" not in ln]
        agy_lines = [ln for ln in lines if "@agy" in ln]

        all_non_agy_have_effort_low = len(non_agy_lines) == 6 and all("--effort low" in ln for ln in non_agy_lines)
        agy_has_no_effort = len(agy_lines) == 2 and all("--effort" not in ln for ln in agy_lines)

        ok7 = res.returncode == 0 and has_8_lines and all_non_agy_have_effort_low and agy_has_no_effort
        record(
            "7. dry-run with fake catalog: --effort low for non-agy, omitted for agy",
            ok7,
            f"rc={res.returncode} total={len(lines)} non_agy_ok={all_non_agy_have_effort_low} agy_ok={agy_has_no_effort}\n{res.stdout}",
        )

        # -------------------------------------------------------------
        # 8. --dry-run with absent CLI prints 'cli absent' row
        # -------------------------------------------------------------
        os.remove(os.path.join(fake_bin, "grok"))
        res8 = subprocess.run(
            [sys.executable, BROWSER_PROBES_PY, "--dry-run", "--only", "grok"],
            env=test_env,
            capture_output=True,
            text=True,
        )
        ok8 = res8.returncode == 0 and "cli absent" in res8.stdout
        record("8. dry-run with absent cli prints cli absent row", ok8, f"rc={res8.returncode} stdout={res8.stdout}")

    if fails > 0:
        print(f"FAIL: {fails} tests failed", file=sys.stderr)
        sys.exit(1)
    else:
        print("PASS: all test_browser_probes.py tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()

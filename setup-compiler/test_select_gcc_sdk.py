# SPDX-FileCopyrightText: 2026 Oleksandr Kulkov
# SPDX-License-Identifier: CC-BY-4.0

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("select-gcc-sdk.sh")


class SelectSDK(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.active = self.root / "active SDK"
        self.configured = self.root / "configured SDK"
        for sdk in (self.active, self.configured):
            sdk.mkdir()
        self.output = self.root / "github-env"
        self.output.write_text("EXISTING=value\n")
        self.calls = self.root / "calls"
        self.env = dict(os.environ)
        self.env.pop("SDKROOT", None)
        self.env.update(
            PATH=f"{self.root}:{os.environ['PATH']}",
            RUNNER_TEMP=str(self.root),
            GITHUB_ENV=str(self.output),
            ACTIVE_SDK=str(self.active),
            CONFIGURED_SDK=str(self.configured),
            CALLS=str(self.calls),
        )
        self.executable("xcrun", '''#!/bin/bash
if [[ -n "${XCRUN_FAIL:-}" ]]; then exit 72; fi
printf '%s\n' "$ACTIVE_SDK"
''')
        compiler = '''#!/bin/bash
if [[ "$1" == -print-sysroot ]]; then
  printf '%s\n' "$CONFIGURED_SDK"
  exit 0
fi
[[ "$1" == -isysroot && "$2" == "$SDKROOT" ]] || exit 2
printf '%s|%s\n' "${0##*/}" "$SDKROOT" >> "$CALLS"
case "$0" in
  *g++*) marker=cxx ;;
  *) marker=c ;;
esac
if [[ ! -f "$SDKROOT/$marker" ]]; then
  echo "mock $marker compiler diagnostic" >&2
  exit 1
fi
'''
        self.executable("gcc-14", compiler)
        self.executable("g++-14", compiler)

    def executable(self, name, source):
        path = self.root / name
        path.write_text(source)
        path.chmod(0o755)

    def compatible(self, sdk):
        for marker in ("c", "cxx"):
            (sdk / marker).touch()

    def run_selector(self, expected=None):
        result = subprocess.run(
            ["bash", str(SCRIPT), "gcc-14"], env=self.env,
            text=True, capture_output=True, timeout=30,
        )
        if expected is None:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.output.read_text(), "EXISTING=value\n")
            self.assertIn("::error::", result.stdout)
        else:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.output.read_text(), f"EXISTING=value\nSDKROOT={expected.resolve()}\n")
        self.assertEqual(list(self.root.glob("gcc-sdk.*")), [])
        return result

    def test_active_sdk_preferred(self):
        self.compatible(self.active)
        self.compatible(self.configured)
        self.run_selector(self.active)

    def test_configured_sdk_after_c_failure(self):
        self.compatible(self.configured)
        result = self.run_selector(self.configured)
        self.assertIn("mock c compiler diagnostic", result.stdout)

    def test_configured_sdk_after_cxx_failure(self):
        (self.active / "c").touch()
        self.compatible(self.configured)
        result = self.run_selector(self.configured)
        self.assertIn("mock cxx compiler diagnostic", result.stdout)

    def test_explicit_sdk_preferred(self):
        self.compatible(self.active)
        self.compatible(self.configured)
        self.env["SDKROOT"] = str(self.configured)
        self.run_selector(self.configured)
        self.assertNotIn(str(self.active), self.calls.read_text())

    def test_explicit_failure_does_not_fall_back(self):
        self.compatible(self.active)
        self.env["SDKROOT"] = str(self.configured)
        self.run_selector()
        self.assertNotIn(str(self.active), self.calls.read_text())

    def test_missing_explicit_sdk(self):
        self.compatible(self.active)
        self.env["SDKROOT"] = str(self.root / "missing")
        self.run_selector()
        self.assertFalse(self.calls.exists())

    def test_failed_discovery(self):
        self.env["XCRUN_FAIL"] = "1"
        self.compatible(self.configured)
        self.run_selector(self.configured)

    def test_no_compatible_sdk(self):
        self.run_selector()

    def test_duplicate_sdk_is_only_probed_once(self):
        alias = self.root / "SDK alias"
        alias.symlink_to(self.active, target_is_directory=True)
        self.env["CONFIGURED_SDK"] = str(alias)
        self.run_selector()
        self.assertEqual(self.calls.read_text().count(f"gcc-14|{self.active.resolve()}\n"), 1)


if __name__ == "__main__":
    unittest.main()

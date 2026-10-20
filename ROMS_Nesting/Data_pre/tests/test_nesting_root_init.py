#!/usr/bin/env python3
"""``ROMS_NESTING_ROOT`` must be resolved explicitly, never as an import effect.

The old behaviour set the variable at import time, which silently overrode any
value the user had exported.  These tests pin the replacement contract:

* importing ``case_context`` mutates nothing;
* ``init_nesting_root()`` sets the variable exactly once, at a call site;
* an explicit value is honoured when it names a real nesting checkout;
* anything else fails closed instead of being silently replaced.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CORE = BASE / "core"
sys.path.insert(0, str(CORE))

from case_context import (  # noqa: E402
    NESTING_ROOT_ENV,
    default_nesting_root,
    init_nesting_root,
    is_nesting_root,
)

MARKERS = ("Data_pre", "ROMS_Build", "ROMS_Run")


def _make_checkout(root: Path, markers=MARKERS) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for marker in markers:
        (root / marker).mkdir(exist_ok=True)
    return root


class ImportSideEffectTest(unittest.TestCase):
    def test_importing_case_context_does_not_set_the_variable(self):
        """A clean environment must stay clean across the import."""
        script = textwrap.dedent(
            f"""
            import os, sys
            os.environ.pop({NESTING_ROOT_ENV!r}, None)
            sys.path.insert(0, {str(CORE)!r})
            import case_context
            value = os.environ.get({NESTING_ROOT_ENV!r})
            assert value is None, f"import mutated the environment: {{value!r}}"
            print("CLEAN")
            """
        )
        env = {key: value for key, value in os.environ.items() if key != NESTING_ROOT_ENV}
        result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CLEAN", result.stdout)

    def test_importing_preserves_a_preexisting_value(self):
        script = textwrap.dedent(
            f"""
            import os, sys
            os.environ[{NESTING_ROOT_ENV!r}] = "/tmp/sentinel-do-not-touch"
            sys.path.insert(0, {str(CORE)!r})
            import case_context
            print(os.environ[{NESTING_ROOT_ENV!r}])
            """
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "/tmp/sentinel-do-not-touch")


class InitNestingRootTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self._saved = os.environ.get(NESTING_ROOT_ENV)
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop(NESTING_ROOT_ENV, None)
        else:
            os.environ[NESTING_ROOT_ENV] = self._saved

    def test_unset_initialises_to_this_checkout(self):
        os.environ.pop(NESTING_ROOT_ENV, None)
        self.assertEqual(init_nesting_root(), default_nesting_root())
        self.assertEqual(os.environ[NESTING_ROOT_ENV], str(default_nesting_root()))

    def test_this_checkout_explicitly_set_is_honoured(self):
        os.environ[NESTING_ROOT_ENV] = str(default_nesting_root())
        self.assertEqual(init_nesting_root(), default_nesting_root().resolve())

    def test_a_different_checkout_fails_closed(self):
        """Accepting another tree would mix its data with this tree's code."""
        other = _make_checkout(self.root / "other_checkout")
        os.environ[NESTING_ROOT_ENV] = str(other)
        with self.assertRaises(SystemExit) as caught:
            init_nesting_root()
        message = str(caught.exception)
        self.assertIn("different checkout", message)
        self.assertIn("Cross-checkout rebinding is not supported", message)
        self.assertEqual(os.environ[NESTING_ROOT_ENV], str(other))

    def test_directory_that_is_not_a_checkout_fails_closed(self):
        plain = self.root / "plain"
        plain.mkdir()
        os.environ[NESTING_ROOT_ENV] = str(plain)
        with self.assertRaises(SystemExit) as caught:
            init_nesting_root()
        self.assertIn("is not a ROMS nesting checkout", str(caught.exception))

    def test_partial_checkout_fails_closed(self):
        partial = _make_checkout(self.root / "partial", markers=("Data_pre", "ROMS_Build"))
        os.environ[NESTING_ROOT_ENV] = str(partial)
        with self.assertRaises(SystemExit):
            init_nesting_root()

    def test_missing_path_fails_closed(self):
        os.environ[NESTING_ROOT_ENV] = str(self.root / "does_not_exist")
        with self.assertRaises(SystemExit):
            init_nesting_root()

    def test_failed_init_does_not_rewrite_the_environment(self):
        os.environ[NESTING_ROOT_ENV] = str(self.root / "does_not_exist")
        with self.assertRaises(SystemExit):
            init_nesting_root()
        self.assertEqual(os.environ[NESTING_ROOT_ENV], str(self.root / "does_not_exist"))

    def test_is_nesting_root_accepts_this_checkout(self):
        self.assertTrue(is_nesting_root(default_nesting_root()))


if __name__ == "__main__":
    unittest.main()

"""Lifecycle guards for `run_web.sh` — TODO-82 and TODO-83.

*** WHY THESE TESTS EXIST, IN ONE SENTENCE. ***

On 2026-10-13 the kiosk launcher `exec`ed Chromium, which replaced the shell and
destroyed its own cleanup trap, so killing the browser left the transport running
on PID 1 — still bound to :8711, still answering, and on a live run still holding
`/dev/ttyAMA0` with nothing on screen. A relaunch would then have attached to that
orphan and filmed its data as though it were the new run's.

Two kinds of test, deliberately:

  SOURCE GUARDS   assert the shape of the fix, because the failure mode is a
                  later contributor "tidying" a redundant-looking `&` or trap.
                  They cost nothing and they run everywhere.

  BEHAVIOURAL     actually start the launcher, signal it, and check what is left
                  behind. These are the only tests that can catch a fix that
                  looks right and does not work — which is precisely what the
                  pre-2026-10-13 launcher was.

Neither kind touches a serial device, and the behavioural tests run with
`--no-browser`, so no Chromium is launched and no display is needed.
"""

from __future__ import annotations

import pathlib
import re
import signal
import socket
import subprocess
import time
import unittest

PI = pathlib.Path(__file__).resolve().parents[1]
REPO = PI.parent
LAUNCHER = PI / "run_web.sh"
FIXTURE = REPO / "ai" / "evidence" / "phase10-result-1khz.bin"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _is_listening(port: int, timeout: float = 0.3) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _code_only(src: str) -> str:
    """Source with whole-line comments removed.

    The guards below ban certain *commands*. The comments that explain why a
    command is banned necessarily quote it, so matching raw source makes the
    documentation trip its own guard — which it did, first run.
    """
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def _wait_for(predicate, seconds: float, step: float = 0.1) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


# =============================================================================
# SOURCE GUARDS — the shape of the fix
# =============================================================================

class TestLauncherSupervisesRatherThanExecs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = LAUNCHER.read_text()

    def test_it_does_not_exec_the_browser(self):
        """`exec` replaces the shell, taking the trap with it.

        This is the whole of TODO-82. If this assertion ever fails, the orphaned
        transport is back and so is the stale-data-on-camera risk.
        """
        self.assertNotRegex(
            self.src, r"(?m)^\s*exec\s+\"\$CHROMIUM\"",
            "run_web.sh execs Chromium again: the cleanup trap cannot fire")

    def test_the_browser_runs_in_the_background_and_is_waited_for(self):
        """Backgrounding is not cosmetic — it is what makes SIGTERM prompt.

        A trapped signal arriving while a POSIX shell waits on a FOREGROUND
        command is not acted on until that command finishes, which for a kiosk
        means never. Dropping the `exec` is necessary and NOT sufficient.
        """
        self.assertRegex(self.src, r"--check-for-update-interval=\d+\s*&",
                         "Chromium is not backgrounded")
        self.assertIn("BROWSER_PID=$!", self.src)
        self.assertRegex(self.src, r'wait\s+"\$BROWSER_PID"')

    def test_both_children_are_tracked(self):
        self.assertIn("SERVER_PID=$!", self.src)
        self.assertIn("BROWSER_PID=$!", self.src)

    def test_normal_exit_and_both_signals_are_handled(self):
        for sig in ("EXIT", "INT", "TERM"):
            self.assertRegex(
                self.src, rf"(?m)^trap\s+.*\b{sig}\b",
                f"no trap handles {sig}")

    def test_the_signal_handlers_terminate_the_script(self):
        """An INT/TERM handler that cleans up and returns would let the shell
        carry on waiting, which is a hang rather than a shutdown."""
        self.assertRegex(self.src, r"trap\s+'[^']*cleanup;\s*exit\s+130'\s+INT")
        self.assertRegex(self.src, r"trap\s+'[^']*cleanup;\s*exit\s+143'\s+TERM")

    def test_shutdown_is_bounded_and_escalates(self):
        """An unbounded `wait` on a child that ignores SIGTERM hangs cleanup and
        strands the profile on disk."""
        self.assertIn("kill -9", self.src, "no SIGKILL escalation")
        self.assertRegex(self.src, r"while\s+\[\s+\"\$_i\"\s+-lt\s+\d+\s+\]",
                         "no bounded wait loop")

    def test_children_are_reaped(self):
        """Without a reap the child lingers as a zombie and `ps -p` reports a
        dead process as alive — the exact ambiguity seen on 2026-10-13."""
        self.assertRegex(self.src, r'wait\s+"\$_pid"')

    def test_liveness_is_not_decided_by_kill_dash_zero_alone(self):
        """`kill -0` succeeds against a zombie, so it cannot answer "is it
        gone?". On Linux the state field is what answers."""
        self.assertIn("/proc/$1/stat", self.src)

    def test_cleanup_is_idempotent(self):
        """EXIT fires after an INT/TERM handler has already cleaned up."""
        self.assertIn("CLEANED", self.src)


class TestProfileCleanupIsScopedToThisLaunch(unittest.TestCase):
    """TODO-83. The leak must be fixed without acquiring the power to delete
    somebody else's profile."""

    @classmethod
    def setUpClass(cls):
        cls.src = LAUNCHER.read_text()
        cls.code = _code_only(cls.src)

    def test_it_never_glob_deletes_kiosk_profiles(self):
        """`rm -rf /tmp/gra-kiosk.*` would take the profile of a kiosk another
        session is still running, with no way to tell whose it was."""
        self.assertNotRegex(
            self.code, r"rm\s+-rf\s+/tmp/gra-kiosk\.\*",
            "blanket profile deletion: this can destroy another session's kiosk")

    def test_it_removes_exactly_the_profile_it_created(self):
        self.assertRegex(self.code, r'rm\s+-rf\s+"\$PROFILE"')

    def test_pre_existing_profiles_are_reported_not_removed(self):
        """Inventory, so a leak is visible, without taking the decision to
        delete away from the operator."""
        inventory = re.search(r"for d in /tmp/gra-kiosk\.\*.*?done",
                              self.code, re.S)
        self.assertIsNotNone(inventory, "no profile inventory")
        self.assertNotIn("rm ", inventory.group(0),
                         "the inventory deletes rather than reports")


class TestPortOwnershipGuard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = LAUNCHER.read_text()

    def test_the_guard_exists_and_refuses(self):
        self.assertIn("already bound", self.src)

    def test_the_guard_does_not_claim_to_be_a_uart_check(self):
        """A free port says nothing about who owns the serial device, and the
        comment that says so is load-bearing: this guard sits one step before a
        UART handoff and must not be mistaken for clearing it."""
        self.assertIn("A FREE PORT IS NOT A FREE UART", self.src)
        self.assertIn("ttyAMA0", self.src)


# =============================================================================
# BEHAVIOURAL — start it, signal it, inspect what is left
# =============================================================================

@unittest.skipUnless(FIXTURE.is_file(), "fixture not present")
class TestLauncherLifecycleForReal(unittest.TestCase):
    """No Chromium and no display: every case runs with --no-browser."""

    def _launch(self, port: int):
        return subprocess.Popen(
            [
                "sh", str(LAUNCHER),
                "--fixture", "../ai/evidence/phase10-result-1khz.bin",
                "--no-browser", "--port", str(port),
            ],
            cwd=str(REPO), start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def test_it_refuses_a_port_somebody_else_owns(self):
        """The orphan scenario, reproduced: something is already listening, and
        the launcher must refuse rather than quietly serve from it."""
        port = _free_port()
        with socket.socket() as occupant:
            occupant.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupant.bind(("127.0.0.1", port))
            # Backlog of 1 was not enough: the launcher's guard probe connects
            # and is never accepted, so a backlog of 1 is already full when this
            # test checks the listener afterwards. That looked exactly like the
            # launcher having killed it. It had not.
            occupant.listen(64)

            proc = self._launch(port)
            try:
                out, _ = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.fail("launcher hung instead of refusing an occupied port")

            self.assertEqual(proc.returncode, 1, f"expected refusal, got:\n{out}")
            self.assertIn("already bound", out)
            self.assertTrue(_is_listening(port),
                            "the launcher disturbed the existing listener")

    def test_sigterm_stops_the_transport_and_releases_the_port(self):
        """The regression that matters. Before the fix the transport survived
        and kept the port — and, on a live run, the UART."""
        port = _free_port()
        proc = self._launch(port)
        try:
            self.assertTrue(
                _wait_for(lambda: _is_listening(port), 30),
                "transport never came up")

            proc.send_signal(signal.SIGTERM)
            try:
                out, _ = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.fail("launcher did not exit within 30 s of SIGTERM")

            self.assertEqual(proc.returncode, 143,
                             f"expected the TERM handler's exit code:\n{out}")
            self.assertTrue(
                _wait_for(lambda: not _is_listening(port), 10),
                "the transport outlived its supervisor and kept the port")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

    def test_sigint_is_handled_the_same_way(self):
        port = _free_port()
        proc = self._launch(port)
        try:
            self.assertTrue(
                _wait_for(lambda: _is_listening(port), 30),
                "transport never came up")

            proc.send_signal(signal.SIGINT)
            try:
                out, _ = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.fail("launcher did not exit within 30 s of SIGINT")

            self.assertEqual(proc.returncode, 130, f"unexpected exit:\n{out}")
            self.assertTrue(
                _wait_for(lambda: not _is_listening(port), 10),
                "the transport outlived its supervisor after SIGINT")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

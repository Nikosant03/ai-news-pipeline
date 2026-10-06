"""Tests for the cryptography self-repair that 2026-10-06 made necessary."""

import os
import sys

import pytest

from scripts import bootstrap


class _Result:
    def __init__(self, returncode):
        self.returncode = returncode


def _recorder(returncode=0):
    calls = []

    def runner(command, check=False):
        calls.append(command)
        return _Result(returncode)

    return runner, calls


def _restart_recorder():
    restarts = []

    def restart(executable, argv):
        restarts.append((executable, argv))

    return restart, restarts


@pytest.fixture(autouse=True)
def _clear_guard(monkeypatch):
    monkeypatch.delenv(bootstrap.REPAIR_ATTEMPTED, raising=False)


def test_nothing_happens_when_the_library_already_works(monkeypatch):
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: True)
    runner, calls = _recorder()
    restart, restarts = _restart_recorder()

    bootstrap.ensure_cryptography(runner=runner, restart=restart)

    assert calls == [], "a working library must never be reinstalled"
    assert restarts == []


def test_a_library_that_imports_but_cannot_encrypt_is_still_repaired(monkeypatch):
    """The real probe is a Fernet round-trip, not an import: a cryptography
    that imports and then fails with UnsupportedAlgorithm is no use for
    encrypting the refresh token, which is all this pipeline wants from it."""
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: False)
    runner, calls = _recorder()
    restart, restarts = _restart_recorder()

    bootstrap.ensure_cryptography(runner=runner, restart=restart)

    assert len(calls) == 1
    assert len(restarts) == 1


def test_the_install_uses_the_running_interpreter(monkeypatch):
    """The fix hinges on this: the install must go through sys.executable,
    because the shell's `pip` belonged to a different interpreter and that is
    exactly why the routine's own prescribed retry did nothing on 2026-10-06."""
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: False)
    runner, calls = _recorder()
    restart, _ = _restart_recorder()

    bootstrap.ensure_cryptography(runner=runner, restart=restart)

    assert calls[0][:4] == [sys.executable, "-m", "pip", "install"]
    assert "cryptography" in calls[0]
    assert "cffi" in calls[0]


def test_the_restart_reruns_the_same_command(monkeypatch):
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: False)
    runner, _ = _recorder()
    restart, restarts = _restart_recorder()

    bootstrap.ensure_cryptography(runner=runner, restart=restart)

    executable, argv = restarts[0]
    assert executable == sys.executable
    assert argv == sys.orig_argv
    assert os.environ[bootstrap.REPAIR_ATTEMPTED] == "1", (
        "without the guard the restarted process would reinstall and restart again"
    )


def test_an_externally_managed_pip_is_retried_with_the_override(monkeypatch):
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: False)
    runner, calls = _recorder(returncode=1)
    restart, _ = _restart_recorder()

    bootstrap.ensure_cryptography(runner=runner, restart=restart)

    assert len(calls) == 2, "a refused install must be retried once"
    assert "--break-system-packages" not in calls[0]
    assert "--break-system-packages" in calls[1]


def test_still_broken_after_a_repair_raises_instead_of_looping(monkeypatch):
    monkeypatch.setattr(bootstrap, "_fernet_works", lambda: False)
    monkeypatch.setenv(bootstrap.REPAIR_ATTEMPTED, "1")
    runner, calls = _recorder()
    restart, restarts = _restart_recorder()

    with pytest.raises(RuntimeError) as err:
        bootstrap.ensure_cryptography(runner=runner, restart=restart)

    assert "needs fixing, not retrying" in str(err.value)
    assert calls == [] and restarts == []

"""Make sure `cryptography` actually works before anything in this package
leans on it, and repair the installation once if it does not.

2026-10-06 cost a whole morning to this. The sandbox that ran the brief had
Debian's `cryptography` at /usr/lib/python3/dist-packages with no matching
`cffi` next to it, so importing it raised `No module named '_cffi_backend'`
and then panicked inside its Rust bindings. `python -m scripts.run_daily_brief`
died on its very first import — before the token refresh, before the audio,
before the podcast push — and nothing was delivered that day: no OneDrive
files, no mail-folder message, no episode in the feed.

The routine's instruction sheet already prescribed `pip install
--ignore-installed -r requirements.txt` as the one retry for exactly this
failure, and the retry changed nothing. The reason is that `pip` on that image
is Debian's /usr/bin/pip while `python` is /usr/local/bin/python: the two do
not share a site-packages directory, so reinstalling with one cannot change
what the other imports. Installing with `sys.executable -m pip` is what closes
the gap — the same interpreter that is about to do the importing, so the files
land where it actually looks, ahead of the broken system copy on sys.path.
Doing it from inside the process that needs the library is the point: it cannot
be defeated by a shell whose `pip` happens to point somewhere else.

Why the repair restarts the process instead of just re-importing: a first
attempt at this deleted `cryptography` from sys.modules and imported it again
in place. That leaves the Rust extension module half-initialised, and the
symptom is worse than the original — the import succeeds, and then Fernet
fails with `cipher AES in CBC mode is not supported`, which reads like a
broken key rather than a broken install. A C extension cannot be re-initialised
in a running interpreter, so the only honest way to pick up the new files is a
fresh one.

Why the check is a Fernet round-trip and not just an import: the import
succeeding proves nothing. That `UnsupportedAlgorithm` failure above is a
`cryptography` that imports perfectly and still cannot encrypt the refresh
token, which is the only thing this pipeline uses it for.
"""

from __future__ import annotations

import os
import subprocess
import sys

PACKAGES = ("cryptography", "cffi")

# Set before the restart so one bad image cannot put the run into a loop of
# install-restart-install. Inherited across os.execv with the rest of the
# environment.
REPAIR_ATTEMPTED = "AI_NEWS_CRYPTO_REPAIR_ATTEMPTED"


def _fernet_works() -> bool:
    """True only if the library can do the one job this pipeline needs."""
    try:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        return Fernet(key).decrypt(Fernet(key).encrypt(b"probe")) == b"probe"
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        # Not just ImportError: the observed failures include
        # pyo3_runtime.PanicException from the Rust bindings, which does not
        # inherit from Exception, and cryptography's own UnsupportedAlgorithm.
        return False


def _pip_install(runner) -> None:
    command = [
        sys.executable, "-m", "pip", "install",
        "--quiet", "--upgrade", "--force-reinstall", *PACKAGES,
    ]
    result = runner(command, check=False)
    if getattr(result, "returncode", 1) != 0:
        # A future image may mark its system Python "externally managed", which
        # makes pip refuse the install above. The flag only goes on the retry
        # because an older pip rejects the flag itself.
        runner([*command, "--break-system-packages"], check=False)


def ensure_cryptography(runner=None, restart=None) -> None:
    """Return once a Fernet round-trip works, repairing the install once.

    On the repair path this function does not return: it replaces the process
    with a fresh one running the same command. Nothing has been delivered at
    the point it is called (it is the first thing the daily run does), so
    starting over costs only the seconds already spent.

    Raises RuntimeError if the library is still unusable after a repair. The
    caller decides what that costs — as of 2026-10-06 it no longer costs the
    podcast.
    """
    if _fernet_works():
        return
    if os.environ.get(REPAIR_ATTEMPTED):
        raise RuntimeError(
            "cryptography is still unusable after reinstalling it with "
            f"{sys.executable} -m pip — this image needs fixing, not retrying"
        )
    _pip_install(runner or subprocess.run)
    os.environ[REPAIR_ATTEMPTED] = "1"
    (restart or os.execv)(sys.executable, sys.orig_argv)

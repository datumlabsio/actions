"""Deliberately bad. Every finding here is one the gate must catch."""

import subprocess


def run_user_command(name):
    # shell=True with a constructed command: a filename becomes code execution.
    return subprocess.run(f"ls {name}", shell=True, check=False)


def swallow_everything():
    try:
        run_user_command("x")
    except:  # noqa: E722 — bare except, hides KeyboardInterrupt and SystemExit
        pass


class BlockManifest:
    """Retired by RFC-0008. Should be flagged."""

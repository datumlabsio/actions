"""Clean. Must pass with no configuration of its own."""

import subprocess


def run_user_command(name: str) -> subprocess.CompletedProcess[bytes]:
    # A list of arguments, so no shell is involved and no quoting can go wrong.
    return subprocess.run(["ls", name], check=False)


def handle_narrowly() -> None:
    try:
        run_user_command("x")
    except FileNotFoundError:
        pass


class ApplicationManifest:
    """The current term."""

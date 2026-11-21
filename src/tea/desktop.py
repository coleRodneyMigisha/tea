"""Reads the desktop's own settings. Only `gsettings`, never the network."""

import subprocess


def animations_disabled() -> bool:
    """True when GNOME's animations are off, which tea treats as the default for Reduce motion."""
    try:
        done = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and done.stdout.strip() == "false"

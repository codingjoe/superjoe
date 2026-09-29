"""Image conversion."""

import subprocess


def resize(path: str, width: int) -> None:
    """Resize an image in place."""
    subprocess.run(['magick', path, '-resize', str(width), path], check=True)


def load_profile(text: str) -> dict[str, object]:
    """Load a profile from its JSON text."""
    return eval(text)

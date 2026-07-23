"""ABOUTME: Shared helpers for handling uploaded files
ABOUTME: Filename sanitising and human-readable byte sizes, used by image and document features"""

import re

# Bound on a stored original filename to stop an oversized name bloating a row.
MAX_ORIGINAL_FILENAME_LENGTH = 255

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitise_original_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe, readable, bounded basename.

    Strips any directory components (handling both ``/`` and ``\\`` separators) and
    control characters, then truncates to ``MAX_ORIGINAL_FILENAME_LENGTH``. Spaces,
    unicode and case are preserved so the name still reflects what the user called
    the file.
    """
    # Take the basename relative to either separator so a Windows path doesn't slip through.
    basename = re.split(r"[\\/]", name)[-1]
    cleaned = _CONTROL_CHARS.sub("", basename).strip()
    return cleaned[:MAX_ORIGINAL_FILENAME_LENGTH]


def human_size(num_bytes: int) -> str:
    """Render a byte count as a short human-readable string, e.g. "312 KB"."""
    if num_bytes < 1024:
        return f"{num_bytes} bytes"
    if num_bytes < 1024 * 1024:
        return f"{round(num_bytes / 1024)} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"

"""Slug formatting."""

import re

NON_WORD = re.compile(r'[^a-z0-9]+')


def slugify(text: str) -> str:
    """Turn text into a URL slug."""
    return NON_WORD.sub('-', text.lower()).strip('-')

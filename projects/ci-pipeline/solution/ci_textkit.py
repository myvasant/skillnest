"""ci_textkit: a small text-utility library - the code our CI pipeline protects.

Three functions, each with a precise, testable contract:

* ``slugify(text, max_length=50)`` - a URL-safe slug such as ``"hello-world"``.
* ``word_frequencies(text, top=None)`` - ``[(word, count), ...]``, most frequent first.
* ``parse_key_values(text)`` - ``{"KEY": "value"}`` from ``KEY=value`` lines.

The library is deliberately tiny so the project can focus on the pipeline around it:
lint, tests on several Python versions and a coverage gate.
"""

import re
import unicodedata
from collections import Counter

__all__ = ["KeyValueError", "parse_key_values", "slugify", "word_frequencies"]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# A word is a run of letters or digits (any script), optionally joined by
# apostrophes: "don't" is one word. Underscores are not part of words.
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUOTES = "\"'"


class KeyValueError(ValueError):
    """A line of ``KEY=value`` text could not be parsed.

    Attributes:
        line_number: 1-based number of the offending line.
    """

    def __init__(self, line_number: int, message: str) -> None:
        super().__init__(f"line {line_number}: {message}")
        self.line_number = line_number


def slugify(text: str, max_length: int = 50) -> str:
    """Turn ``text`` into a lowercase, hyphen-separated, ASCII slug.

    Accents are removed (``"Crème"`` -> ``"creme"``); characters with no ASCII
    equivalent are dropped. Runs of anything that is not a letter or digit become
    one hyphen, and there are no leading or trailing hyphens. Slugs longer than
    ``max_length`` are cut at the last whole word that fits; a single word that is
    too long is cut hard.

    Raises:
        ValueError: if ``max_length < 1`` or the text has no letters or digits.
    """
    if max_length < 1:
        raise ValueError("max_length must be at least 1")
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", ascii_text.lower()).strip("-")
    if not slug:
        raise ValueError("text must contain at least one letter or digit")
    return _shorten(slug, max_length)


def _shorten(slug: str, max_length: int) -> str:
    """Cut ``slug`` to ``max_length`` characters, preferring a word boundary."""
    if len(slug) <= max_length:
        return slug
    cut = slug[:max_length]
    cut_mid_word = slug[max_length] != "-"
    if cut_mid_word and "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.rstrip("-")


def word_frequencies(text: str, top: int | None = None) -> list[tuple[str, int]]:
    """Count words case-insensitively, most frequent first.

    Ties are broken alphabetically so the result is deterministic. With ``top``,
    only the first ``top`` pairs are returned.

    Raises:
        ValueError: if ``top`` is given and is less than 1.
    """
    if top is not None and top < 1:
        raise ValueError("top must be a positive integer or None")
    counts = Counter(_WORD.findall(text.casefold()))
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked if top is None else ranked[:top]


def parse_key_values(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines (like a tiny ``.env`` file) into a dict.

    Blank lines and lines starting with ``#`` are ignored. Whitespace around keys
    and values is removed, one pair of matching surrounding quotes is removed from
    a value, and everything after the first ``=`` belongs to the value.

    Raises:
        KeyValueError: (a ``ValueError``) naming the line number when a line has no
            ``=``, the key is not an identifier, or a key appears twice.
    """
    result: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = _split_pair(line, number)
        if key in result:
            raise KeyValueError(number, f"duplicate key {key!r}")
        result[key] = value
    return result


def _split_pair(line: str, number: int) -> tuple[str, str]:
    """Split one non-comment line into a validated key and an unquoted value."""
    key, separator, value = line.partition("=")
    if not separator:
        raise KeyValueError(number, f"expected KEY=value, got {line!r}")
    key = key.strip()
    if not _KEY.fullmatch(key):
        raise KeyValueError(number, f"invalid key {key!r} (use letters, digits and _)")
    return key, _unquote(value.strip())


def _unquote(value: str) -> str:
    """Remove one pair of matching surrounding quotes, if present."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES:
        return value[1:-1]
    return value

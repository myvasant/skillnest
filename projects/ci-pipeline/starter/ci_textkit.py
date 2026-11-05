"""ci_textkit: a small text-utility library - the code our CI pipeline protects.

Three functions, each with a precise, testable contract:

* ``slugify(text, max_length=50)`` - a URL-safe slug such as ``"hello-world"``.
* ``word_frequencies(text, top=None)`` - ``[(word, count), ...]``, most frequent first.
* ``parse_key_values(text)`` - ``{"KEY": "value"}`` from ``KEY=value`` lines.

Milestone 1: implement the three functions (run ``python -m pytest -k Milestone1``).
Milestones 2-4 happen in ``starter/.github/workflows/ci.yml``, not in this file.

Useful standard-library tools: ``re``, ``unicodedata.normalize("NFKD", ...)``,
``str.encode("ascii", "ignore")``, ``collections.Counter`` and ``str.partition``.
"""

__all__ = ["KeyValueError", "parse_key_values", "slugify", "word_frequencies"]


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
    # TODO(milestone 1): validate max_length, strip accents (NFKD + ASCII),
    #   lowercase, replace runs of non-alphanumerics with "-", strip "-",
    #   reject empty slugs, then shorten at a word boundary.
    raise NotImplementedError("TODO(milestone 1): implement slugify")


def word_frequencies(text: str, top: int | None = None) -> list[tuple[str, int]]:
    """Count words case-insensitively, most frequent first.

    A word is a run of letters or digits, optionally joined by apostrophes
    (``"don't"`` is one word). Ties are broken alphabetically so the result is
    deterministic. With ``top``, only the first ``top`` pairs are returned.

    Raises:
        ValueError: if ``top`` is given and is less than 1.
    """
    # TODO(milestone 1): find words with a regex, count them, sort by
    #   (-count, word) and apply ``top``.
    raise NotImplementedError("TODO(milestone 1): implement word_frequencies")


def parse_key_values(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines (like a tiny ``.env`` file) into a dict.

    Blank lines and lines starting with ``#`` are ignored. Whitespace around keys
    and values is removed, one pair of matching surrounding quotes is removed from
    a value, and everything after the first ``=`` belongs to the value.

    Raises:
        KeyValueError: (a ``ValueError``) naming the line number when a line has no
            ``=``, the key is not an identifier, or a key appears twice.
    """
    # TODO(milestone 1): loop over enumerate(text.splitlines(), start=1), skip
    #   blanks/comments, split on the first "=", validate the key, unquote the
    #   value and raise KeyValueError(line_number, message) on bad input.
    raise NotImplementedError("TODO(milestone 1): implement parse_key_values")

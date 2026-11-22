import hashlib
import re
from typing import NamedTuple

from rich.cells import get_character_cell_size


def display_width(text: str) -> int:
    if not text:
        return 0
    return sum(max(0, get_character_cell_size(ch)) for ch in text)


def display_slice(text: str, max_cells: int) -> str:
    if max_cells <= 0:
        return ""
    out: list[str] = []
    used = 0
    for ch in text:
        cell = get_character_cell_size(ch)
        if cell < 0:
            continue
        if used + cell > max_cells:
            break
        out.append(ch)
        used += cell
    return "".join(out)

WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
TAG_PATTERN = re.compile(r"(?<![\w/&#`'\"])#([^\W\d_]\w*)", re.UNICODE)


class Wikilink(NamedTuple):
    target: str
    display: str
    raw: str

    @property
    def normalized_target(self) -> str:
        return normalize_title(self.target)


def normalize_title(title: str) -> str:
    if title is None:
        return ""
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned.casefold()


def title_display(title: str) -> str:
    if title is None:
        return ""
    return re.sub(r"\s+", " ", title).strip()


def parse_wikilinks(content: str) -> list[Wikilink]:
    if not content:
        return []
    links: list[Wikilink] = []
    seen_targets: set = set()
    for match in WIKILINK_PATTERN.finditer(content):
        raw = match.group(1)
        target, _, display = raw.partition("|")
        target = target.strip()
        display = (display or target).strip()
        if not target:
            continue
        norm = normalize_title(target)
        if norm in seen_targets:
            continue
        seen_targets.add(norm)
        links.append(Wikilink(target=target, display=display, raw=raw))
    return links


def extract_tags(content: str) -> list[str]:
    if not content:
        return []
    seen = set()
    ordered: list[str] = []
    for match in TAG_PATTERN.finditer(content):
        tag = match.group(1).casefold()
        if tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)
    return ordered


def tag_widget_id(tag: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", tag)
    if not safe:
        safe = "tag"
    if safe[0].isdigit():
        safe = "t_" + safe
    digest = hashlib.sha256(tag.encode("utf-8")).hexdigest()[:8]
    return f"tag-{safe}-{digest}"


def escape_markup(text: str) -> str:
    """Escape Rich/textual markup characters so user text is rendered literally."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def sanitize_filename(text: str) -> str:
    """Make a string safe to use as a single path component.

    Replaces path separators and control characters with underscores,
    collapses whitespace, and trims leading/trailing dots and spaces.
    """
    if not text:
        return "untitled"
    cleaned = re.sub(r"[\\/\x00-\x1f]", "_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "untitled"


TITLE_MAX_LENGTH = 200


def is_valid_title(title: str) -> bool:
    """Reject empty, overly long, or control-character-laden titles."""
    if title is None:
        return False
    if not title.strip():
        return False
    if len(title) > TITLE_MAX_LENGTH:
        return False
    if any(ord(ch) < 0x20 and ch not in ("\t",) for ch in title):
        return False
    return True

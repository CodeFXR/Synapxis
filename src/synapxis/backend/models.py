from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    id: str
    title: str
    content: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""
    deleted_at: str | None = None


class NoteStoreError(Exception):
    """Raised by store operations that need to surface to the UI."""


class DuplicateTitleError(NoteStoreError):
    def __init__(self, title: str, existing_id: str):
        super().__init__(f"A note titled {title!r} already exists.")
        self.title = title
        self.existing_id = existing_id


class EmptyTitleError(NoteStoreError):
    def __init__(self) -> None:
        super().__init__("Title cannot be empty.")


class InvalidTitleError(NoteStoreError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class NoteNotFoundError(NoteStoreError):
    pass

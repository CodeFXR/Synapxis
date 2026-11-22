import asyncio
import json
import math
import os
import sqlite3
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from ..utils.parsing import is_valid_title, normalize_title, title_display
from .models import (
    DuplicateTitleError,
    EmptyTitleError,
    InvalidTitleError,
    Note,
    NoteNotFoundError,
    NoteStoreError,
)

CURRENT_SCHEMA_VERSION = 3

MIGRATIONS: dict[int, list[str]] = {
    1: [
        "ALTER TABLE notes ADD COLUMN deleted_at TEXT",
    ],
    2: [
        "ALTER TABLE notes ADD COLUMN title_key TEXT",
    ],
    3: [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_title_key_unique ON notes(title_key)",
    ],
}

LAYOUT_KEY = "layout"
TAG_COLORS_KEY = "tag_colors"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_layout(raw: Any) -> dict[str, list[float]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[float]] = {}
    for nid, pos in raw.items():
        if not isinstance(nid, str) or not isinstance(pos, (list, tuple)):
            continue
        if len(pos) != 2:
            continue
        try:
            x, y = float(pos[0]), float(pos[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        out[nid] = [x, y]
    return out


def _validate_tag_colors(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for tag, idx in raw.items():
        if not isinstance(tag, str) or not tag:
            continue
        if isinstance(idx, bool) or not isinstance(idx, int):
            continue
        if not 0 <= idx <= 99:
            continue
        out[tag] = idx
    return out


def _safe_mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _normalize_file_mode(path: Path) -> None:
    if sys.platform == "win32":
        return
    if not path.exists():
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _row_to_note(row: aiosqlite.Row) -> Note:
    raw_tags = row["tags"]
    try:
        tags_parsed = json.loads(raw_tags) if raw_tags else []
    except (TypeError, ValueError):
        tags_parsed = []
    tags = [t for t in tags_parsed if isinstance(t, str)]
    return Note(
        id=row["id"],
        title=row["title"] or "",
        content=row["content"] or "",
        tags=tags,
        created_at=row["created_at"] or "",
        modified_at=row["modified_at"] or "",
        deleted_at=row["deleted_at"],
    )


def _serialize_tags(tags: list[str]) -> str:
    return json.dumps([t for t in tags if isinstance(t, str)], ensure_ascii=False)


class NoteStore:
    def __init__(self, path: Path):
        self.db_path = path.with_suffix(".db")
        self.notes: dict[str, Note] = {}
        self.trash: dict[str, Note] = {}
        self.layout: dict[str, list[float]] = {}
        self.tag_colors: dict[str, int] = {}
        self._write_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @property
    def db_dir(self) -> Path:
        return self.db_path.parent

    async def load(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            self.db_dir.mkdir(parents=True, exist_ok=True)
            _safe_mkdir_private(self.db_dir)
            await self._init_db()
            await self._load_into_memory()
            self._initialized = True
            for sidecar in (self.db_path, *self.db_path.parent.glob(self.db_path.name + ".*")):
                _normalize_file_mode(sidecar)

    async def _init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA busy_timeout = 5000")

            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notes'"
            ) as cursor:
                existing_notes_table = await cursor.fetchone()

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    title_key TEXT,
                    content TEXT,
                    tags TEXT,
                    created_at TEXT,
                    modified_at TEXT,
                    deleted_at TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_deleted_at ON notes(deleted_at)"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            if existing_notes_table is None:
                await db.execute(
                    "CREATE UNIQUE INDEX idx_notes_title_key_unique ON notes(title_key)"
                )
                await db.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(CURRENT_SCHEMA_VERSION),),
                )
            else:
                await self._run_migrations(db)
            await db.commit()

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        async with db.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ) as cursor:
            row = await cursor.fetchone()
        current = int(row[0]) if row and row[0] else 0
        if current >= CURRENT_SCHEMA_VERSION:
            return
        for target in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
            if target == 3:
                async with db.execute("SELECT id, title FROM notes") as cursor:
                    rows = await cursor.fetchall()
                for note_id, title in rows:
                    await db.execute(
                        "UPDATE notes SET title_key = ? WHERE id = ?",
                        (normalize_title(title or ""), note_id),
                    )
                async with db.execute(
                    "SELECT title_key FROM notes WHERE title_key IS NOT NULL "
                    "GROUP BY title_key HAVING COUNT(*) > 1"
                ) as cursor:
                    collisions = [row[0] async for row in cursor]
                if collisions:
                    joined = ", ".join(repr(key) for key in collisions)
                    raise NoteStoreError(
                        f"Cannot enforce unique note titles; duplicate normalized keys: {joined}"
                    )
            statements = MIGRATIONS.get(target, [])
            for stmt in statements:
                try:
                    await db.execute(stmt)
                except aiosqlite.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(CURRENT_SCHEMA_VERSION),),
        )

    async def _load_into_memory(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT id, title, title_key, content, tags, created_at, modified_at, deleted_at FROM notes"
            ) as cursor:
                async for row in cursor:
                    note = _row_to_note(row)
                    if note.deleted_at:
                        self.trash[note.id] = note
                    else:
                        self.notes[note.id] = note

            async with db.execute("SELECT value FROM kv_store WHERE key = ?", (LAYOUT_KEY,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        self.layout = _validate_layout(json.loads(row[0]))
                    except (TypeError, ValueError):
                        self.layout = {}

            async with db.execute(
                "SELECT value FROM kv_store WHERE key = ?", (TAG_COLORS_KEY,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        self.tag_colors = _validate_tag_colors(json.loads(row[0]))
                    except (TypeError, ValueError):
                        self.tag_colors = {}

    def require_active_note(self, note_id: str) -> Note:
        note = self.notes.get(note_id)
        if note is None:
            raise NoteNotFoundError(f"Note {note_id!r} no longer exists.")
        return note

    def find_active_by_title(self, title: str) -> Note | None:
        key = normalize_title(title)
        if not key:
            return None
        for note in self.notes.values():
            if normalize_title(note.title) == key:
                return note
        return None

    def _title_in_use(self, key: str, exclude_id: str | None = None) -> Note | None:
        if not key:
            return None
        for source in (self.notes.values(), self.trash.values()):
            for note in source:
                if exclude_id and note.id == exclude_id:
                    continue
                if normalize_title(note.title) == key:
                    return note
        return None

    async def _duplicate_id_for_key(self, key: str) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id FROM notes WHERE title_key = ? LIMIT 1", (key,)
            ) as cursor:
                row = await cursor.fetchone()
        return str(row[0]) if row else ""

    @asynccontextmanager
    async def _writer(self):
        """Open a transactional SQLite connection.

        Commits on successful exit. ``IntegrityError`` propagates so callers
        can map it to ``DuplicateTitleError``; every other exception becomes
        a ``NoteStoreError``.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                yield db
                await db.commit()
        except aiosqlite.IntegrityError:
            raise
        except Exception as exc:
            raise NoteStoreError(str(exc)) from exc

    async def _ensure_loaded(self) -> None:
        if not self._initialized:
            await self.load()

    async def create_note(
        self, title: str, content: str = "", tags: list[str] | None = None
    ) -> Note:
        await self._ensure_loaded()
        clean_title = title_display(title)
        if not clean_title.strip():
            raise EmptyTitleError()
        if not is_valid_title(clean_title):
            raise InvalidTitleError(
                "Title must be under 200 characters and contain no control characters."
            )
        key = normalize_title(clean_title)

        async with self._write_lock:
            existing = self._title_in_use(key)
            if existing is not None:
                raise DuplicateTitleError(clean_title, existing.id)

            nid = str(uuid.uuid4())
            now = _utc_now()
            note = Note(
                id=nid,
                title=clean_title,
                content=content,
                tags=list(tags or []),
                created_at=now,
                modified_at=now,
            )

            try:
                async with self._writer() as db:
                    await db.execute(
                        "INSERT INTO notes (id, title, title_key, content, tags, created_at, modified_at, deleted_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                        (
                            note.id,
                            note.title,
                            key,
                            note.content,
                            _serialize_tags(note.tags),
                            note.created_at,
                            note.modified_at,
                        ),
                    )
            except aiosqlite.IntegrityError as exc:
                existing_id = await self._duplicate_id_for_key(key)
                raise DuplicateTitleError(clean_title, existing_id) from exc

            self.notes[note.id] = note
            return note

    async def update_note(
        self,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> Note:
        await self._ensure_loaded()
        clean_title: str | None = None
        new_key: str | None = None
        if title is not None:
            clean_title = title_display(title)
            if not clean_title.strip():
                raise EmptyTitleError()
            if not is_valid_title(clean_title):
                raise InvalidTitleError(
                    "Title must be under 200 characters and contain no control characters."
                )
            new_key = normalize_title(clean_title)

        new_tags = list(tags) if tags is not None else None

        async with self._write_lock:
            note = self.require_active_note(note_id)
            if new_key is not None and new_key != normalize_title(note.title):
                collision = self._title_in_use(new_key, exclude_id=note_id)
                if collision is not None:
                    raise DuplicateTitleError(clean_title or "", collision.id)

            updates: dict[str, Any] = {"modified_at": _utc_now()}
            if clean_title is not None:
                updates["title"] = clean_title
                updates["title_key"] = new_key
            if content is not None:
                updates["content"] = content
            if new_tags is not None:
                updates["tags"] = new_tags

            set_clause = ", ".join(f"{column} = ?" for column in updates)
            params: list[Any] = [
                value if column != "tags" else _serialize_tags(value)
                for column, value in updates.items()
            ]
            params.append(note_id)

            try:
                async with self._writer() as db:
                    await db.execute(
                        f"UPDATE notes SET {set_clause} WHERE id = ?",
                        tuple(params),
                    )
            except aiosqlite.IntegrityError as exc:
                conflict_key = new_key or normalize_title(note.title)
                existing_id = await self._duplicate_id_for_key(conflict_key)
                raise DuplicateTitleError(clean_title or note.title, existing_id) from exc

            note.modified_at = updates["modified_at"]
            if clean_title is not None:
                note.title = clean_title
            if content is not None:
                note.content = content
            if new_tags is not None:
                note.tags = new_tags
            return note

    async def delete_note(self, note_id: str) -> Note:
        await self._ensure_loaded()
        async with self._write_lock:
            note = self.require_active_note(note_id)
            deletion_stamp = _utc_now()
            async with self._writer() as db:
                await db.execute(
                    "UPDATE notes SET deleted_at = ? WHERE id = ?",
                    (deletion_stamp, note_id),
                )
                if note_id in self.layout:
                    new_layout = dict(self.layout)
                    new_layout.pop(note_id, None)
                    await db.execute(
                        "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                        (LAYOUT_KEY, json.dumps(new_layout)),
                    )

            note.deleted_at = deletion_stamp
            self.trash[note.id] = note
            self.notes.pop(note.id, None)
            self.layout.pop(note_id, None)
            return note

    async def restore_note(self, note_id: str) -> Note:
        await self._ensure_loaded()
        async with self._write_lock:
            note = self.trash.get(note_id)
            if note is None:
                raise NoteNotFoundError(f"Trashed note {note_id!r} not found.")

            key = normalize_title(note.title)
            collision = self._title_in_use(key)
            if collision is not None and collision.id != note_id:
                raise DuplicateTitleError(
                    note.title,
                    collision.id,
                )

            restore_stamp = _utc_now()
            try:
                async with self._writer() as db:
                    await db.execute(
                        "UPDATE notes SET deleted_at = NULL, modified_at = ? WHERE id = ?",
                        (restore_stamp, note_id),
                    )
            except aiosqlite.IntegrityError as exc:
                existing_id = await self._duplicate_id_for_key(key)
                raise DuplicateTitleError(note.title, existing_id) from exc

            note.deleted_at = None
            note.modified_at = restore_stamp
            self.notes[note.id] = note
            self.trash.pop(note.id, None)
            return note

    async def purge_note(self, note_id: str) -> None:
        await self._ensure_loaded()
        async with self._write_lock:
            if note_id not in self.trash and note_id not in self.notes:
                raise NoteNotFoundError(f"Note {note_id!r} not found.")
            async with self._writer() as db:
                await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))

            self.notes.pop(note_id, None)
            self.trash.pop(note_id, None)
            self.layout.pop(note_id, None)

    async def update_layout(
        self, layout_data: dict[str, tuple[float, float]]
    ) -> None:
        await self._ensure_loaded()
        validated = _validate_layout(
            {nid: list(pos) for nid, pos in layout_data.items()}
        )
        async with self._write_lock:
            async with self._writer() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                    (LAYOUT_KEY, json.dumps(validated)),
                )

            self.layout = validated

    async def save_tag_colors(self, colors: dict[str, int]) -> None:
        await self._ensure_loaded()
        validated = _validate_tag_colors(colors)
        async with self._write_lock:
            async with self._writer() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                    (TAG_COLORS_KEY, json.dumps(validated)),
                )

            self.tag_colors = validated

    async def backup_to(self, destination: Path, *, overwrite: bool = False) -> Path:
        await self._ensure_loaded()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not overwrite:
            raise NoteStoreError(
                f"Backup destination already exists: {destination}. "
                "Pass overwrite=True to replace it."
            )
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)

        try:
            async with self._write_lock:
                await asyncio.to_thread(self._backup_database, temporary)
                await asyncio.to_thread(self._verify_database, temporary)
                os.replace(temporary, destination)
                if sys.platform != "win32":
                    try:
                        os.chmod(destination, 0o600)
                    except OSError:
                        pass
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise NoteStoreError(str(exc)) from exc

        return destination

    def _backup_database(self, destination: Path) -> None:
        with sqlite3.connect(self.db_path) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)

    @staticmethod
    def _verify_database(path: Path) -> None:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise NoteStoreError("Backup integrity check failed.")

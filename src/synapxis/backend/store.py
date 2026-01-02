import json
import uuid
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .models import Note

class NoteStore:
    """
    Handles data persistence using SQLite.

    """

    def __init__(self, path: Path):
        self.db_path = path.with_suffix(".db")
        self.notes: Dict[str, Note] = {}
        self.layout: Dict[str, List[float]] = {} 
        self.tag_colors: Dict[str, int] = {} # New: Stores {"tag": color_index}
        self._db_ready = asyncio.Event()

    async def _init_db(self):
        """Creates tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    content TEXT,
                    created_at TEXT,
                    modified_at TEXT,
                    tags TEXT
                )
            """)
            # Key-Value table for layouts and settings
            await db.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.commit()
        self._db_ready.set()

    async def load(self) -> None:
        """Loads data from SQLite into memory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        await self._init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # 1. Load Notes
            async with db.execute("SELECT * FROM notes") as cursor:
                async for row in cursor:
                    tags = json.loads(row['tags']) if row['tags'] else []
                    note = Note(
                        id=row['id'],
                        title=row['title'],
                        content=row['content'],
                        created_at=row['created_at'],
                        modified_at=row['modified_at'],
                        tags=tags
                    )
                    self.notes[note.id] = note
            
            # 2. Load Layout
            async with db.execute("SELECT value FROM kv_store WHERE key='layout'") as cursor:
                row = await cursor.fetchone()
                if row:
                    self.layout = json.loads(row[0])

            # 3. Load Tag Colors (Settings)
            async with db.execute("SELECT value FROM kv_store WHERE key='tag_colors'") as cursor:
                row = await cursor.fetchone()
                if row:
                    self.tag_colors = json.loads(row[0])

    async def create_note(self, title: str, content: str = "") -> Note:
        nid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        note = Note(id=nid, title=title, content=content, created_at=now, modified_at=now)
        self.notes[nid] = note
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO notes (id, title, content, created_at, modified_at, tags) VALUES (?, ?, ?, ?, ?, ?)",
                (note.id, note.title, note.content, note.created_at, note.modified_at, json.dumps(note.tags))
            )
            await db.commit()
        return note

    async def update_note(self, note_id: str, title: str = None, content: str = None, tags: List[str] = None) -> None:
        if note_id not in self.notes: return
        
        note = self.notes[note_id]
        if title is not None: note.title = title
        if content is not None: note.content = content
        if tags is not None: note.tags = tags # Update tags in memory
        
        note.modified_at = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE notes SET title = ?, content = ?, tags = ?, modified_at = ? WHERE id = ?",
                (note.title, note.content, json.dumps(note.tags), note.modified_at, note.id)
            )
            await db.commit()

    async def delete_note(self, note_id: str) -> None:
        if note_id in self.notes:
            del self.notes[note_id]
            if note_id in self.layout:
                del self.layout[note_id]
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                await db.execute(
                    "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                    ('layout', json.dumps(self.layout))
                )
                await db.commit()
            
    async def update_layout(self, layout_data: Dict[str, Tuple[float, float]]) -> None:
        clean_layout = {k: list(v) for k, v in layout_data.items()}
        self.layout = clean_layout
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                ('layout', json.dumps(clean_layout))
            )
            await db.commit()

    async def save_tag_colors(self, colors: Dict[str, int]) -> None:
        """Saves the user's color preferences."""
        self.tag_colors = colors
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                ('tag_colors', json.dumps(colors))
            )
            await db.commit()

    def get_note_by_title(self, title: str) -> Optional[Note]:
        title_lower = title.lower().strip()
        for n in self.notes.values():
            if n.title.lower().strip() == title_lower:
                return n
        return None

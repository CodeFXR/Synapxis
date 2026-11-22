import asyncio
from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static, TextArea

from synapxis.assets import find_asset
from synapxis.backend.graph import GraphManager
from synapxis.backend.models import (
    DuplicateTitleError,
    EmptyTitleError,
    NoteNotFoundError,
    NoteStoreError,
)
from synapxis.backend.store import NoteStore
from synapxis.services.export import ExportError, ExportRequest
from synapxis.services.export import export_note as services_export_note
from synapxis.utils.parsing import escape_markup, extract_tags, normalize_title, parse_wikilinks

from ._image import HAS_IMAGE_LIB, Image
from .modals import ConfirmModal, ExportModal, NewNoteModal, SuggestionModal
from .trash import TrashScreen


@dataclass(frozen=True)
class _PendingEdit:
    """One buffered save: the latest title and content the user has typed."""

    note_id: str
    title: str
    content: str


class NoteViewScreen(Screen):

    GRAPH_REBUILD_DELAY = 0.18
    SAVE_DELAY = 0.35
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("alt+n", "new", "New"),
        Binding("alt+d", "delete", "Delete"),
        Binding("alt+f", "focus_search", "Search"),
        Binding("alt+e", "export", "Export"),
        Binding("alt+enter", "jump_link", "Follow Link"),
        Binding("alt+g", "graph_view", "Graph"),
        Binding("alt+b", "show_backlinks", "Backlinks"),
        Binding("alt+t", "open_trash", "Trash"),
        Binding("ctrl+a", "select_all", "Select All", show=False),
    ]


    def __init__(self, store: NoteStore, graph_manager: GraphManager):
        super().__init__()
        self.store = store
        self.gm = graph_manager
        self.current_note_id: str | None = None
        self._last_len = 0
        self._refreshing = False
        self._loading_widgets = False
        self._pending_graph_update: asyncio.Task | None = None
        self._pending_save: asyncio.Task | None = None
        self._pending: _PendingEdit | None = None
        self._flush_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        with Container(id="main-layout"):
            with Vertical(id="sidebar"):
                found_img = find_asset("n_v.png")
                with Vertical(id="sidebar-header-container"):
                    if HAS_IMAGE_LIB and found_img:
                        yield Image(str(found_img), id="sidebar-icon")
                    else:
                        yield Label("Note View", id="sidebar-label")
                yield Input(placeholder="⌕", id="search")
                yield ListView(id="note-list")
                yield Button("+ New Page", id="btn-new", variant="default")
                yield Button("🗑 Trash", id="btn-trash", variant="default")

            with Vertical(id="content-pane"):
                yield Label("Select a page or Alt+N: New", id="empty-state")
                yield Input(placeholder="PAGE TITLE", id="note-title", classes="hidden")
                yield TextArea(id="note-content", classes="hidden", language="markdown")

        yield Static("Alt+N: New • Alt+D: Delete (to Trash) • Alt+T: Trash • Alt+F: Search • Alt+Enter: Link • Alt+B: Backlinks • Alt+E: Export • Alt+G: Graph", id="custom-footer")

    async def on_mount(self) -> None:
        await self.refresh_list()

    async def on_screen_resume(self) -> None:
        await self.refresh_list()
        if self.current_note_id:
            await self.select_note(self.current_note_id)

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self._refreshing:
            return
        if event.item is None:
            return
        note_id = getattr(event.item, "note_id", None)
        if note_id is not None:
            await self.select_note(note_id)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        note_id = getattr(event.item, "note_id", None)
        if note_id is not None:
            await self.select_note(note_id)
            self.query_one("#note-content").focus()

    async def select_note(self, note_id: str) -> None:
        if self.current_note_id and self.current_note_id != note_id:
            await self.flush_pending()
            if (
                self._pending_graph_update is not None
                and not self._pending_graph_update.done()
            ):
                self._pending_graph_update.cancel()
                self._pending_graph_update = None
        self.current_note_id = note_id
        if not self.is_mounted:
            return
        if note_id not in self.store.notes:
            self._show_empty_state()
            return

        note = self.store.notes[note_id]

        list_view = self.query_one("#note-list", ListView)
        for item in list_view.children:
            if getattr(item, "note_id", None) == note_id:
                item.add_class("-active")
            else:
                item.remove_class("-active")

        self.query_one("#content-pane").styles.align = ("center", "top")
        self.query_one("#empty-state").add_class("hidden")
        self.query_one("#note-title").remove_class("hidden")
        self.query_one("#note-content").remove_class("hidden")

        self._loading_widgets = True
        self.query_one("#note-title", Input).value = note.title
        self.query_one("#note-content", TextArea).load_text(note.content)
        # Textual queues Changed events until after the current refresh
        # cycle. Defer the reset so the queue drains with the guard set.
        self.app.call_after_refresh(self._end_loading)
        self._last_len = len(note.content)

    def _end_loading(self) -> None:
        self._loading_widgets = False

    def _show_empty_state(self) -> None:
        self.current_note_id = None
        content_pane = self.query_one("#content-pane")
        content_pane.styles.align = ("center", "middle")
        self.query_one("#empty-state").remove_class("hidden")
        self.query_one("#note-title").add_class("hidden")
        self.query_one("#note-content").add_class("hidden")

    def _record_pending_title(self, title: str) -> None:
        self._record_pending(title=title, content=None)

    def _record_pending_content(self, content: str) -> None:
        self._record_pending(title=None, content=content)

    def _record_pending(self, *, title: str | None, content: str | None) -> None:
        note_id = self.current_note_id
        if note_id is None:
            return
        current = self.store.notes.get(note_id)
        if current is None:
            return
        existing_title = current.title
        existing_content = current.content
        if self._pending is not None and self._pending.note_id == note_id:
            existing_title = self._pending.title
            existing_content = self._pending.content
        merged_title = title if title is not None else existing_title
        merged_content = content if content is not None else existing_content
        if merged_title == current.title and merged_content == current.content:
            return
        self._pending = _PendingEdit(
            note_id=note_id, title=merged_title, content=merged_content
        )
        self._schedule_save()

    async def on_input_changed(self, event) -> None:
        if event.input.id == "search":
            await self.refresh_list()
            return
        if event.input.id == "note-title":
            if self._loading_widgets or not self.current_note_id:
                return
            note_id = self.current_note_id
            self._record_pending_title(event.value)
            list_view = self.query_one("#note-list", ListView)
            for item in list_view.children:
                if getattr(item, "note_id", None) == note_id:
                    item.query_one(Label).update(escape_markup(event.value))

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._loading_widgets or not self.current_note_id:
            return
        content = event.text_area.text
        self._record_pending_content(content)

        if len(content) > self._last_len:
            cursor = event.text_area.cursor_location
            line = event.text_area.document.get_line(cursor[0])
            col = cursor[1]
            if col >= 2 and line[col - 2:col] == "[[":
                self.show_autocomplete()
        self._last_len = len(content)

    def _schedule_save(self) -> None:
        if self._pending_save and not self._pending_save.done():
            self._pending_save.cancel()
        self._pending_save = asyncio.create_task(self._delayed_save())

    async def _delayed_save(self) -> None:
        try:
            await asyncio.sleep(self.SAVE_DELAY)
            await self.flush_pending()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._report_background_failure("save", exc)

    async def flush_pending(self) -> bool:
        current = asyncio.current_task()
        if self._pending_save and self._pending_save is not current:
            self._pending_save.cancel()
        async with self._flush_lock:
            pending = self._pending
            if pending is None:
                return True
            self._pending = None
            try:
                await self.store.update_note(
                    pending.note_id,
                    title=pending.title,
                    content=pending.content,
                    tags=extract_tags(pending.content),
                )
            except NoteStoreError as exc:
                # Keep the failed save only if no newer edit has replaced it
                # for the same note.
                if self._pending is None or self._pending.note_id != pending.note_id:
                    self._pending = pending
                prefix = "Save failed" if isinstance(exc, DuplicateTitleError) else ""
                self.notify(f"{prefix}: {exc}".strip(": "), severity="error")
                return False

            self._schedule_graph_update(note_id=pending.note_id)
            return True

    def _schedule_graph_update(self, *, note_id: str) -> None:
        if self._pending_graph_update and not self._pending_graph_update.done():
            self._pending_graph_update.cancel()
        self._pending_graph_update = asyncio.create_task(
            self._apply_graph_update(note_id)
        )

    async def _apply_graph_update(self, note_id: str) -> None:
        try:
            await asyncio.sleep(self.GRAPH_REBUILD_DELAY)
        except asyncio.CancelledError:
            return
        note = self.store.notes.get(note_id)
        if note is None:
            return
        try:
            await self.gm.sync_and_relayout(self.store.notes)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._report_background_failure("graph update", exc)

    def _report_background_failure(self, label: str, exc: BaseException) -> None:
        try:
            self.notify(
                f"Background {label} failed: {exc}",
                severity="error",
                title="Internal error",
            )
        except Exception:
            pass

    def show_autocomplete(self) -> None:
        titles = [n.title for n in self.store.notes.values()]
        ta = self.query_one("#note-content", TextArea)
        saved_cursor = ta.cursor_location

        def callback(selected) -> None:
            if not selected:
                return

            def do_insert() -> None:
                ta.focus()
                ta.cursor_location = saved_cursor
                ta.insert(f"{selected}]]")

            self.app.call_after_refresh(do_insert)

        self.app.push_screen(SuggestionModal(titles), callback)

    async def action_jump_link(self) -> None:
        if not self.current_note_id:
            return
        ta = self.query_one("#note-content", TextArea)
        cursor = ta.cursor_location
        line = ta.document.get_line(cursor[0])
        col = cursor[1]
        for link in parse_wikilinks(line):
            pattern = f"[[{link.raw}]]"
            start = line.find(pattern)
            if start == -1:
                continue
            end = start + len(pattern)
            if start <= col <= end:
                note = self.store.find_active_by_title(link.target)
                if note is not None:
                    await self.select_note(note.id)
                else:
                    self.notify(
                        f"Note {link.target!r} not found.", severity="warning"
                    )
                return

    def action_show_backlinks(self) -> None:
        if not self.current_note_id:
            return
        self.gm.build(self.store.notes, self.store.layout)
        links = self.gm.get_backlinks(self.current_note_id)
        if not links:
            self.notify("No backlinks found.", severity="information")
            return

        def on_select(selected_title: str | None) -> None:
            if not selected_title:
                return
            note = self.store.find_active_by_title(selected_title)
            if note is not None:
                self.run_worker(self.select_note(note.id))

        self.app.push_screen(SuggestionModal(links), on_select)

    async def action_export(self) -> None:
        if not self.current_note_id:
            return
        if await self.flush_pending():
            self.app.push_screen(ExportModal(), self.handle_export)

    def handle_export(self, format_type: str | None) -> None:
        if not format_type or not self.current_note_id:
            return
        if self.current_note_id not in self.store.notes:
            self.notify("Note no longer exists.", severity="error")
            return

        note_id = self.current_note_id
        note = self.store.notes[note_id]
        export_dir = Path.home() / "Documents"

        async def do_export() -> None:
            try:
                path = await services_export_note(
                    ExportRequest(
                        title=note.title,
                        content=note.content,
                        format=format_type,
                        directory=export_dir,
                    )
                )
            except ExportError as exc:
                self.notify(str(exc), severity="error")
                return
            self.notify(f"Exported to {path}")

        self.run_worker(do_export(), exclusive=True, name=f"export-{format_type}")

    async def refresh_list(self) -> None:
        self._refreshing = True
        lv = self.query_one("#note-list", ListView)
        lv.clear()
        search = (
            self.query_one("#search", Input).value.lower()
            .replace("⌕", "")
            .replace("search...", "")
            .strip()
        )
        sorted_notes = sorted(
            self.store.notes.values(), key=lambda n: normalize_title(n.title)
        )

        for n in sorted_notes:
            if search in n.title.lower():
                item = ListItem(Label(escape_markup(n.title), classes="note-label", markup=False))
                item.note_id = n.id
                if n.id == self.current_note_id:
                    item.add_class("-active")
                lv.append(item)

        self._refreshing = False

    async def action_new(self) -> None:
        if not await self.flush_pending():
            return

        def on_result(chosen_title: str | None) -> None:
            if not chosen_title:
                return
            self.run_worker(self._create_from_modal(chosen_title))

        self.app.push_screen(NewNoteModal(self.store), on_result)

    async def _create_from_modal(self, chosen_title: str) -> None:
        try:
            note = await self.store.create_note(chosen_title)
        except DuplicateTitleError as exc:
            self.notify(str(exc), severity="error")
            return
        except EmptyTitleError as exc:
            self.notify(str(exc), severity="error")
            return
        except NoteStoreError as exc:
            self.notify(f"Create failed: {exc}", severity="error")
            return
        await self.gm.sync_and_relayout(self.store.notes)
        await self.refresh_list()
        await self.select_note(note.id)
        self.query_one("#note-title").focus()

    async def action_delete(self) -> None:
        if not self.current_note_id:
            self.notify("Select a note first.", severity="warning")
            return
        if not await self.flush_pending():
            return
        note_id = self.current_note_id
        note_title = self.store.notes[note_id].title if note_id in self.store.notes else "this note"

        def on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self.run_worker(self._delete_after_confirm(note_id))

        self.app.push_screen(
            ConfirmModal(
                f"Move {note_title!r} to Trash?",
                confirm_label="Move to Trash",
            ),
            on_confirm,
        )

    async def _delete_after_confirm(self, note_id: str) -> None:
        try:
            await self.store.delete_note(note_id)
        except NoteNotFoundError:
            self.notify("Note no longer exists.", severity="warning")
        except NoteStoreError as exc:
            self.notify(f"Delete failed: {exc}", severity="error")
            return
        await self.gm.sync_and_relayout(self.store.notes)
        self._show_empty_state()
        await self.refresh_list()

    async def action_open_trash(self) -> None:
        if await self.flush_pending():
            self.app.push_screen(TrashScreen(self.store, self.gm))

    def action_select_all(self) -> None:
        if self.current_note_id:
            self.query_one("#note-content", TextArea).select_all()

    async def action_back(self) -> None:
        if await self.flush_pending():
            self.app.switch_screen("main")

    def action_focus_search(self) -> None:
        self.query_one("#search").focus()

    async def action_graph_view(self) -> None:
        if await self.flush_pending():
            self.app.switch_screen("graph")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self.run_worker(self.action_new())
        elif event.button.id == "btn-trash":
            self.run_worker(self.action_open_trash())

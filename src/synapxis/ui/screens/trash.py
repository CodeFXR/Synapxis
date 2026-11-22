from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from synapxis.backend.graph import GraphManager
from synapxis.backend.models import DuplicateTitleError, NoteStoreError
from synapxis.backend.store import NoteStore
from synapxis.utils.parsing import escape_markup

from .modals import ConfirmModal


class TrashScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "restore_selected", "Restore", show=False),
        Binding("p", "purge_selected", "Purge", show=False),
        Binding("alt+backspace", "purge_selected", "Purge", show=False),
    ]


    def __init__(self, store: NoteStore, graph_manager: GraphManager | None = None) -> None:
        super().__init__()
        self.store = store
        self.gm = graph_manager

    def compose(self) -> ComposeResult:
        with Vertical(id="trash-layout"):
            yield Label("TRASH", id="trash-header")
            yield ListView(id="trash-list")
            yield Label("Trash is empty.", id="trash-empty")
            yield Static("Esc: Back • R: Restore • Alt+Backspace: Purge • Empty trash to delete forever", id="trash-footer")

    async def on_mount(self) -> None:
        await self.reload()

    def current_trash_selection(self) -> str | None:
        list_view = self.query_one("#trash-list", ListView)
        if list_view.highlighted_child is not None:
            return getattr(list_view.highlighted_child, "note_id", None)
        return None

    async def reload(self) -> None:
        list_view = self.query_one("#trash-list", ListView)
        empty_label = self.query_one("#trash-empty", Label)
        list_view.clear()
        items = sorted(
            self.store.trash.values(),
            key=lambda n: n.deleted_at or "",
            reverse=True,
        )
        if not items:
            empty_label.remove_class("hidden")
            list_view.display = False
            return
        empty_label.add_class("hidden")
        list_view.display = True
        for note in items:
            stamp = note.deleted_at or "?"
            label = f"{escape_markup(note.title)}    [dim](deleted {stamp})[/dim]"
            item = ListItem(Label(label, classes="trash-label", markup=False))
            item.note_id = note.id
            list_view.append(item)

    async def action_restore_selected(self) -> None:
        note_id = self.current_trash_selection()
        if not note_id:
            self.notify("Pick a trashed note first.", severity="warning")
            return
        try:
            await self.store.restore_note(note_id)
        except DuplicateTitleError as exc:
            self.notify(str(exc), severity="error")
            return
        except NoteStoreError as exc:
            self.notify(str(exc), severity="error")
            return
        if self.gm is not None:
            await self.gm.sync_and_relayout(self.store.notes)
        self.notify("Note restored.")
        await self.reload()

    async def action_purge_selected(self) -> None:
        note_id = self.current_trash_selection()
        if not note_id:
            self.notify("Pick a trashed note first.", severity="warning")
            return

        def on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self.run_worker(self._purge_after_confirm(note_id))

        self.app.push_screen(
            ConfirmModal(
                "Permanently delete this note?\nThis cannot be undone.",
                confirm_label="Delete Forever",
            ),
            on_confirm,
        )

    async def _purge_after_confirm(self, note_id: str) -> None:
        try:
            await self.store.purge_note(note_id)
        except NoteStoreError as exc:
            self.notify(str(exc), severity="error")
            return
        if self.gm is not None:
            self.gm.remove_note(note_id)
        self.notify("Note permanently deleted.")
        await self.reload()

    def action_back(self) -> None:
        self.app.pop_screen()

from datetime import datetime, timezone
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

from synapxis.backend.models import NoteStoreError
from synapxis.backend.store import NoteStore


class ExportModal(ModalScreen[str]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
    ]


    def compose(self) -> ComposeResult:
        with Vertical(id="export-box"):
            yield Label("EXPORT NOTE", classes="header")
            yield Button("Markdown (.md)", id="fmt-md")
            yield Button("HTML Document (.html)", id="fmt-html")
            yield Button("PDF Document (.pdf)", id="fmt-pdf")
            yield Button("Cancel", id="cancel", variant="error")

    def on_mount(self):
        self.query_one("#fmt-md").focus()

    def action_move_up(self):
        self.focus_previous()

    def action_move_down(self):
        self.focus_next()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "fmt-md":
            self.dismiss("md")
        elif event.button.id == "fmt-html":
            self.dismiss("html")
        elif event.button.id == "fmt-pdf":
            self.dismiss("pdf")


class SuggestionListItem(ListItem):
    def __init__(self, title: str) -> None:
        self.note_title = title
        super().__init__(Label(title, markup=False))


class SuggestionModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]


    def __init__(self, titles):
        super().__init__()
        self.all_titles = titles

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label("LINK TO PAGE", classes="header")
            yield Input(placeholder="⌕", id="modal-search")
            yield ListView(id="list")

    def on_mount(self):
        self.update_list("")
        self.query_one("#modal-search").focus()

    def update_list(self, search_term: str):
        list_view = self.query_one("#list", ListView)
        list_view.clear()

        filtered = [t for t in self.all_titles if search_term.lower() in t.lower()]

        for title in filtered:
            list_view.append(SuggestionListItem(title))

        if filtered:
            list_view.index = 0

    def on_key(self, event: events.Key) -> None:
        # Manual navigation for the list view since Input has focus
        list_view = self.query_one("#list", ListView)
        if event.key == "down":
            event.prevent_default()
            event.stop()
            list_view.action_cursor_down()
        elif event.key == "up":
            event.prevent_default()
            event.stop()
            list_view.action_cursor_up()
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            # Trigger selection for the currently highlighted item
            if list_view.highlighted_child:
                self._select_item(list_view.highlighted_child)

    def on_input_changed(self, event: Input.Changed):
        self.update_list(event.value.strip())

    # This Standard Textual Event handles both Mouse Clicks and programmatic selection
    def on_list_view_selected(self, event: ListView.Selected):
        self._select_item(event.item)

    def _select_item(self, item):
        if isinstance(item, SuggestionListItem):
            self.dismiss(item.note_title)

    def action_cancel(self):
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]


    def __init__(self, message: str, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self._message, id="confirm-message")
            with Horizontal(classes="button-row"):
                yield Button(self._confirm_label, id="confirm-yes", classes="confirm")
                yield Button("Cancel", id="confirm-no")

    def on_mount(self) -> None:
        self.query_one("#confirm-no").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class NewNoteModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]


    def __init__(self, store: NoteStore, initial: str = "") -> None:
        super().__init__()
        self.store = store
        self._initial = initial
        self._error: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="new-note-box"):
            yield Label("NEW PAGE TITLE", id="new-note-message")
            yield Input(value=self._initial, placeholder="Title", id="new-note-input")
            yield Label("", id="new-note-error")
            with Horizontal(classes="button-row"):
                yield Button("Create", id="new-note-create")
                yield Button("Cancel", id="new-note-cancel")

    def on_mount(self) -> None:
        self.query_one("#new-note-input", Input).focus()

    def _show_error(self, message: str) -> None:
        self._error = message
        self.query_one("#new-note-error", Label).update(message)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new-note-input":
            self._complete(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-note-cancel":
            self.dismiss(None)
        elif event.button.id == "new-note-create":
            self._complete(self.query_one("#new-note-input", Input).value)

    def _complete(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            self._show_error("Title cannot be empty.")
            return
        existing = self.store.find_active_by_title(cleaned)
        if existing is not None:
            self._show_error(f"A note titled {cleaned!r} already exists.")
            return
        self.dismiss(cleaned)

    def action_cancel(self) -> None:
        self.dismiss(None)


class BackupModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]


    def __init__(self, store: NoteStore) -> None:
        super().__init__()
        self.store = store
        self._confirmed_overwrite = False

    def compose(self) -> ComposeResult:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        default_path = str(Path.home() / f"synapxis-backup-{stamp}.db")
        with Vertical(id="backup-box"):
            yield Label("BACKUP DATABASE", id="backup-message")
            yield Input(value=default_path, id="backup-path")
            yield Label("", id="backup-status")
            with Horizontal(classes="button-row"):
                yield Button("Save Backup", id="backup-save")
                yield Button("Cancel", id="backup-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "backup-cancel":
            self.dismiss(None)
        elif event.button.id == "backup-save":
            self._save()

    def _save(self) -> None:
        raw = self.query_one("#backup-path", Input).value.strip()
        status = self.query_one("#backup-status", Label)
        if not raw:
            status.update("Enter a destination path.")
            return
        destination = Path(raw).expanduser()
        if destination.exists() and not self._confirmed_overwrite:
            self._confirmed_overwrite = True
            status.update(
                f"Destination exists. Click Save Backup again to overwrite {destination}."
            )
            return

        async def do_backup() -> None:
            if not await self.app.flush_pending_edits():
                status.update("Save pending note edits before backup.")
                return
            try:
                saved_to = await self.store.backup_to(destination, overwrite=True)
            except NoteStoreError as exc:
                self.notify(str(exc), severity="error")
                status.update(f"Failed: {exc}")
                return
            self.notify(f"Backup saved to {saved_to}")
            self.dismiss(str(saved_to))

        self.run_worker(do_backup())

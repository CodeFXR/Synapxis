from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from synapxis._art import ASCII_LOGO
from synapxis.assets import find_asset

from ._image import HAS_IMAGE_LIB, Image
from .modals import BackupModal
from .settings import SettingsScreen


class MainMenuScreen(Screen):
    BINDINGS = [
        Binding("n", "switch_notes", "Notes"),
        Binding("g", "switch_graph", "Graph"),
        Binding("s", "switch_settings", "Settings"),
        Binding("b", "open_backup", "Backup"),
        Binding("q", "quit", "Quit"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
    ]
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            found_img = find_asset("synapxis_icon.png")
            with Container(id="logo-container"):
                if HAS_IMAGE_LIB and found_img:
                    yield Image(str(found_img), id="logo-image")
                else:
                    yield Static(self._get_ascii_logo(), id="logo-ascii")
            yield Static("[i]Map Your Mind![/i]", classes="menu-title")
            with Vertical(id="menu-buttons"):
                yield Button("Note View (N)", id="btn-notes")
                yield Button("Graph View (G)", id="btn-graph")
                yield Button("Settings (S)", id="btn-settings")
                yield Button("Backup Database (B)", id="btn-backup")
                yield Button("Quit (Q)", id="btn-quit")
            yield Static("Use Tab, ↑↓, or Mouse to navigate • Enter to Select", classes="nav-help")
    def on_mount(self): self.query_one("#btn-notes").focus()
    def action_switch_notes(self): self.app.switch_screen("notes")
    def action_switch_graph(self): self.app.switch_screen("graph")
    def action_switch_settings(self): self.app.push_screen(SettingsScreen(self.app.store))
    def action_open_backup(self): self.app.push_screen(BackupModal(self.app.store))
    async def action_quit(self):
        await self.app.flush_pending_edits()
        self.app.exit()
    def action_move_up(self): self.focus_previous()
    def action_move_down(self): self.focus_next()
    def on_button_pressed(self, e):
        if e.button.id == "btn-notes":
            self.action_switch_notes()
        elif e.button.id == "btn-graph":
            self.action_switch_graph()
        elif e.button.id == "btn-settings":
            self.action_switch_settings()
        elif e.button.id == "btn-backup":
            self.action_open_backup()
        elif e.button.id == "btn-quit":
            self.run_worker(self.action_quit())
    def _get_ascii_logo(self) -> str:
        return ASCII_LOGO

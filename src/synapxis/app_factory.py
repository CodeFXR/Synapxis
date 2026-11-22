import asyncio
import os
from importlib import resources
from pathlib import Path

from textual.app import App

from synapxis.backend.graph import GraphManager
from synapxis.backend.store import NoteStore
from synapxis.ui.screens import (
    GraphViewScreen,
    MainMenuScreen,
    NoteViewScreen,
)


def default_data_path() -> Path:
    """Return the SQLite database path for the current install.

    The database is always named ``notes.db`` and lives inside the
    data directory. ``SYNAPXIS_DATA_DIR`` sets the directory; the
    default is ``~/.synapxis/``. The contract is documented in
    ``readme.md`` and pinned by ``tests/test_data_path.py``.
    """
    env = os.environ.get("SYNAPXIS_DATA_DIR")
    if env:
        return Path(env).expanduser() / "notes.db"
    return Path.home() / ".synapxis" / "notes.db"


class SynapxisApp(App):
    CSS_PATH = Path(
        str(resources.files("synapxis.ui.screens").joinpath("styles.tcss"))
    )

    def __init__(self, data_path: Path):
        super().__init__()
        self.store = NoteStore(data_path)
        self.graph_manager = GraphManager()

    async def on_mount(self):
        await self.store.load()
        await asyncio.to_thread(
            self.graph_manager.build, self.store.notes, self.store.layout
        )

        self.install_screen(MainMenuScreen(), name="main")
        self.install_screen(NoteViewScreen(self.store, self.graph_manager), name="notes")
        self.install_screen(GraphViewScreen(self.store, self.graph_manager), name="graph")
        self.push_screen("main")

    async def flush_pending_edits(self) -> bool:
        """Flush any pending edits in the notes screen. Returns True on success."""
        try:
            notes_screen = self.get_screen("notes")
        except KeyError:
            return True
        flush = getattr(notes_screen, "flush_pending", None)
        if flush is None:
            return True
        return await flush()


def make_app_for_testing(data_path: Path) -> SynapxisApp:
    return SynapxisApp(data_path)


def cli_main() -> None:
    app = SynapxisApp(default_data_path())
    app.run()


if __name__ == "__main__":
    cli_main()

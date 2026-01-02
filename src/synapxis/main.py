import sys
import asyncio
from pathlib import Path
from textual.app import App

from synapxis.backend.store import NoteStore
from synapxis.backend.graph import GraphManager
from synapxis.ui.screens import MainMenuScreen, NoteViewScreen, GraphViewScreen

class SynapxisApp(App):
    # Global Theme Settings
    CSS = """
    Screen { background: #1a1b26; color: #c0caf5; }
    
    /* Toast Notifications */
    Toast {
        background: #1f2335;
        color: #c0caf5;
        border-left: wide orange;
        padding: 1 2;
    }
    ToastTitle { color: orange; text-style: bold; }
    
    /* Scrollbars - Global Theme */
    ScrollBarThumb { background: orange; }
    ScrollBarThumb:hover { background: #ffb700; }
    
    /* Global Input Reset */
    Input {
        background: #1f2335;
        border: none;
        color: #c0caf5;
    }
    Input:focus {
        border: none;
        color: orange;
    }
    """

    def __init__(self):
        super().__init__()
        data_path = Path.home() / ".synapxis_v2" / "notes.db"
        self.store = NoteStore(data_path)
        self.graph_manager = GraphManager()

    async def on_mount(self):
        await self.store.load()
        self.graph_manager.build(self.store.notes, self.store.layout)
        
        self.install_screen(MainMenuScreen(), name="main")
        self.install_screen(NoteViewScreen(self.store, self.graph_manager), name="notes")
        self.install_screen(GraphViewScreen(self.store, self.graph_manager), name="graph")
        self.push_screen("main")

def run():
    app = SynapxisApp()
    app.run()

if __name__ == "__main__":
    run()

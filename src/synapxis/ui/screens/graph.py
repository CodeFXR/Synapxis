import asyncio

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from synapxis.assets import find_asset
from synapxis.backend.graph import GraphManager
from synapxis.backend.store import NoteStore
from synapxis.ui.widgets.graph_widget import GraphWidget

from ._image import HAS_IMAGE_LIB, Image


class GraphViewScreen(Screen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("f", "toggle_search", "Find Node"),
        ("alt+n", "switch_to_notes", "Notes"),
        ("up", "pan(0, 5)", "Up"),
        ("down", "pan(0, -5)", "Down"),
        ("left", "pan(5, 0)", "Left"),
        ("right", "pan(-5, 0)", "Right"),
        ("+", "zoom(1.1)", "Zoom In"),
        ("-", "zoom(0.9)", "Zoom Out"),
    ]
    def __init__(self, store: NoteStore, graph_manager: GraphManager):
        super().__init__()
        self.store = store
        self.gm = graph_manager

    def compose(self) -> ComposeResult:
        with Vertical(id="graph-header"):
            found_img = find_asset("g_v.png")
            if HAS_IMAGE_LIB and found_img:
                yield Image(str(found_img), id="header-logo")
            else:
                yield Label("Graph View", id="header-label")

        yield GraphWidget(self.gm, self.store)
        yield Static("", id="graph-info")

        with Container(id="search-container"):
            yield Input(placeholder="⌕", id="graph-search")

    async def on_mount(self):
        await asyncio.to_thread(self.gm.build, self.store.notes, self.store.layout)
        self.update_stats()
        self.query_one(GraphWidget).focus()

    async def on_screen_resume(self):
        await asyncio.to_thread(self.gm.build, self.store.notes, self.store.layout)
        self.query_one(GraphWidget).refresh()
        self.update_stats()

    def update_stats(self):
        nodes = len(self.store.notes)
        text = f"Nodes: {nodes} • Links: {self.gm.edge_count()}   (Alt+N: Notes • Click node to Open • F: Search • Drag node to Move • ↑↓←→ to Pan • + - or Wheel to Zoom)"
        self.query_one("#graph-info", Static).update(text)

    def action_pan(self, x, y): self.query_one(GraphWidget).action_pan(x, y)
    def action_zoom(self, amount): self.query_one(GraphWidget).action_zoom(amount)

    def action_toggle_search(self):
        cont = self.query_one("#search-container")
        if cont.has_class("-visible"):
            cont.remove_class("-visible")
            self.query_one(GraphWidget).focus()
        else:
            cont.add_class("-visible")
            self.query_one("#graph-search").focus()

    def on_input_submitted(self, event):
        if event.input.id == "graph-search":
            target = self.store.find_active_by_title(event.value.replace("⌕", "").strip())
            if target:
                self.query_one(GraphWidget).center_on_node(target.id)
                self.query_one("#search-container").remove_class("-visible")
                self.query_one(GraphWidget).focus()
                self.notify(f"Found: {target.title}")
            else:
                self.notify("Node not found", severity="error")

    async def on_graph_widget_selected(self, message):
        notes_screen = self.app.get_screen("notes")
        select_note = getattr(notes_screen, "select_note", None)
        if select_note is not None:
            await select_note(message.node_id)
        self.app.switch_screen("notes")

    async def on_graph_widget_layout_updated(self, message):
        new_layout = self.gm.get_layout_data()
        await self.store.update_layout(new_layout)

    def action_back(self):
        if self.query_one("#search-container").has_class("-visible"):
            self.query_one("#search-container").remove_class("-visible")
            self.query_one(GraphWidget).focus()
        else:
            self.app.switch_screen("main")

    def action_switch_to_notes(self):
        self.app.switch_screen("notes")

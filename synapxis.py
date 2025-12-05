from __future__ import annotations

# ---------------------------------------------------------
# Imports & Dependencies
# ---------------------------------------------------------

from dataclasses import dataclass, field
from pathlib import Path
import json
import uuid
import subprocess
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Check for NetworkX (Math library for Graphs)
try:
    import networkx as nx
    # Community detection for "Auto-Coloring" clusters
    import networkx.algorithms.community as nx_comm
except ImportError:
    print("Error: networkx (and scipy/numpy) are required. Please install: pip install networkx scipy numpy")
    exit(1)

# Check for Rust Backend (The high-speed renderer)
try:
    import synapxis_rs
    HAS_RUST_BACKEND = True
except ImportError:
    HAS_RUST_BACKEND = False
    # Suppress warning to keep TUI start clean

# Check for Image Library (Displays the PNG logo)
try:
    from textual_image.widget import Image
    HAS_IMAGE_LIB = True
except ImportError:
    HAS_IMAGE_LIB = False

from rich.text import Text
from rich.style import Style

# Textual UI Framework Imports
from textual import events
from textual.app import App, ComposeResult
from textual.widgets import (
    Footer, Static, Input, ListView, ListItem, 
    Label, Button, TextArea
)
from textual.containers import Vertical, Container, Center, Horizontal
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.message import Message
from textual.events import Click, ScreenResume


# ---------------------------------------------------------
# Data Model (Notes & Storage)
# ---------------------------------------------------------

@dataclass
class Note:
    """Represents a single Zettel/Note."""
    id: str
    title: str
    content: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""


class NoteStore:
    """
    Handles saving/loading notes to JSON.
    Automatically parses [[Wikilinks]] to build the Graph.
    """

    def __init__(self, path: Path):
        self.path = path
        self.notes: Dict[str, Note] = {}
        self.links: List[Tuple[str, str]] = []
        self.layout: Dict[str, List[float]] = {} # Stores (x,y) positions
        self.load()

    def load(self) -> None:
        """Reads JSON from disk."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            return

        try:
            with self.path.open("r", encoding="utf8") as f:
                content = f.read().strip()
                data = json.loads(content) if content else {}

            notes = data.get("notes", [])
            self.notes = {n["id"]: Note(**n) for n in notes}
            self.layout = data.get("layout", {}) # Load positions
            self._rebuild_links()
            
        except (json.JSONDecodeError, FileNotFoundError):
            self.notes = {}
            self.links = []
            self.layout = {}

    def save(self) -> None:
        """Writes current state to JSON."""
        self._rebuild_links()
        
        # Always write to file to prevent zombie notes on deletion
        data = {
            "notes": [vars(n) for n in self.notes.values()],
            "links": self.links,
            "layout": self.layout, # Save positions
        }
        
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf8") as f:
            json.dump(data, f, indent=2)

    def update_layout(self, layout_data: Dict[str, Tuple[float, float]]) -> None:
        """Updates the graph coordinates and saves to disk."""
        self.layout = {k: list(v) for k, v in layout_data.items()}
        self.save()

    def _rebuild_links(self) -> None:
        """Scans content for [[Title]] patterns to create graph edges."""
        self.links = []
        title_map = {n.title.lower().strip(): n.id for n in self.notes.values()}
        
        for note in self.notes.values():
            matches = re.findall(r"\[\[(.*?)\]\]", note.content)
            for link_title in matches:
                clean_title = link_title.strip().lower()
                target_id = title_map.get(clean_title)
                
                # Only link if the target note actually exists
                if target_id and target_id != note.id:
                    pair = tuple(sorted((note.id, target_id)))
                    if pair not in self.links:
                        self.links.append(pair)

    def create_note(self, title: str, content: str = "") -> Note:
        """Creates a new note and logs to 'jrnl' if available."""
        nid = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        note = Note(id=nid, title=title, content=content, created_at=now, modified_at=now)
        self.notes[nid] = note
        self.save()
        self._create_jrnl_entry(title, content)
        return note

    def update_note(self, note_id: str, title: str = None, content: str = None) -> None:
        if note_id in self.notes:
            note = self.notes[note_id]
            if title is not None: note.title = title
            if content is not None: note.content = content
            note.modified_at = datetime.now().isoformat()
            self.save()

    def _create_jrnl_entry(self, title: str, content: str) -> bool:
        """Optional integration with the 'jrnl' CLI tool."""
        try:
            subprocess.run(["jrnl", "--version"], capture_output=True, check=True)
            entry_text = f"{title}: {content}" if content else title
            subprocess.run(["jrnl", entry_text], input="", capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def delete_note(self, note_id: str) -> None:
        if note_id in self.notes:
            del self.notes[note_id]
            # Clean up layout data
            if note_id in self.layout:
                del self.layout[note_id]
            self.save()

    def graph(self) -> nx.Graph:
        """Converts internal data to a NetworkX Graph object."""
        g = nx.Graph()
        for n in self.notes.values():
            g.add_node(n.id, title=n.title)
        for a, b in self.links:
            if a in self.notes and b in self.notes:
                g.add_edge(a, b)
        return g

    def find_by_title(self, title: str) -> Optional[Note]:
        """Case-insensitive search."""
        title_lower = title.lower().strip()
        for n in self.notes.values():
            if n.title.lower().strip() == title_lower:
                return n
        for n in self.notes.values():
            if title_lower in n.title.lower():
                return n
        return None


# ---------------------------------------------------------
# UI: Main Menu
# ---------------------------------------------------------

class MainMenuScreen(Screen):
    """The landing screen with the Logo."""
    
    # Priority True ensures these keys work even if a widget has focus
    BINDINGS = [
        Binding("n", "note_view", "Notes", show=True, priority=True),
        Binding("g", "graph_view", "Graph", show=True, priority=True),
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("up", "move_up", "Up", show=False, priority=True),
        Binding("down", "move_down", "Down", show=False, priority=True),
    ]

    CSS = """
    MainMenuScreen { align: center middle; background: $surface; }
    
    #menu-container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 2;
    }
    
    #logo-container {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 2;
    }
    
    #logo-image { 
        height: 14; 
        width: auto; 
    }
    
    .menu-title { 
        width: 100%; 
        text-align: center; 
        color: $text-muted; 
        text-style: bold; 
        margin-bottom: 3; 
    }
    
    #menu-buttons { 
        width: 100%; 
        height: auto; 
        align: center middle; 
    }
    
    #menu-buttons Button { 
        width: auto; 
        min-width: 30; 
        margin: 1; 
        background: transparent; 
        color: $text; 
        border: none; 
    }
    
    #menu-buttons Button:focus, #menu-buttons Button:hover { 
        background: transparent; 
        color: $accent; 
        text-style: bold; 
    }
    
    .nav-help { 
        width: 100%; 
        text-align: center; 
        color: $text-muted; 
        margin-top: 4; 
        text-style: italic; 
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            base_dir = Path(__file__).parent.resolve()
            icon_path = base_dir / "synapxis_icon.png"

            # Logo Section
            with Container(id="logo-container"):
                if HAS_IMAGE_LIB and icon_path.exists():
                    yield Image(str(icon_path), id="logo-image")
                else:
                    yield Static(self._get_logo(), id="logo")
            
            # Title
            yield Static("[i]Map Your Mind![/i]", classes="menu-title")
            
            # Buttons
            with Vertical(id="menu-buttons"):
                yield Button("Note View (N)", id="btn-notes")
                yield Button("Graph View (G)", id="btn-graph")
                yield Button("Quit (Q)", id="btn-quit")
            
            # Footer Help
            yield Static("Use Tab, ↑↓, or Mouse to navigate • Enter to Select", classes="nav-help")

    def on_mount(self) -> None:
        self.query_one("#btn-notes").focus()

    def action_move_up(self) -> None:
        self.focus_previous()

    def action_move_down(self) -> None:
        self.focus_next()

    def _get_logo(self) -> str:
        return """
███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ██╗  ██╗██╗███████╗
██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗╚██╗██╔╝██║██╔════╝
███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝ ╚███╔╝ ██║███████╗
╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝  ██╔██╗ ██║╚════██║
███████║   ██║   ██║ ╚████║██║  ██║██║     ██╔╝ ██╗██║███████║
╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝
"""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-notes": self.app.push_screen("notes")
        elif event.button.id == "btn-graph": self.app.push_screen("graph")
        elif event.button.id == "btn-quit": self.app.exit()

    def on_key(self, event: events.Key) -> None:
        if event.key == "n": self.app.push_screen("notes")
        elif event.key == "g": self.app.push_screen("graph")
        elif event.key == "q": self.app.exit()


# ---------------------------------------------------------
# UI: Suggestion Modal (Autocomplete)
# ---------------------------------------------------------

class SuggestionModal(ModalScreen[str]):
    """Popup that shows list of notes when you type '[['."""
    
    CSS = """
    SuggestionModal { align: center middle; background: rgba(0, 0, 0, 0.4); }
    #suggestion-container { width: 45; height: auto; max-height: 18; background: $surface-darken-2; border: none; padding: 0; }
    #suggestion-label { dock: top; width: 100%; text-align: center; background: $accent; color: $surface; text-style: bold; }
    #suggestion-list { height: auto; max-height: 15; border: none; scrollbar-gutter: stable; }
    #suggestion-list ListItem { padding: 1 2; background: transparent; color: $text-muted; }
    #suggestion-list > ListItem:hover { background: $surface-lighten-1; color: $accent; text-style: bold; }
    """

    def __init__(self, notes: List[Note]):
        super().__init__()
        self.notes = notes

    def compose(self) -> ComposeResult:
        with Container(id="suggestion-container"):
            yield Label("LINK TO PAGE", id="suggestion-label")
            yield ListView(id="suggestion-list")

    def on_mount(self) -> None:
        list_view = self.query_one("#suggestion-list", ListView)
        for note in sorted(self.notes, key=lambda n: n.title.lower()):
            item = ListItem(Label(note.title))
            item.title = note.title  # type: ignore
            list_view.append(item)
        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        title = getattr(event.item, "title", "")
        self.dismiss(title)


# ---------------------------------------------------------
# UI: Note View (Sidebar + Editor)
# ---------------------------------------------------------

class NoteViewScreen(Screen):
    """The main workspace with list and text editor."""
    
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("alt+n", "new_note", "New"),
        Binding("alt+d", "delete_note", "Delete"),
        Binding("alt+f", "focus_search", "Search"),
        Binding("alt+g", "graph_view", "Graph"),
        Binding("alt+enter", "jump_to_link", "Open Link"),
    ]

    CSS = """
    NoteViewScreen { background: $surface; }
    ScrollBarThumb { background: $accent; }
    #main-container { width: 100%; height: 1fr; layout: horizontal; }
    
    /* Sidebar */
    #sidebar { width: 25%; height: 100%; background: $surface-darken-1; border-right: solid $surface-lighten-1; }
    #sidebar-header { width: 100%; height: 3; content-align: center middle; color: $accent; text-style: bold; background: $surface-darken-2; dock: top; }
    #sidebar-search { height: 1; border: none; background: $surface-darken-2; padding: 0 2; margin-bottom: 1; text-align: center; }
    .note-list { height: 1fr; border: none; background: transparent; }
    .note-list > ListItem { background: transparent; color: $text-muted; padding: 1 2; }
    .note-list > ListItem.-active { color: $accent; text-style: bold; }
    #create-btn { dock: bottom; width: 100%; height: auto; min-height: 3; background: transparent; color: $text-muted; border: none; }
    #create-btn:hover { color: $accent; text-style: bold; }

    /* Content Pane */
    #content-pane { width: 75%; height: 100%; background: $surface; padding: 2 4; align: center middle; }
    #empty-state { content-align: center middle; color: $text-muted; text-style: italic; }
    #title-input { dock: top; height: 3; border: none; background: transparent; text-style: bold; text-align: center; color: $accent; }
    #content-area { height: 1fr; border: none; background: transparent; padding: 1 0; }
    TextArea .text-area--cursor-line { background: transparent; }
    .hidden { display: none; }
    
    /* Footer Navigation - Fixed Height to Match Graph View */
    .nav-help { 
        dock: bottom; 
        width: 100%; 
        height: 3; 
        content-align: center middle;
        color: $text-muted; 
        background: black; 
        opacity: 0.8; 
    }
    """

    def __init__(self, store: NoteStore, target_note_id: Optional[str] = None):
        super().__init__()
        self.store = store
        self._current_note_id = target_note_id
        self._ignore_changes = False
        self._filter_text = ""
        self._last_content_len = 0
        self._refreshing = False

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            with Vertical(id="sidebar"):
                yield Label("SYNAPXIS", id="sidebar-header")
                yield Input(placeholder="⌕", id="sidebar-search")
                yield ListView(classes="note-list")
                yield Button("+ New Page", id="create-btn", variant="default")
            
            with Vertical(id="content-pane"):
                yield Label("Select a page or Alt+N: New", id="empty-state")
                yield Input(placeholder="PAGE TITLE", id="title-input", classes="hidden")
                yield TextArea(id="content-area", classes="hidden", show_line_numbers=False, language="markdown")
        
        yield Static("Alt+N: New • Alt+D: Delete • Alt+F: Search • Alt+Enter: Open Link • Alt+G: Graph", classes="nav-help")

    def on_mount(self) -> None:
        self._refresh_list(preserve_selection=self._current_note_id)
        if self._current_note_id:
            self._load_note_into_editor(self._current_note_id)
            self.query_one("#content-area").focus()
        else:
            self._show_empty_state()

    def select_note(self, note_id: str) -> None:
        """API to switch note from other screens (like graph)."""
        self._current_note_id = note_id
        if self.is_mounted and note_id in self.store.notes:
            self._load_note_into_editor(note_id)
            self._refresh_list(preserve_selection=note_id)
            self.query_one("#content-area").focus()

    def action_graph_view(self) -> None: self.app.switch_screen("graph")
    def action_focus_search(self) -> None: self.query_one("#sidebar-search").focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Auto-save content and trigger autocomplete."""
        if self._ignore_changes or not self._current_note_id: return
        
        if event.text_area.id == "content-area":
            current_text = event.text_area.text
            self.store.update_note(self._current_note_id, content=current_text)
            
            # Autocomplete Logic
            if len(current_text) > self._last_content_len: # Only on typing, not deleting
                cursor_loc = event.text_area.cursor_location
                line = event.text_area.document.get_line(cursor_loc[0])
                if cursor_loc[1] >= 2 and line[cursor_loc[1]-2:cursor_loc[1]] == "[[":
                    self._open_suggestion_modal()
            self._last_content_len = len(current_text)

    def _open_suggestion_modal(self) -> None:
        def on_select(title: str | None) -> None:
            if title:
                editor = self.query_one("#content-area", TextArea)
                editor.insert(f"{title}]]")
                self.store.update_note(self._current_note_id, content=editor.text)
        self.app.push_screen(SuggestionModal(list(self.store.notes.values())), on_select)

    def action_jump_to_link(self) -> None:
        """Follow the [[Link]] under the cursor."""
        editor = self.query_one("#content-area", TextArea)
        cursor = editor.cursor_location
        line = editor.document.get_line(cursor[0])
        col = cursor[1]
        
        matches = list(re.finditer(r"\[\[(.*?)\]\]", line))
        for m in matches:
            if m.start() <= col <= m.end():
                target = m.group(1)
                note = self.store.find_by_title(target)
                if note:
                    self._load_note_into_editor(note.id)
                    self._refresh_list(preserve_selection=note.id)
                else:
                    self.notify(f"Note '{target}' not found!", severity="warning")
                return

    def _refresh_list(self, preserve_selection: str = None) -> None:
        """Rebuilds the sidebar list."""
        self._refreshing = True
        sidebar = self.query_one("#sidebar")
        for old in self.query(".note-list"): old.remove()
        
        notes = sorted(self.store.notes.values(), key=lambda n: n.title.lower())
        if self._filter_text:
            notes = [n for n in notes if self._filter_text.lower() in n.title.lower()]
            
        items = []
        target_idx = 0
        for i, note in enumerate(notes):
            item = ListItem(Label(note.title))
            item.note_id = note.id # type: ignore
            items.append(item)
            if note.id == preserve_selection: target_idx = i

        new_list = ListView(*items, classes="note-list")
        search = self.query_one("#sidebar-search")
        sidebar.mount(new_list, after=search)
        
        if items: new_list.index = target_idx
        
        # Debounce refresh flag
        def release():
            self._refreshing = False
            if self._current_note_id: self._highlight_active_note(self._current_note_id)
        self.set_timer(0.05, release)

    def _highlight_active_note(self, note_id: str) -> None:
        try:
            for item in self.query_one(".note-list", ListView).children:
                if getattr(item, "note_id", None) == note_id: item.add_class("-active")
                else: item.remove_class("-active")
        except: pass

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if not self._refreshing and event.item:
            nid = getattr(event.item, "note_id", None)
            if nid: self._load_note_into_editor(nid)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.query_one("#content-area").focus()

    def _load_note_into_editor(self, note_id: str) -> None:
        note = self.store.notes.get(note_id)
        if not note: return
        
        self._current_note_id = note_id
        self._hide_empty_state()
        self._highlight_active_note(note_id)
        
        self._ignore_changes = True
        self.query_one("#title-input", Input).value = note.title
        self.query_one("#content-area", TextArea).load_text(note.content)
        self._last_content_len = len(note.content)
        self._ignore_changes = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "sidebar-search":
            self._filter_text = event.value
            self._refresh_list()
        elif event.input.id == "title-input" and self._current_note_id:
            self.store.update_note(self._current_note_id, title=event.value)
            # Update label in list
            for item in self.query_one(".note-list").children:
                if getattr(item, "note_id", None) == self._current_note_id:
                    item.query_one(Label).update(event.value)

    def action_new_note(self) -> None:
        base = "Untitled"
        c = 1
        while self.store.find_by_title(base):
            c += 1
            base = f"Untitled {c}"
        
        note = self.store.create_note(base, "")
        self._load_note_into_editor(note.id)
        self._refresh_list(preserve_selection=note.id)
        self.call_after_refresh(lambda: self.query_one("#title-input").focus())

    def action_delete_note(self) -> None:
        if not self._current_note_id: return

        # 1. Delete the note
        self.store.delete_note(self._current_note_id)
        self._current_note_id = None
        
        # 2. Check if we have notes left to select
        remaining_notes = sorted(self.store.notes.values(), key=lambda n: n.title.lower())
        
        if remaining_notes:
            # Select the first available note automatically
            new_selection = remaining_notes[0]
            self._load_note_into_editor(new_selection.id)
            self._refresh_list(preserve_selection=new_selection.id)
        else:
            # Truly empty: show empty state
            self._refresh_list()
            self._show_empty_state()
            self.query_one(".note-list").focus()
    
    def _show_empty_state(self):
        self.query_one("#empty-state").remove_class("hidden")
        self.query_one("#title-input").add_class("hidden")
        self.query_one("#content-area").add_class("hidden")

    def _hide_empty_state(self):
        self.query_one("#empty-state").add_class("hidden")
        self.query_one("#title-input").remove_class("hidden")
        self.query_one("#content-area").remove_class("hidden")

    def action_back(self) -> None: self.app.pop_screen()
    def on_button_pressed(self, event: Button.Pressed) -> None: self.action_new_note()


# ---------------------------------------------------------
# UI: Visualization (The Graph)
# ---------------------------------------------------------

class InteractiveGraph(Static):
    """
    Renders the node graph.
    - Uses Rust for rendering (HD Braille).
    - Includes Python fallback if Rust missing.
    - Uses NetworkX for layout.
    - Handles Dragging, Zooming, and Spotlight logic.
    """
    
    can_focus = True # Allow this widget to receive keyboard events (Arrow Keys)

    class NodeSelected(Message):
        def __init__(self, node_id: str):
            self.node_id = node_id
            super().__init__()

    class LayoutUpdated(Message):
        """Emitted when the user changes the graph structure (dragging)."""
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._graph: Optional[nx.Graph] = None
        self._pos: Dict[str, Tuple[float, float]] = {}  # STABILITY: Persist positions
        self._click_map: Dict[Tuple[int, int], str] = {}
        
        # Camera
        self._zoom_level: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        
        # Interaction (Spotlight & Dragging)
        self._hover_node_id: Optional[str] = None
        self._drag_node_id: Optional[str] = None
        self._is_dragging_active: bool = False
        self._last_mouse_x: int = 0
        self._last_mouse_y: int = 0

    def set_graph(self, graph: nx.Graph, layout: Dict[str, List[float]] = None) -> None:
        """
        Calculates layout.
        If 'layout' is provided (from disk), we use that to pin nodes.
        """
        self._graph = graph
        
        if self._graph and len(self._graph.nodes) > 0:
            try:
                # 1. Load Saved Positions if available
                if layout:
                    self._pos = {k: tuple(v) for k, v in layout.items()}
                
                # 2. Check for new nodes that don't have positions yet
                new_nodes = [n for n in self._graph.nodes if n not in self._pos]
                
                # 3. If NO positions exist (first run ever), run full physics
                if not self._pos:
                    self._pos = nx.spring_layout(
                        self._graph, 
                        seed=42, 
                        iterations=60, 
                        center=(0,0), 
                        scale=0.6
                    )
                # 4. If we have partial positions (new notes added), place new ones randomly
                elif new_nodes:
                    import random
                    for n in new_nodes:
                        self._pos[n] = (random.uniform(-0.1, 0.1), random.uniform(-0.1, 0.1))
            except Exception:
                self._pos = {}
        self.refresh()

    def get_layout(self) -> Dict[str, Tuple[float, float]]:
        return self._pos

    def center_on_node(self, node_id: str) -> None:
        """Animates/Snaps camera to specific node."""
        if node_id in self._pos:
            tx, ty = self._pos[node_id]
            width = self.content_size.width
            height = self.content_size.height
            
            # Reset Zoom to standard level so user can see context
            self._zoom_level = 1.0
            
            # Calculate Pan to center the target (tx, ty)
            # screen_x = center_x + pan_x + (tx * scale * zoom)
            # We want screen_x = center_x. So pan_x = -(tx * scale * zoom)
            base_scale_x = width / 3
            base_scale_y = height / 3
            
            self._pan_x = -(tx * base_scale_x)
            self._pan_y = -(ty * base_scale_y)
            
            # Highlight it
            self._hover_node_id = node_id
            self.refresh()

    # --- Zoom & Pan Actions ---
    def zoom_in(self) -> None:
        self._zoom_level *= 1.2
        self.refresh()

    def zoom_out(self) -> None:
        self._zoom_level *= 0.8
        self.refresh()
        
    def zoom_reset(self) -> None:
        self._zoom_level = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.refresh()

    def pan(self, x: int, y: int) -> None:
        sensitivity = 2.0 / self._zoom_level
        self._pan_x += x * sensitivity
        self._pan_y += y * sensitivity
        self.refresh()

    # --- Mouse Interaction Logic ---
    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.zoom_in()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.zoom_out()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start dragging."""
        self.focus() # Ensure keys work if we click the graph
        if self._hover_node_id:
            self._drag_node_id = self._hover_node_id
            self._is_dragging_active = False # Reset drag flag
            self._last_mouse_x = event.x
            self._last_mouse_y = event.y
            self.capture_mouse() 

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """End dragging."""
        was_dragging = self._is_dragging_active

        if self._drag_node_id:
            self.release_mouse()
            self._drag_node_id = None
            self._is_dragging_active = False
        
        # If we were dragging, we need to save the new layout!
        if was_dragging:
            self.post_message(self.LayoutUpdated())
        
        # Only open the note if we were NOT dragging
        if not was_dragging and self._hover_node_id:
            self.post_message(self.NodeSelected(self._hover_node_id))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Handles both Spotlight (Hover) and Dragging math."""
        
        # 1. DRAGGING LOGIC
        if self._drag_node_id:
            if not self._is_dragging_active:
                if abs(event.x - self._last_mouse_x) > 0 or abs(event.y - self._last_mouse_y) > 0:
                    self._is_dragging_active = True

            if self._is_dragging_active:
                dx_screen = event.x - self._last_mouse_x
                dy_screen = event.y - self._last_mouse_y
                self._last_mouse_x = event.x
                self._last_mouse_y = event.y
                
                # Inverse Projection: Convert pixels back to graph coordinates
                width = self.content_size.width
                height = self.content_size.height
                base_scale_x = width / 3
                base_scale_y = height / 3
                
                if base_scale_x > 0 and base_scale_y > 0:
                    dx_graph = dx_screen / (base_scale_x * self._zoom_level)
                    dy_graph = dy_screen / (base_scale_y * self._zoom_level)
                    
                    if self._drag_node_id in self._pos:
                        old_x, old_y = self._pos[self._drag_node_id]
                        self._pos[self._drag_node_id] = (old_x + dx_graph, old_y + dy_graph)
                        self.refresh()
            return

        # 2. SPOTLIGHT (HOVER) LOGIC
        hover_id = self._click_map.get((event.y, event.x))
        if not hover_id:
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    hover_id = self._click_map.get((event.y + dy, event.x + dx))
                    if hover_id: break
                if hover_id: break

        if hover_id != self._hover_node_id:
            self._hover_node_id = hover_id
            self.refresh()

    # --- Rendering Engine ---
    def render(self) -> Text:
        self._click_map.clear()
        
        if not self._graph or not self._graph.nodes:
            return Text("\n\nNo notes linked yet.\nCreate wikilinks [[Like This]].", justify="center", style="dim")

        width = self.content_size.width
        height = self.content_size.height
        if width < 5 or height < 5: return Text("")

        # 1. Community Detection (Auto-Coloring)
        node_colors = {}
        try:
            communities = nx_comm.greedy_modularity_communities(self._graph)
            for i, comm in enumerate(communities):
                color_idx = i % 7
                for node_id in comm:
                    node_colors[node_id] = color_idx
        except: pass

        # 2. Spotlight Calculation (Which nodes are "Active")
        highlight_set = None
        if self._hover_node_id and self._hover_node_id in self._graph:
            highlight_set = set(self._graph.neighbors(self._hover_node_id))
            highlight_set.add(self._hover_node_id)

        # 3. Projection Math
        degrees = dict(self._graph.degree())
        center_x = (width / 2) + self._pan_x
        center_y = (height / 2) + self._pan_y
        base_scale_x = width / 3
        base_scale_y = height / 3
        
        screen_coords = {}
        
        # Data for Rust
        nodes_rs = []   
        labels_rs = []
        edges_rs = []

        # Iterate stored positions
        for node_id, (x, y) in self._pos.items():
            if node_id not in self._graph: continue

            sx = int(center_x + (x * base_scale_x * self._zoom_level))
            sy = int(center_y + (y * base_scale_y * self._zoom_level))
            screen_coords[node_id] = (sx, sy)
            
            if 0 <= sy < height and 0 <= sx < width:
                self._click_map[(sy, sx)] = node_id
                
                # Determine Symbol
                deg = degrees.get(node_id, 0)
                if deg >= 5: symbol = "⦿"
                elif deg >= 2: symbol = "●"
                else: symbol = "•"
                
                c_idx = node_colors.get(node_id, 0)
                
                # Determine Dimming
                is_dimmed = False
                if highlight_set is not None and node_id not in highlight_set:
                    is_dimmed = True

                nodes_rs.append((sx, sy, symbol, c_idx, is_dimmed))

                title = self._graph.nodes[node_id].get("title", "")
                label_x = sx + 2
                if label_x < width:
                    labels_rs.append((label_x, sy, title, is_dimmed))
                    # Make labels clickable too
                    for i in range(len(title)):
                        if label_x + i < width:
                            self._click_map[(sy, label_x + i)] = node_id

        # Edge preparation
        for u, v in self._graph.edges:
            if u in screen_coords and v in screen_coords:
                is_dimmed = False
                if highlight_set is not None:
                    # Edge is bright ONLY if connecting two highlighted nodes
                    if not (u in highlight_set and v in highlight_set):
                        is_dimmed = True
                edges_rs.append((screen_coords[u], screen_coords[v], is_dimmed))

        # 4. Final Render
        if HAS_RUST_BACKEND:
            try:
                ansi_result = synapxis_rs.render_frame(width, height, edges_rs, nodes_rs, labels_rs)
                return Text.from_ansi(ansi_result)
            except Exception:
                # If Rust fails for any reason, fallback silently to Python
                pass

        # Python Fallback (Slower, but functional Braille)
        return self._render_python_fallback(width, height, edges_rs, nodes_rs, labels_rs)

    def _render_python_fallback(self, width: int, height: int, edges: list, nodes: list, labels: list) -> Text:
        """Slower Python implementation of Braille rendering for servers/no-rust."""
        # 1. Initialize Grids
        mask_grid = [0] * (width * height)
        bright_grid = [False] * (width * height)
        
        # 2. Draw Edges (Braille Bresenham)
        for (x0, y0), (x1, y1), is_dimmed in edges:
            px0, py0 = x0 * 2 + 1, y0 * 4 + 2
            px1, py1 = x1 * 2 + 1, y1 * 4 + 2
            
            dx = abs(px1 - px0)
            dy = -abs(py1 - py0)
            sx = 1 if px0 < px1 else -1
            sy = 1 if py0 < py1 else -1
            err = dx + dy
            
            curr_x, curr_y = px0, py0
            
            while True:
                cx, cy = curr_x // 2, curr_y // 4
                if 0 <= cx < width and 0 <= cy < height:
                    idx = cy * width + cx
                    col, row = curr_x % 2, curr_y % 4
                    
                    # Braille Dot Mapping
                    bit = 0
                    if col == 0:
                        if row == 0: bit = 1
                        elif row == 1: bit = 2
                        elif row == 2: bit = 4
                        elif row == 3: bit = 64
                    else:
                        if row == 0: bit = 8
                        elif row == 1: bit = 16
                        elif row == 2: bit = 32
                        elif row == 3: bit = 128
                    
                    mask_grid[idx] |= bit
                    if not is_dimmed: bright_grid[idx] = True
                
                if curr_x == px1 and curr_y == py1: break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    curr_x += sx
                if e2 <= dx:
                    err += dx
                    curr_y += sy

        # 3. Construct Text
        text_output = Text()
        C_EDGE_DIM = Style(color="grey50", dim=True)
        C_EDGE_BRIGHT = Style(color="white")
        PALETTE_STYLES = [
            Style(color="orange1"), Style(color="cyan1"), Style(color="green1"),
            Style(color="magenta1"), Style(color="yellow1"), Style(color="red1"), Style(color="purple")
        ]

        # Helper to build the buffer
        screen_buf = [(" ", Style())] * (width * height)

        # Fill Braille
        for i, mask in enumerate(mask_grid):
            if mask > 0:
                char = chr(0x2800 + mask)
                style = C_EDGE_BRIGHT if bright_grid[i] else C_EDGE_DIM
                screen_buf[i] = (char, style)

        # Overlay Nodes
        for x, y, symbol, c_idx, is_dimmed in nodes:
            if 0 <= x < width and 0 <= y < height:
                idx = y * width + x
                style = C_EDGE_DIM if is_dimmed else PALETTE_STYLES[c_idx % 7]
                screen_buf[idx] = (symbol[0], style)

        # Overlay Labels
        for x, y, txt, is_dimmed in labels:
            if 0 <= y < height:
                style = C_EDGE_DIM if is_dimmed else C_EDGE_BRIGHT
                for k, char in enumerate(txt):
                    if 0 <= x + k < width:
                        idx = y * width + (x + k)
                        if screen_buf[idx][0] not in "⦿●•":
                            screen_buf[idx] = (char, style)

        # Build Rich Text
        for y in range(height):
            for x in range(width):
                char, style = screen_buf[y * width + x]
                text_output.append(char, style=style)
            text_output.append("\n")
            
        return text_output


class GraphViewScreen(Screen):
    """Container for the InteractiveGraph."""
    
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
        Binding("alt+n", "switch_to_notes", "Notes"),
        Binding("+", "zoom_in", "Zoom In"),
        Binding("-", "zoom_out", "Zoom Out"),
        Binding("0", "zoom_reset", "Reset"),
        Binding("f", "toggle_search", "Find Node"),
        # Pan bindings
        Binding("up", "pan_up", "Up", show=False),
        Binding("down", "pan_down", "Down", show=False),
        Binding("left", "pan_left", "Left", show=False),
        Binding("right", "pan_right", "Right", show=False),
        Binding("w", "pan_up", "Up", show=False),
        Binding("s", "pan_down", "Down", show=False),
        Binding("a", "pan_left", "Left", show=False),
        Binding("d", "pan_right", "Right", show=False),
    ]

    CSS = """
    GraphViewScreen { 
        background: $surface; 
        layers: base overlay; /* Defines layer order for search bar */
    }
    
    #graph-header { dock: top; height: 3; background: $surface-darken-2; content-align: center middle; color: $accent; text-style: bold; }
    #graph-display { height: 1fr; border: none; background: $surface; padding: 0; }
    #graph-info { dock: bottom; height: 3; background: black; color: $text-muted; content-align: center middle; }
    
    /* Search Bar Styling - Now on 'overlay' layer to be visible */
    #search-container {
        layer: overlay;
        dock: top;
        width: 100%;
        height: auto;
        align: center top;
        margin-top: 4; /* Moves it BELOW the header */
        display: none;
    }
    
    #search-container.-visible { display: block; }
    
    #graph-search { 
        width: 40; 
        height: 3; 
        background: $surface; 
        color: $text;
        border: tall orange; 
    }
    """

    def __init__(self, store: NoteStore):
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        yield Static("GRAPH VIEW", id="graph-header")
        yield InteractiveGraph(id="graph-display")
        yield Static("", id="graph-info")
        
        # Search container uses 'overlay' layer to sit on top of everything
        # Placed last to ensure precedence
        with Container(id="search-container"):
            yield Input(placeholder="Search node... (ESC to close)", id="graph-search")

    def on_mount(self) -> None: 
        self._refresh_graph()
        # Explicitly focus the graph widget so arrow keys work immediately
        self.query_one(InteractiveGraph).focus()

    def on_screen_resume(self, event: ScreenResume) -> None: self._refresh_graph()
    def on_resize(self, event) -> None: self.query_one("#graph-display", InteractiveGraph).refresh()

    def on_interactive_graph_node_selected(self, message: InteractiveGraph.NodeSelected) -> None:
        notes_screen = self.app.get_screen("notes")
        if isinstance(notes_screen, NoteViewScreen):
            notes_screen.select_note(message.node_id)
        self.app.switch_screen("notes")
        self.notify("Opened note")

    def on_interactive_graph_layout_updated(self, message: InteractiveGraph.LayoutUpdated) -> None:
        """Save layout when user stops dragging."""
        graph_widget = self.query_one(InteractiveGraph)
        new_layout = graph_widget.get_layout()
        self.store.update_layout(new_layout)

    # --- Search Logic ---
    def action_toggle_search(self) -> None:
        search_container = self.query_one("#search-container")
        graph = self.query_one(InteractiveGraph)
        
        if search_container.has_class("-visible"):
            search_container.remove_class("-visible")
            graph.focus() # Return focus to graph
        else:
            search_container.add_class("-visible")
            self.query_one("#graph-search").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "graph-search":
            query = event.value
            target = self.store.find_by_title(query)
            graph = self.query_one(InteractiveGraph)
            search_container = self.query_one("#search-container")
            
            if target:
                graph.center_on_node(target.id)
                self.notify(f"Found: {target.title}")
                search_container.remove_class("-visible")
                event.input.value = ""
                graph.focus() # Return focus to graph
            else:
                self.notify(f"Node '{query}' not found", severity="error")
    
    # Handle Escape key specifically to close search first
    def action_back(self) -> None:
        search_container = self.query_one("#search-container")
        if search_container.has_class("-visible"):
            search_container.remove_class("-visible")
            self.query_one(InteractiveGraph).focus()
        else:
            self.app.pop_screen() # Default back behavior

    def action_switch_to_notes(self) -> None: self.app.switch_screen("notes")
    def action_zoom_in(self) -> None: self.query_one(InteractiveGraph).zoom_in()
    def action_zoom_out(self) -> None: self.query_one(InteractiveGraph).zoom_out()
    def action_zoom_reset(self) -> None: self.query_one(InteractiveGraph).zoom_reset()
    def action_pan_up(self) -> None: self.query_one(InteractiveGraph).pan(0, 2)
    def action_pan_down(self) -> None: self.query_one(InteractiveGraph).pan(0, -2)
    def action_pan_left(self) -> None: self.query_one(InteractiveGraph).pan(4, 0)
    def action_pan_right(self) -> None: self.query_one(InteractiveGraph).pan(-4, 0)

    def _refresh_graph(self) -> None:
        # Pass both graph AND saved layout to the widget
        self.query_one("#graph-display", InteractiveGraph).set_graph(
            self.store.graph(), 
            self.store.layout
        )
        t, l = len(self.store.notes), len(self.store.links)
        self.query_one("#graph-info", Static).update(f"Nodes: {t} • Links: {l}   (Alt+N: Notes • Click node to Open • F: Search • Drag node to Move • ↑↓←→ to Pan • + - or Wheel to Zoom)")


# ---------------------------------------------------------
# App Lifecycle
# ---------------------------------------------------------

class SynapxisCLI(App):
    """Entry point for the application."""

    CSS = """
    Screen { background: $surface; }
    
    /* Override Toast Colors to Orange/Dark Grey */
    Toast {
        background: $surface-darken-1;
        color: $text;
        border-left: wide orange; 
    }
    ToastTitle {
        color: orange;
        text-style: bold;
    }
    
    ScrollBarThumb { background: orange; }
    ScrollBarThumb:hover { background: #ffb700; }
    
    /* Ensure the search bar is on top of everything */
    Center { layer: top_layer; }
    """

    def __init__(self, store: NoteStore, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())
        self.install_screen(NoteViewScreen(self.store), "notes")
        self.install_screen(GraphViewScreen(self.store), "graph")


def main() -> None:
    data_path = Path.home() / ".synapxis_cli" / "notes.json"
    store = NoteStore(data_path)
    app = SynapxisCLI(store)
    app.run()


if __name__ == "__main__":
    main()

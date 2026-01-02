import re
import subprocess
from pathlib import Path
from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Static, Label, ListView, ListItem, Input, TextArea, Select
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding
from textual import events

from synapxis.backend.store import NoteStore
from synapxis.backend.graph import GraphManager
from synapxis.ui.widgets.graph_widget import GraphWidget
from synapxis.utils.parsing import extract_tags

try:
    from textual_image.widget import Image
    HAS_IMAGE_LIB = True
except ImportError:
    HAS_IMAGE_LIB = False

# --- HELPER: EXPORT MODAL ---
class ExportModal(ModalScreen[str]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
    ]

    CSS = """
    ExportModal { align: center middle; background: rgba(0,0,0,0.6); }
    #export-box {
        width: 40;
        height: auto;
        background: #1f2335;
        border: tall orange;
        padding: 0 1;
    }
    .header {
        width: 100%;
        color: orange;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
        border-bottom: solid #16161e;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
        background: #16161e;
        color: #c0caf5;
        border: none;
        text-align: center;
    }
    Button:focus, Button:hover {
        background: orange;
        color: black;
        text-style: bold;
    }
    """

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


# --- HELPER: AUTOCOMPLETE POPUP ---

class SuggestionListItem(ListItem):
    """
    Custom ListItem to store the note title safely and handle layout.
    """
    def __init__(self, title: str) -> None:
        self.note_title = title
        # Label is strictly for display; ListItem handles the layout/events
        super().__init__(Label(title))

class SuggestionModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    SuggestionModal { align: center middle; background: rgba(0,0,0,0.4); }

    #box {
        width: 45;
        height: auto;
        max-height: 22;
        background: #1f2335;
        border: none;
        padding: 0;
    }

    .header {
        width: 100%;
        background: orange;
        color: #1a1b26;
        text-style: bold;
        text-align: center;
    }

    #modal-search {
        height: 1;
        min-height: 1;
        border: none;
        background: #16161e;
        color: orange;
        padding: 0;
        margin: 0;
        text-align: center;
        border-bottom: solid #1f2335;
    }
    #modal-search:focus { border: none; }

    ListView {
        height: auto;
        max-height: 15;
        border: none;
        background: #1f2335;
    }


    SuggestionListItem {
        padding: 1 2;
        background: transparent;
        height: auto;
    }

    SuggestionListItem:hover {
        background: #24283b;
    }


    SuggestionListItem Label {
    width: auto;
    padding: 0;
    background: transparent;
    color: #565f89;
    content-align: left middle;

    }

    SuggestionListItem:hover Label,
    SuggestionListItem.-highlight Label {
        color: orange;
        text-style: bold;
    }
    """

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


# --- SCREEN: SETTINGS ---
class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]

    CSS = """
    SettingsScreen { align: center middle; background: rgba(26, 27, 38, 0.8); }
    #settings-window { width: 50; height: auto; max-height: 80%; background: #1f2335; border: tall orange; padding: 0 1; }
    #settings-header { width: 100%; text-align: center; color: orange; text-style: bold; padding: 1 0; border-bottom: solid #16161e; }
    #tags-scroll { height: auto; max-height: 1fr; overflow-y: auto; padding-top: 1; scrollbar-gutter: stable; }
    .tag-row { height: 3; width: 100%; align: center middle; margin-bottom: 1; }
    .tag-label { width: 1fr; color: #c0caf5; text-style: bold; content-align: left middle; }
    Select { width: 20; height: auto; }
    SelectCurrent { border: none; background: #16161e; color: orange; }
    SelectOverlay { background: #1f2335; border: tall orange; }
    #no-tags { width: 100%; text-align: center; color: #565f89; margin: 2 0; text-style: italic; }
    #settings-footer { width: 100%; text-align: center; color: #565f89; padding: 1 0; text-style: italic; border-top: solid #16161e; }
    """

    COLORS = [("Orange", 0), ("Blue", 1), ("Green", 2), ("Pink", 3), ("Yellow", 4), ("Red", 5), ("Purple", 6)]

    def __init__(self, store: NoteStore):
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-window"):
            yield Label("GRAPH SETTINGS", id="settings-header")
            with Vertical(id="tags-scroll"):
                all_tags = set()
                for note in self.store.notes.values():
                    for tag in note.tags:
                        all_tags.add(tag)
                if not all_tags:
                    yield Label("No #tags found in notes.", id="no-tags")
                else:
                    for tag in sorted(list(all_tags)):
                        current_val = self.store.tag_colors.get(tag, 0)
                        with Horizontal(classes="tag-row"):
                            yield Label(f"#{tag}", classes="tag-label")
                            yield Select(options=self.COLORS, value=current_val, allow_blank=False, id=f"sel-{tag}")
            yield Label("Esc: Back • Select to Change Color", id="settings-footer")

    def on_select_changed(self, event: Select.Changed):
        if event.select.id and event.select.id.startswith("sel-"):
            tag = event.select.id[4:]
            self.store.tag_colors[tag] = event.value
            self.run_worker(self.store.save_tag_colors(self.store.tag_colors))

    def action_back(self):
        self.app.pop_screen()


# --- SCREEN 1: MAIN MENU ---
class MainMenuScreen(Screen):
    BINDINGS = [
        Binding("n", "switch_notes", "Notes"),
        Binding("g", "switch_graph", "Graph"),
        Binding("s", "switch_settings", "Settings"),
        Binding("q", "quit", "Quit"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
    ]
    CSS = """
    MainMenuScreen { align: center middle; background: #1a1b26; overflow: hidden; }
    #menu-container { width: 100%; height: 100%; align: center middle; }
    #logo-container { width: 100%; height: auto; align: center middle; margin-bottom: 0; }
    #logo-image { height: 12; width: 30; }
    #logo-ascii { width: 100%; text-align: center; color: orange; }
    .menu-title { width: 100%; text-align: center; color: #565f89; text-style: bold; margin: 1 0; }
    #menu-buttons { width: 100%; height: auto; align: center middle; }
    #menu-buttons Button { width: 30; height: 3; margin: 0; background: transparent; color: #c0caf5; border: none; text-align: center; }
    #menu-buttons Button:focus, #menu-buttons Button:hover { background: transparent; color: orange; text-style: bold; }
    .nav-help { dock: bottom; width: 100%; text-align: center; color: #565f89; padding-bottom: 1; text-style: italic; }
    """
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            img_paths = [Path("synapxis.png"), Path("assets/synapxis.png"), Path("synapxis_icon.png"), Path("assets/synapxis_icon.png")]
            found_img = next((p for p in img_paths if p.exists()), None)
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
                yield Button("Quit (Q)", id="btn-quit")
            yield Static("Use Tab, ↑↓, or Mouse to navigate • Enter to Select", classes="nav-help")
    def on_mount(self): self.query_one("#btn-notes").focus()
    def action_switch_notes(self): self.app.switch_screen("notes")
    def action_switch_graph(self): self.app.switch_screen("graph")
    def action_switch_settings(self): self.app.push_screen(SettingsScreen(self.app.store))
    def action_quit(self): self.app.exit()
    def action_move_up(self): self.focus_previous()
    def action_move_down(self): self.focus_next()
    def on_button_pressed(self, e):
        if e.button.id == "btn-notes": self.action_switch_notes()
        elif e.button.id == "btn-graph": self.action_switch_graph()
        elif e.button.id == "btn-settings": self.action_switch_settings()
        elif e.button.id == "btn-quit": self.action_quit()
    def _get_ascii_logo(self) -> str:
        return """
███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ██╗  ██╗██╗███████╗
██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗╚██╗██╔╝██║██╔════╝
███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝ ╚███╔╝ ██║███████╗
╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝  ██╔██╗ ██║╚════██║
███████║   ██║   ██║ ╚████║██║  ██║██║     ██╔╝ ██╗██║███████║
╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝
"""


# --- SCREEN 2: NOTE VIEW ---
class NoteViewScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("alt+n", "new", "New"),
        Binding("alt+d", "delete", "Delete"),
        Binding("alt+f", "focus_search", "Search"),
        Binding("alt+e", "export", "Export"),
        Binding("alt+enter", "jump_link", "Follow Link"),
        Binding("alt+g", "graph_view", "Graph"),
        Binding("alt+b", "show_backlinks", "Backlinks"),
        Binding("ctrl+a", "select_all", "Select All", show=False),
    ]

    CSS = """
    NoteViewScreen { background: #1a1b26; }

    #main-layout { width: 100%; height: 100%; layout: horizontal; }

    #sidebar { width: 25%; height: 100%; background: #16161e; border-right: solid #24283b; }

    #sidebar-header-container {
        width: 100%; height: auto; padding-top: 1; padding-bottom: 1;
        align: center middle; background: #1f2335;
    }
    #sidebar-icon { height: 3; width: auto; }
    #sidebar-label { color: orange; text-style: bold; }

    #search {
        height: 1; border: none; background: #1f2335; padding: 0; margin: 0;
        text-align: center; color: #c0caf5; border-bottom: solid #16161e;
    }
    #search:focus { border: none; }

    #note-list { height: 1fr; border: none; background: transparent; }
    #note-list ListItem { background: transparent; padding: 1 2; border: none; }

    ListItem, ListItem:hover, ListItem.--highlighted, ListItem.-active, ListItem:focus {
        background: transparent !important;
        border: none !important;
    }

    .note-label { color: #565f89; }

    ListItem.--highlighted .note-label,
    #note-list ListItem.-active .note-label,
    ListItem:hover .note-label {
        color: orange !important;
        text-style: bold;
    }

    #btn-new {
        dock: bottom;
        width: 100%;
        height: 3;
        background: transparent;
        color: #565f89;
        border: none;
        content-align: center middle;
    }
    #btn-new:hover { color: orange; background: transparent; }
    #btn-new:focus { color: orange; background: transparent; border: none; }

    #content-pane { width: 75%; height: 100%; background: #1a1b26; padding: 2 4; align: center middle; }
    #empty-state { content-align: center middle; color: #565f89; text-style: italic; }
    #note-title { dock: top; height: 3; border: none; background: transparent; text-style: bold; text-align: center; color: orange; }
    #note-content { height: 1fr; border: none; background: transparent; padding: 1 0; }
    TextArea .text-area--cursor-line { background: transparent; }
    .hidden { display: none; }

    #custom-footer { dock: bottom; width: 100%; height: 3; content-align: center middle; color: #565f89; background: black; opacity: 0.8; }
    """

    def __init__(self, store: NoteStore, graph_manager: GraphManager):
        super().__init__()
        self.store = store
        self.gm = graph_manager
        self.current_note_id = None
        self._last_len = 0
        self._refreshing = False

    def compose(self) -> ComposeResult:
        with Container(id="main-layout"):
            with Vertical(id="sidebar"):
                img_paths = [Path("synapxis_icon.png"), Path("assets/synapxis_icon.png")]
                found_img = next((p for p in img_paths if p.exists()), None)
                with Vertical(id="sidebar-header-container"):
                    if HAS_IMAGE_LIB and found_img:
                        yield Image(str(found_img), id="sidebar-icon")
                    else:
                        yield Label("SYNAPXIS", id="sidebar-label")
                yield Input(placeholder="⌕", id="search")
                yield ListView(id="note-list")
                yield Button("+ New Page", id="btn-new", variant="default")

            with Vertical(id="content-pane"):
                yield Label("Select a page or Alt+N: New", id="empty-state")
                yield Input(placeholder="PAGE TITLE", id="note-title", classes="hidden")
                yield TextArea(id="note-content", classes="hidden", language="markdown")

        yield Static("Alt+N: New • Alt+D: Delete • Alt+F: Search • Alt+Enter: Link • Alt+B: Backlinks • Alt+E: Export • Alt+G: Graph", id="custom-footer")

    async def on_mount(self): await self.refresh_list()

    async def on_screen_resume(self):
        await self.refresh_list()
        if self.current_note_id:
            self.select_note(self.current_note_id)

    def on_list_view_highlighted(self, event: ListView.Highlighted):
        if not self._refreshing and event.item:
            if hasattr(event.item, 'note_id'):
                self.select_note(event.item.note_id)

    def on_list_view_selected(self, event: ListView.Selected):
        if hasattr(event.item, 'note_id'):
            self.select_note(event.item.note_id)
            self.query_one("#note-content").focus()

    def select_note(self, note_id):
        self.current_note_id = note_id
        if not self.is_mounted: return
        if note_id not in self.store.notes: return

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

        self.query_one("#note-title", Input).value = note.title
        self.query_one("#note-content", TextArea).load_text(note.content)
        self._last_len = len(note.content)

    async def on_input_changed(self, event):
        if event.input.id == "search": await self.refresh_list()
        elif event.input.id == "note-title" and self.current_note_id:
            await self.store.update_note(self.current_note_id, title=event.value)
            self.gm.build(self.store.notes, self.store.layout)
            list_view = self.query_one("#note-list", ListView)
            for item in list_view.children:
                if getattr(item, "note_id", None) == self.current_note_id:
                    item.query_one(Label).update(event.value)

    async def on_text_area_changed(self, event: TextArea.Changed):
        if not self.current_note_id: return

        content = event.text_area.text
        tags = extract_tags(content)
        await self.store.update_note(self.current_note_id, content=content, tags=tags)

        self.gm.build(self.store.notes, self.store.layout)

        text = content
        if len(text) > self._last_len:
            cursor = event.text_area.cursor_location
            line = event.text_area.document.get_line(cursor[0])
            col = cursor[1]
            if col >= 2 and line[col-2:col] == "[[":
                self.show_autocomplete()
        self._last_len = len(text)

    # --- DEFINITIVE FIX FOR AUTOCOMPLETE ---
    def show_autocomplete(self):
        titles = [n.title for n in self.store.notes.values()]
        ta = self.query_one("#note-content", TextArea)

        # Save cursor just in case, though TextArea usually handles it
        saved_cursor = ta.cursor_location

        def callback(selected):
            if selected:
                # Define the insertion logic
                def do_insert():
                    ta.focus()
                    ta.cursor_location = saved_cursor
                    ta.insert(f"{selected}]]")

                # IMPORTANT: Schedule this to run AFTER the modal close refresh cycle
                self.app.call_after_refresh(do_insert)

        self.app.push_screen(SuggestionModal(titles), callback)

    def action_jump_link(self):
        ta = self.query_one("#note-content", TextArea)
        cursor = ta.cursor_location
        line = ta.document.get_line(cursor[0])
        col = cursor[1]
        matches = list(re.finditer(r"\[\[(.*?)\]\]", line))
        for m in matches:
            if m.start() <= col <= m.end():
                target = m.group(1)
                note = self.store.get_note_by_title(target)
                if note: self.select_note(note.id)
                else: self.notify(f"Note '{target}' not found!", severity="warning")
                return

    def action_show_backlinks(self):
        if not self.current_note_id: return
        self.gm.build(self.store.notes, self.store.layout)
        links = self.gm.get_backlinks(self.current_note_id)
        if not links:
            self.notify("No backlinks found.", severity="information")
            return
        def on_select(selected_title):
            if selected_title:
                note = self.store.get_note_by_title(selected_title)
                if note: self.select_note(note.id)
        self.app.push_screen(SuggestionModal(links), on_select)

    def action_export(self):
        if not self.current_note_id: return
        self.app.push_screen(ExportModal(), self.handle_export)

    def handle_export(self, format_type: str | None):
        if not format_type: return

        note = self.store.notes[self.current_note_id]
        clean_title = "".join(x for x in note.title if x.isalnum() or x in " _-")

        export_dir = Path.home() / "Documents"
        export_dir.mkdir(exist_ok=True)

        try:
            if format_type == "md":
                path = export_dir / f"{clean_title}.md"
                path.write_text(note.content, encoding="utf-8")
                self.notify(f"Exported to {path}")

            elif format_type == "html":
                path = export_dir / f"{clean_title}.html"
                subprocess.run(
                    ["pandoc", "-f", "markdown", "-t", "html", "-o", str(path)],
                    input=note.content.encode("utf-8"),
                    check=True
                )
                self.notify(f"Exported to {path}")

            elif format_type == "pdf":
                path = export_dir / f"{clean_title}.pdf"
                subprocess.run(
                    ["pandoc", "-f", "markdown", "--pdf-engine=weasyprint", "-o", str(path)],
                    input=note.content.encode("utf-8"),
                    check=True
                )
                self.notify(f"Exported to {path}")

        except FileNotFoundError:
            self.notify("Pandoc or PDF engine not found!", severity="error")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    async def refresh_list(self):
        self._refreshing = True
        lv = self.query_one("#note-list", ListView)
        lv.clear()
        search = self.query_one("#search", Input).value.lower().replace("⌕", "").replace("search...", "").strip()
        sorted_notes = sorted(self.store.notes.values(), key=lambda n: n.title.lower())

        for n in sorted_notes:
            if search in n.title.lower():
                item = ListItem(Label(n.title, classes="note-label"))
                item.note_id = n.id
                if n.id == self.current_note_id:
                    item.add_class("-active")
                lv.append(item)

        self._refreshing = False

    async def action_new(self):
        note = await self.store.create_note("Untitled")
        await self.refresh_list()
        self.select_note(note.id)
        self.query_one("#note-title").focus()

    async def action_delete(self):
        if self.current_note_id:
            await self.store.delete_note(self.current_note_id)
            self.current_note_id = None
            self.query_one("#content-pane").styles.align = ("center", "middle")
            self.query_one("#empty-state").remove_class("hidden")
            self.query_one("#note-title").add_class("hidden")
            self.query_one("#note-content").add_class("hidden")
            await self.refresh_list()

    def action_select_all(self):
        if self.current_note_id:
            self.query_one("#note-content", TextArea).select_all()

    def action_back(self): self.app.switch_screen("main")
    def action_focus_search(self): self.query_one("#search").focus()
    def action_graph_view(self): self.app.switch_screen("graph")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new": self.run_worker(self.action_new())


# --- SCREEN 3: GRAPH VIEW ---
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
    CSS = """
    GraphViewScreen { background: #1a1b26; layers: base overlay; }

    #graph-header {
        dock: top;
        width: 100%;
        height: 4;
        padding: 1;
        align: center middle;
        background: #1f2335;
    }
    #header-logo { height: 2; width: auto; }
    #header-label { color: orange; text-style: bold; }

    #search-container {
        layer: overlay;
        dock: top;
        width: 100%;
        height: auto;
        align: center top;
        margin-top: 4;
        display: none;
    }
    #search-container.-visible { display: block; }

    #graph-search {
        width: 40;
        height: 1;
        min-height: 1;
        border: none;
        background: #1f2335;
        color: #c0caf5;
        padding: 0;
        margin: 0;
        text-align: center;
    }

    #graph-info {
        dock: bottom;
        height: 3;
        background: black;
        color: #565f89;
        content-align: center middle;
    }
    """
    def __init__(self, store: NoteStore, graph_manager: GraphManager):
        super().__init__()
        self.store = store
        self.gm = graph_manager

    def compose(self) -> ComposeResult:
        with Vertical(id="graph-header"):
            img_paths = [Path("synapxis_icon.png"), Path("assets/synapxis_icon.png")]
            found_img = next((p for p in img_paths if p.exists()), None)
            if HAS_IMAGE_LIB and found_img:
                yield Image(str(found_img), id="header-logo")
            else:
                yield Label("SYNAPXIS", id="header-label")

        yield GraphWidget(self.gm, self.store)
        yield Static("", id="graph-info")

        with Container(id="search-container"):
            yield Input(placeholder="⌕", id="graph-search")

    def on_mount(self):
        self.gm.build(self.store.notes, self.store.layout)
        self.update_stats()
        self.query_one(GraphWidget).focus()

    def on_screen_resume(self):
        self.gm.build(self.store.notes, self.store.layout)
        self.query_one(GraphWidget).refresh()
        self.update_stats()

    def update_stats(self):
        nodes = len(self.store.notes)
        links = 0
        if self.gm._graph:
            links = self.gm._graph.number_of_edges()
        text = f"Nodes: {nodes} • Links: {links}   (Alt+N: Notes • Click node to Open • F: Search • Drag node to Move • ↑↓←→ to Pan • + - or Wheel to Zoom)"
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
            target = self.store.get_note_by_title(event.value.replace("⌕", "").strip())
            if target:
                self.query_one(GraphWidget).center_on_node(target.id)
                self.query_one("#search-container").remove_class("-visible")
                self.query_one(GraphWidget).focus()
                self.notify(f"Found: {target.title}")
            else:
                self.notify("Node not found", severity="error")

    def on_graph_widget_selected(self, message):
        notes_screen = self.app.get_screen("notes")
        if isinstance(notes_screen, NoteViewScreen):
            notes_screen.select_note(message.node_id)
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

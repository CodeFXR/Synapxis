from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, Select

from synapxis.backend.store import NoteStore
from synapxis.utils.parsing import escape_markup, tag_widget_id


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back")]


    COLORS = [("Orange", 0), ("Blue", 1), ("Green", 2), ("Pink", 3), ("Yellow", 4), ("Red", 5), ("Purple", 6)]

    def __init__(self, store: NoteStore):
        super().__init__()
        self.store = store
        self._tag_id_to_name: dict[str, str] = {}

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
                        safe_id = tag_widget_id(tag)
                        self._tag_id_to_name[safe_id] = tag
                        with Horizontal(classes="tag-row"):
                            yield Label(f"#{escape_markup(tag)}", classes="tag-label")
                            yield Select(options=self.COLORS, value=current_val, allow_blank=False, id=safe_id)
            yield Label("Esc: Back • Select to Change Color", id="settings-footer")

    def on_select_changed(self, event: Select.Changed):
        if not event.select.id:
            return
        tag = self._tag_id_to_name.get(event.select.id)
        if tag is None:
            return
        try:
            color_index = int(event.select.value)
        except (TypeError, ValueError):
            return
        self.store.tag_colors[tag] = color_index
        self.run_worker(self.store.save_tag_colors(self.store.tag_colors))

    def action_back(self):
        self.app.pop_screen()

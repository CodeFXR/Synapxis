from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

import synapxis
from synapxis.backend.graph import GraphManager
from synapxis.utils.parsing import display_width

MIN_ZOOM = 0.2
MAX_ZOOM = 5.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class GraphWidget(Widget):
    can_focus = True

    class Selected(Message):
        def __init__(self, node_id: str):
            self.node_id = node_id
            super().__init__()

    class LayoutUpdated(Message):
        pass

    def __init__(self, graph_manager: GraphManager, store, **kwargs):
        super().__init__(**kwargs)
        self.gm = graph_manager
        self.store = store

        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        self.hover_id = None
        self.drag_id = None
        self.is_dragging = False
        self.last_mouse_pos = (0, 0)
        self.click_start_pos = (0, 0)

    def render(self) -> Text:
        w, h = self.content_size
        if w < 2 or h < 2:
            return Text("")

        edges, nodes, labels = self.gm.get_render_data(
            w, h, self.pan_x, self.pan_y, self.zoom, self.hover_id,
            tag_colors=self.store.tag_colors,
        )

        if not nodes:
            return Text(
                "\n\nNo notes linked yet.\nCreate wikilinks [[Like This]].",
                justify="center",
                style="dim",
            )

        try:
            ansi_string = synapxis.render_frame(w, h, edges, nodes, labels)
            return Text.from_ansi(ansi_string)
        except Exception as e:
            return Text(f"Render Error: {e}", style="red")

    def _scales(self) -> tuple[float, float]:
        w, h = self.content_size
        scale_x = max(0.001, (w / 3) * self.zoom)
        scale_y = max(0.001, (h / 3) * self.zoom)
        return scale_x, scale_y

    def project_to_screen(self, world_x: float, world_y: float) -> tuple[int, int]:
        w, h = self.content_size
        center_x = (w / 2) + self.pan_x
        center_y = (h / 2) + self.pan_y
        scale_x, scale_y = self._scales()
        return int(center_x + (world_x * scale_x)), int(center_y + (world_y * scale_y))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.is_dragging and self.drag_id:
            dx = event.x - self.last_mouse_pos[0]
            dy = event.y - self.last_mouse_pos[1]
            self.last_mouse_pos = (event.x, event.y)

            if self.drag_id == "CAMERA":
                self.pan_x += dx
                self.pan_y += dy
                self.refresh()
                return

            scale_x, scale_y = self._scales()
            world_dx = dx / scale_x
            world_dy = dy / scale_y
            self.gm.update_node_position(self.drag_id, world_dx, world_dy)
            self.refresh()
            return

        w, h = self.content_size

        found = None
        layout = self.gm.get_layout_data()

        for nid, (nx, ny) in layout.items():
            sx, sy = self.project_to_screen(nx, ny)

            if 0 <= sx < w and 0 <= sy < h and abs(event.x - sx) < 3 and abs(event.y - sy) < 2:
                found = nid
                break

            title = self.gm.note_title(nid)
            if title:
                label_cells = display_width(title)
                if event.y == sy and (sx + 2 <= event.x <= sx + 2 + label_cells):
                    found = nid
                    break

        if found != self.hover_id:
            self.hover_id = found
            self.refresh()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.focus()
        if self.hover_id:
            self.drag_id = self.hover_id
        else:
            self.drag_id = "CAMERA"

        self.is_dragging = True
        self.last_mouse_pos = (event.x, event.y)
        self.click_start_pos = (event.x, event.y)
        self.capture_mouse()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.release_mouse()
        dist = abs(event.x - self.click_start_pos[0]) + abs(event.y - self.click_start_pos[1])

        if dist < 2 and self.hover_id and self.drag_id == self.hover_id:
            self.post_message(self.Selected(self.hover_id))
        elif self.drag_id and self.drag_id != "CAMERA":
            self.post_message(self.LayoutUpdated())

        self.drag_id = None
        self.is_dragging = False

    def on_mouse_scroll_up(self, event) -> None:
        self.action_zoom(1.1)

    def on_mouse_scroll_down(self, event) -> None:
        self.action_zoom(0.9)

    def action_pan(self, x, y) -> None:
        self.pan_x += x * (1 / self.zoom)
        self.pan_y += y * (1 / self.zoom)
        self.refresh()

    def action_zoom(self, amount: float) -> None:
        next_zoom = _clamp(self.zoom * amount, MIN_ZOOM, MAX_ZOOM)
        if next_zoom == self.zoom:
            return
        self.zoom = next_zoom
        self.refresh()

    def center_on_node(self, node_id: str) -> None:
        layout = self.gm.get_layout_data()
        if node_id not in layout:
            return
        nx, ny = layout[node_id]
        w, h = self.content_size
        scale_x = max(1.0, w / 3)
        scale_y = max(1.0, h / 3)
        self.pan_x = -(nx * scale_x)
        self.pan_y = -(ny * scale_y)
        self.zoom = 1.0
        self.hover_id = node_id
        self.refresh()

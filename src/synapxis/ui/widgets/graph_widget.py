from textual.widget import Widget
from rich.text import Text
from textual import events
from textual.message import Message

import synapxis
from synapxis.backend.graph import GraphManager
# Type hinting only
if False:
    from synapxis.backend.store import NoteStore

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
        self.store = store # We need the store to access tag_colors
        
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
        if w < 2 or h < 2: return Text("")

        # Pass the tag_colors from the store to the math layer
        edges, nodes, labels = self.gm.get_render_data(
            w, h, self.pan_x, self.pan_y, self.zoom, self.hover_id,
            tag_colors=self.store.tag_colors
        )
        
        if not nodes:
             return Text("\n\nNo notes linked yet.\nCreate wikilinks [[Like This]].", justify="center", style="dim")

        try:
            ansi_string = synapxis.render_frame(w, h, edges, nodes, labels)
            return Text.from_ansi(ansi_string)
        except Exception as e:
            return Text(f"Render Error: {e}", style="red")

    # --- Interaction Logic ---
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

            w, h = self.content_size
            scale_x = (w / 3) * self.zoom
            scale_y = (h / 3) * self.zoom
            
            if scale_x > 0:
                world_dx = dx / scale_x
                world_dy = dy / scale_y
                self.gm.update_node_position(self.drag_id, world_dx, world_dy)
                self.refresh()
            return

        # Hit Test
        w, h = self.content_size
        center_x = (w / 2) + self.pan_x
        center_y = (h / 2) + self.pan_y
        scale_x = (w / 3) * self.zoom
        scale_y = (h / 3) * self.zoom
        
        found = None
        layout = self.gm.get_layout_data()
        
        for nid, (nx, ny) in layout.items():
            sx = int(center_x + (nx * scale_x))
            sy = int(center_y + (ny * scale_y))
            
            if abs(event.x - sx) < 3 and abs(event.y - sy) < 2:
                found = nid
                break
            
            if self.gm._graph.has_node(nid):
                title = self.gm._graph.nodes[nid].get("title", "")
                label_len = len(title)
                if event.y == sy and (sx + 2 <= event.x <= sx + 2 + label_len):
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

    def on_mouse_scroll_up(self, event): self.action_zoom(1.1)
    def on_mouse_scroll_down(self, event): self.action_zoom(0.9)
    def action_pan(self, x, y): 
        self.pan_x += x * (1/self.zoom)
        self.pan_y += y * (1/self.zoom)
        self.refresh()
    def action_zoom(self, amount): 
        self.zoom *= amount
        self.refresh()
        
    def center_on_node(self, node_id: str):
        layout = self.gm.get_layout_data()
        if node_id in layout:
            nx, ny = layout[node_id]
            w, h = self.content_size
            scale_x = w / 3
            scale_y = h / 3
            self.pan_x = -(nx * scale_x)
            self.pan_y = -(ny * scale_y)
            self.zoom = 1.0
            self.hover_id = node_id
            self.refresh()

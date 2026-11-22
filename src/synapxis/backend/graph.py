import asyncio
import math
from collections.abc import Mapping

import networkx as nx

from ..utils.parsing import display_slice, normalize_title, parse_wikilinks
from .models import Note

Position = tuple[float, float]


class GraphManager:
    """
    Manages the NetworkX graph topology and memoized layout positions.

    Three layers:
    - Mutation: ``update_note`` / ``remove_note`` adjust a single node + its incident edges.
    - Layout:   ``relayout`` / ``build`` re-run physics only when needed.
    - Render:   ``get_render_data`` is read-only and called from the widget.
    """

    def __init__(self):
        self._graph = nx.DiGraph()
        self._positions: dict[str, Position] = {}
        self._title_index: dict[str, str] = {}
        self._pending_layout: set[str] = set()
        self._generation = 0

    @property
    def nodes(self):
        return self._graph.nodes

    @property
    def edges(self):
        return self._graph.edges

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    def has_node(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def note_title(self, node_id: str) -> str:
        if not self._graph.has_node(node_id):
            return ""
        return self._graph.nodes[node_id].get("title", "")

    def note_tags(self, node_id: str) -> list[str]:
        if not self._graph.has_node(node_id):
            return []
        return list(self._graph.nodes[node_id].get("tags", []))

    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def incoming_edges(self, node_id: str) -> list[str]:
        return [src for src in self._graph.predecessors(node_id)]

    def position(self, node_id: str) -> Position | None:
        return self._positions.get(node_id)

    def build(
        self,
        notes: dict[str, Note],
        saved_layout: Mapping[str, list[float]] | None = None,
    ) -> None:
        self._graph.clear()
        self._title_index = {}

        for nid, note in notes.items():
            self._graph.add_node(nid, title=note.title, tags=list(note.tags))
            key = normalize_title(note.title)
            if key:
                self._title_index[key] = nid

        for nid, note in notes.items():
            for link in parse_wikilinks(note.content):
                target_key = normalize_title(link.target)
                target_id = self._title_index.get(target_key)
                if target_id and target_id != nid:
                    self._graph.add_edge(nid, target_id)

        self._pending_layout = set(self._graph.nodes)
        self._generation += 1
        self._update_layout(dict(saved_layout) if saved_layout else None)

    def sync_notes(self, notes: Mapping[str, Note], relayout: bool = True) -> None:
        active_ids = set(notes)
        for node_id in set(self._graph.nodes) - active_ids:
            self._graph.remove_node(node_id)
            self._positions.pop(node_id, None)
            self._pending_layout.discard(node_id)

        self._title_index = {}
        for node_id, note in notes.items():
            if node_id not in self._graph:
                self._graph.add_node(node_id)
                self._pending_layout.add(node_id)
            self._graph.nodes[node_id].update(title=note.title, tags=list(note.tags))
            key = normalize_title(note.title)
            if key:
                self._title_index[key] = node_id

        self._graph.remove_edges_from(list(self._graph.edges))
        for node_id, note in notes.items():
            for target_id in self._outgoing_targets(note):
                if target_id != node_id:
                    self._graph.add_edge(node_id, target_id)

        self._generation += 1
        if relayout:
            self._update_layout(None)

    def add_or_update_note(self, note: Note) -> None:
        if self._graph.has_node(note.id):
            self._graph.nodes[note.id]["title"] = note.title
            self._graph.nodes[note.id]["tags"] = list(note.tags)
        else:
            self._graph.add_node(note.id, title=note.title, tags=list(note.tags))
            self._pending_layout.add(note.id)
        key = normalize_title(note.title)
        if key:
            self._title_index[key] = note.id

        outgoing_targets = set(self._outgoing_targets(note))
        self._graph.remove_edges_from(
            list(self._graph.out_edges(note.id))
        )
        for target_id in outgoing_targets:
            if target_id and target_id != note.id:
                self._graph.add_edge(note.id, target_id)
        self._pending_layout.discard(note.id)
        self._generation += 1

    def remove_note(self, note_id: str) -> None:
        if self._graph.has_node(note_id):
            self._graph.remove_node(note_id)
        self._positions.pop(note_id, None)
        self._pending_layout.discard(note_id)
        for key, mapped_id in list(self._title_index.items()):
            if mapped_id == note_id:
                del self._title_index[key]
        self._generation += 1

    def _outgoing_targets(self, note: Note) -> set[str]:
        targets: set[str] = set()
        for link in parse_wikilinks(note.content):
            key = normalize_title(link.target)
            mapped = self._title_index.get(key)
            if mapped:
                targets.add(mapped)
        return targets

    def relayout(self) -> None:
        if not self._graph.nodes:
            self._positions = {}
            self._pending_layout.clear()
            return
        self._update_layout(None)

    async def relayout_async(self) -> bool:
        if not self._graph.nodes:
            self._positions = {}
            self._pending_layout.clear()
            return True

        missing = [node for node in self._graph if node not in self._positions]
        if not missing and not self._pending_layout:
            return True

        generation = self._generation
        graph = self._graph.copy()
        positions = dict(self._positions)
        new_positions = await asyncio.to_thread(
            self._calculate_layout, graph, positions
        )
        if generation != self._generation:
            return False
        self._positions = new_positions
        self._pending_layout.clear()
        return True

    async def sync_and_relayout(self, notes: Mapping[str, Note]) -> bool:
        """Sync topology against current notes and run async layout.

        This is the standard mutation path: callers persist a note change,
        then ``sync_and_relayout`` reconciles the graph and recomputes
        positions off the event loop.
        """
        self.sync_notes(notes, relayout=False)
        return await self.relayout_async()

    @staticmethod
    def _calculate_layout(
        graph: nx.DiGraph,
        positions: dict[str, Position],
    ) -> dict[str, Position]:
        """Run NetworkX spring_layout on the graph.

        The cold branch (no prior positions) seeds with a fixed
        integer; the warm branch uses the existing positions as
        fixed anchors so the layout converges. A ``ValueError`` from
        the warm branch falls back to a fresh seed rather than
        failing the save.
        """
        if not positions:
            result = nx.spring_layout(
                graph,
                seed=42,
                k=0.5,
                iterations=50,
                center=(0.0, 0.0),
                scale=1.0,
            )
        else:
            try:
                result = nx.spring_layout(
                    graph,
                    pos=positions,
                    fixed=positions.keys(),
                    k=0.5,
                    iterations=50,
                    center=(0.0, 0.0),
                    scale=1.0,
                )
            except ValueError:
                result = nx.spring_layout(graph, seed=42)
        return {
            node_id: (float(x), float(y))
            for node_id, (x, y) in result.items()
        }

    def _coerce_positions(
        self, raw: Mapping[str, list[float]]
    ) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for nid, pos in raw.items():
            if not isinstance(nid, str) or nid not in self._graph:
                continue
            if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                continue
            try:
                x = float(pos[0])
                y = float(pos[1])
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            out[nid] = (x, y)
        return out

    def _update_layout(
        self, saved_layout: dict[str, list[float]] | None
    ) -> None:
        if not self._graph.nodes:
            self._positions = {}
            self._pending_layout.clear()
            return

        current_pos = self._coerce_positions(saved_layout or {})
        for nid in current_pos:
            self._positions[nid] = current_pos[nid]

        missing_nodes = [n for n in self._graph.nodes if n not in self._positions]
        if not missing_nodes and not self._pending_layout:
            return
        if not missing_nodes:
            return

        self._positions = self._calculate_layout(
            self._graph, dict(self._positions)
        )
        self._pending_layout.clear()

    def get_layout_data(self) -> dict[str, Position]:
        return {nid: (x, y) for nid, (x, y) in self._positions.items()}

    def update_node_position(self, node_id: str, dx: float, dy: float) -> None:
        if node_id not in self._positions:
            return
        x, y = self._positions[node_id]
        self._positions[node_id] = (x + dx, y + dy)

    def get_backlinks(self, node_id: str) -> list[str]:
        if not self._graph.has_node(node_id):
            return []
        titles: list[str] = []
        for predecessor in self._graph.predecessors(node_id):
            data = self._graph.nodes[predecessor]
            titles.append(data.get("title", ""))
        return sorted(title for title in titles if title)

    def get_render_data(
        self,
        width: int,
        height: int,
        pan_x: float,
        pan_y: float,
        zoom: float,
        hover_id: str | None = None,
        tag_colors: dict[str, int] | None = None,
    ):
        if not self._graph.nodes:
            return [], [], []

        center_x = (width / 2) + pan_x
        center_y = (height / 2) + pan_y
        scale_x = (width / 3) * zoom
        scale_y = (height / 3) * zoom

        highlight_set: set[str] | None = None
        if hover_id and self._graph.has_node(hover_id):
            highlight_set = set(self._graph.neighbors(hover_id))
            highlight_set.add(hover_id)
            for predecessor in self._graph.predecessors(hover_id):
                highlight_set.add(predecessor)

        nodes_rs: list[tuple[int, int, str, int, bool]] = []
        labels_rs: list[tuple[int, int, str, bool]] = []
        edges_rs: list[tuple[tuple[int, int], tuple[int, int], bool]] = []
        screen_map: dict[str, tuple[int, int]] = {}

        tag_colors = tag_colors or {}

        for nid, (x, y) in self._positions.items():
            if nid not in self._graph:
                continue

            sx = int(center_x + (x * scale_x))
            sy = int(center_y + (y * scale_y))

            if -50 <= sx <= width + 50 and -50 <= sy <= height + 50:
                screen_map[nid] = (sx, sy)
                deg = self._graph.degree(nid)
                symbol = "⦿" if deg >= 5 else "●" if deg >= 2 else "•"

                c_idx = 0
                node_tags = self._graph.nodes[nid].get("tags", [])
                for tag in node_tags:
                    if tag in tag_colors:
                        c_idx = tag_colors[tag]
                        break

                is_dimmed = highlight_set is not None and nid not in highlight_set
                nodes_rs.append((sx, sy, symbol, c_idx, is_dimmed))

                if zoom > 0.5:
                    title = self._graph.nodes[nid].get("title", "")
                    label = display_slice(title, max(0, width - (sx + 2)))
                    labels_rs.append((sx + 2, sy, label, is_dimmed))

        for u, v in self._graph.edges:
            if u in screen_map and v in screen_map:
                p1 = screen_map[u]
                p2 = screen_map[v]
                is_dimmed = False
                if highlight_set is not None:
                    if not (u in highlight_set and v in highlight_set):
                        is_dimmed = True
                edges_rs.append((p1, p2, is_dimmed))

        return edges_rs, nodes_rs, labels_rs

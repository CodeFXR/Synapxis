import networkx as nx
import re
from typing import Dict, List, Tuple, Set, Optional
from .models import Note

class GraphManager:
    """
    Manages the NetworkX graph structure and layout calculations.
    """
    def __init__(self):
        self._graph = nx.DiGraph()
        self._positions: Dict[str, Tuple[float, float]] = {}
        
    @property
    def nodes(self):
        return self._graph.nodes

    def build(self, notes: Dict[str, Note], saved_layout: Dict[str, List[float]] = None) -> None:
        """Rebuilds the graph topology from the note data."""
        self._graph.clear()
        
        # 1. Add Nodes (Store TAGS in the node attributes now)
        title_map = {}
        for nid, note in notes.items():
            self._graph.add_node(nid, title=note.title, tags=note.tags)
            title_map[note.title.lower().strip()] = nid
            
        # 2. Add Edges
        for nid, note in notes.items():
            matches = re.findall(r"\[\[(.*?)\]\]", note.content)
            for match in matches:
                link_title = match.split("|")[0].strip()
                target_id = title_map.get(link_title.lower())
                if target_id and target_id != nid:
                    self._graph.add_edge(nid, target_id)

        # 3. Update Positions (Physics)
        self._update_layout(saved_layout)

    def _update_layout(self, saved_layout: Optional[Dict[str, List[float]]]) -> None:
        if not self._graph.nodes:
            self._positions = {}
            return

        current_pos = {}
        if saved_layout:
            for nid, pos in saved_layout.items():
                if nid in self._graph:
                    current_pos[nid] = tuple(pos)
        
        missing_nodes = [n for n in self._graph.nodes if n not in current_pos]
        physics_k = 0.5 
        physics_iter = 50

        if not current_pos and missing_nodes:
            self._positions = nx.spring_layout(self._graph, seed=42, k=physics_k, iterations=physics_iter, center=(0,0), scale=1.0)
        elif missing_nodes:
            try:
                new_pos = nx.spring_layout(self._graph, pos=current_pos, fixed=current_pos.keys(), k=physics_k, iterations=physics_iter, center=(0,0), scale=1.0)
                self._positions = new_pos
            except ValueError:
                self._positions = nx.spring_layout(self._graph, seed=42)
        else:
            self._positions = current_pos

    def get_layout_data(self) -> Dict[str, Tuple[float, float]]:
        return self._positions

    def update_node_position(self, node_id: str, dx: float, dy: float):
        if node_id in self._positions:
            ox, oy = self._positions[node_id]
            self._positions[node_id] = (ox + dx, oy + dy)

    def get_backlinks(self, node_id: str) -> List[str]:
        if not self._graph.has_node(node_id):
            return []
        neighbor_ids = list(self._graph.neighbors(node_id))
        titles = []
        for nid in neighbor_ids:
            title = self._graph.nodes[nid].get("title", "Unknown")
            titles.append(title)
        return sorted(titles)

    def get_render_data(self, width: int, height: int, pan_x: float, pan_y: float, zoom: float, hover_id: str = None, tag_colors: Dict[str, int] = None):
        """
        Prepares data for Rust renderer.
        tag_colors: Dict mapping "tag_name" -> color_index (0-6)
        """
        if not self._graph.nodes:
            return [], [], []

        center_x = (width / 2) + pan_x
        center_y = (height / 2) + pan_y
        scale_x = width / 3 * zoom
        scale_y = height / 3 * zoom
        
        highlight_set = None
        if hover_id and hover_id in self._graph:
            highlight_set = set(self._graph.neighbors(hover_id))
            highlight_set.add(hover_id)

        nodes_rs = []
        labels_rs = []
        edges_rs = []
        screen_map = {} 

        # Default is empty map if none provided
        if tag_colors is None: tag_colors = {}

        for nid, (x, y) in self._positions.items():
            if nid not in self._graph: continue
            
            sx = int(center_x + (x * scale_x))
            sy = int(center_y + (y * scale_y))
            
            if -50 <= sx <= width + 50 and -50 <= sy <= height + 50:
                screen_map[nid] = (sx, sy)
                deg = self._graph.degree[nid]
                symbol = "⦿" if deg >= 5 else "●" if deg >= 2 else "•"
                
                # COLOR LOGIC: Default 0 (Orange)
                c_idx = 0 
                # Check tags for overrides
                node_tags = self._graph.nodes[nid].get("tags", [])
                for tag in node_tags:
                    if tag in tag_colors:
                        c_idx = tag_colors[tag]
                        break # Priority: First matching tag wins
                
                is_dimmed = (highlight_set is not None) and (nid not in highlight_set)
                
                nodes_rs.append((sx, sy, symbol, c_idx, is_dimmed))
                
                if zoom > 0.5:
                    title = self._graph.nodes[nid].get("title", "")
                    labels_rs.append((sx + 2, sy, title, is_dimmed))

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

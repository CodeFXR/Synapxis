try:
    # Try to import the Rust engine (if it exists)
    from .synapxis import render_frame
except ImportError:
    # If missing (or shadowing issue), use this Python fallback
    def render_frame(width: int, height: int, edges: list, nodes: list, labels: list) -> str:
        grid = [[" " for _ in range(width)] for _ in range(height)]
        
        for x, y, char, color, dimmed in nodes:
            if 0 <= y < height and 0 <= x < width:
                grid[y][x] = char
        
        for x, y, text, dimmed in labels:
            if 0 <= y < height:
                max_len = min(len(text), width - x)
                for i in range(max_len):
                    grid[y][x + i] = text[i]
                    
        return "\n".join("".join(row) for row in grid)

__all__ = ["render_frame"]

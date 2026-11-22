use pyo3::prelude::*;
use std::char;
use unicode_width::UnicodeWidthChar;

// --- ANSI THEME PALETTE (Static References) ---
type Point = (i32, i32);
type Edge = (Point, Point, bool);
type Node = (i32, i32, String, u8, bool);
type Label = (i32, i32, String, bool);

const C_RESET: &str = "\x1b[0m";
const C_EDGE_DIM: &str = "\x1b[90m"; // Dark Grey
const C_EDGE_BRIGHT: &str = "\x1b[97m"; // White (Focus)

const PALETTE: [&str; 7] = [
    "\x1b[38;5;208m", // 0: Orange
    "\x1b[38;5;45m",  // 1: Cyan/Blue
    "\x1b[38;5;118m", // 2: Bright Green
    "\x1b[38;5;201m", // 3: Hot Pink
    "\x1b[38;5;226m", // 4: Yellow
    "\x1b[38;5;196m", // 5: Red
    "\x1b[38;5;135m", // 6: Purple
];

// Display cell width of a single character. Zero-width characters
// (combining marks, ZWJs) are skipped entirely; otherwise use the
// East Asian Width of the codepoint.
fn cell_width(c: char) -> usize {
    if c.width().unwrap_or(0) == 0 {
        return 0;
    }
    c.width().unwrap_or(1)
}

/// Pure-Rust core of the renderer. The PyO3 wrapper below
/// (`render_frame`) is a thin shim around this. Splitting the
/// implementation lets the Rust integration test exercise the
/// logic without booting a Python interpreter.
pub fn render_frame_core(
    width: usize,
    height: usize,
    edges: &[Edge],
    nodes: &[Node],
    labels: &[Label],
) -> String {
    // Output empty reset if there's no room to draw anything.
    if width == 0 || height == 0 {
        return C_RESET.to_string();
    }

    // 1. Initialize Grids
    let mut mask_grid = vec![0u8; width * height];
    let mut bright_grid = vec![false; width * height];

    // 2. High-Res Line Drawing (Braille). Coordinates are double-
    // pixel; each terminal cell is 2 columns wide and 4 rows tall
    // in braille space.
    for edge in edges {
        let ((x0, y0), (x1, y1), is_dimmed) = *edge;
        let px0 = x0 * 2 + 1;
        let py0 = y0 * 4 + 2;
        let px1 = x1 * 2 + 1;
        let py1 = y1 * 4 + 2;

        let dx = (px1 - px0).abs();
        let dy = -(py1 - py0).abs();
        let sx = if px0 < px1 { 1 } else { -1 };
        let sy = if py0 < py1 { 1 } else { -1 };
        let mut err = dx + dy;
        let mut curr_x = px0;
        let mut curr_y = py0;

        loop {
            let cx = (curr_x / 2) as usize;
            let cy = (curr_y / 4) as usize;

            if cx < width && cy < height {
                let idx = cy * width + cx;
                let col = curr_x % 2;
                let row = curr_y % 4;

                let bit = match (col, row) {
                    (0, 0) => 0x01,
                    (0, 1) => 0x02,
                    (0, 2) => 0x04,
                    (0, 3) => 0x40,
                    (1, 0) => 0x08,
                    (1, 1) => 0x10,
                    (1, 2) => 0x20,
                    (1, 3) => 0x80,
                    _ => 0,
                };

                mask_grid[idx] |= bit;
                if !is_dimmed {
                    bright_grid[idx] = true;
                }
            }

            if curr_x == px1 && curr_y == py1 {
                break;
            }
            let e2 = 2 * err;
            if e2 >= dy {
                err += dy;
                curr_x += sx;
            }
            if e2 <= dx {
                err += dx;
                curr_y += sy;
            }
        }
    }

    // 3. Construct Output Buffer (Using &str to avoid allocations)
    let mut screen_buf: Vec<(char, &str)> = vec![(' ', C_RESET); width * height];

    // A. Fill with Braille
    for i in 0..(width * height) {
        let mask = mask_grid[i];
        if mask > 0 {
            let braille_char = char::from_u32(0x2800 + mask as u32).unwrap_or(' ');
            let color = if bright_grid[i] {
                C_EDGE_BRIGHT
            } else {
                C_EDGE_DIM
            };
            screen_buf[i] = (braille_char, color);
        }
    }

    // B. Overlay Nodes. Node symbols render as a single Unicode
    // codepoint per cell.
    for node in nodes {
        let (x, y, ref symbol, color_idx, is_dimmed) = *node;
        if x >= 0 && x < width as i32 && y >= 0 && y < height as i32 {
            let idx = (y as usize) * width + (x as usize);
            let char_str = symbol.chars().next().unwrap_or('•');

            let c_code = if is_dimmed {
                C_EDGE_DIM
            } else {
                PALETTE.get(color_idx as usize).unwrap_or(&PALETTE[0])
            };

            screen_buf[idx] = (char_str, c_code);
        }
    }

    // C. Overlay Labels. Each label is drawn cell-by-cell using
    // the East Asian Width of every codepoint. Zero-width characters
    // (combining marks, ZWJs) are dropped. Wide characters (CJK,
    // emoji, ...) advance the cursor by their display width rather
    // than by 1, so adjacent wide chars do not visually overlap.
    // The second cell of a wide char is left at its initial value
    // (' '), which is what the terminal expects when a wide glyph
    // is rendered at the leading column.
    for label in labels {
        let (start_x, y, ref text, is_dimmed) = *label;
        let label_color = if is_dimmed { C_EDGE_DIM } else { C_EDGE_BRIGHT };
        let yi = y;
        if yi < 0 || yi >= height as i32 {
            continue;
        }
        let row_offset = (yi as usize) * width;
        let mut cursor = start_x;

        for c in text.chars() {
            let w = cell_width(c);
            if w == 0 {
                // Skip combining marks; treat them as zero-width.
                continue;
            }
            if cursor >= 0 && cursor < width as i32 {
                let pos = cursor as usize;
                let existing = screen_buf[row_offset + pos].0;
                if !"⦿●•".contains(existing) {
                    screen_buf[row_offset + pos] = (c, label_color);
                }
            }
            // Advance cursor by the display cell width of the char
            // even if `cursor` was negative, so wide chars past the
            // left edge still take their full cell budget.
            cursor += w as i32;
            if cursor >= width as i32 {
                break;
            }
        }
    }

    // 4. Serialize
    let mut output = String::with_capacity(width * height * 2);
    let mut current_color = "";

    for y in 0..height {
        let row_start = y * width;
        let row_end = row_start + width;

        for &(char, color) in &screen_buf[row_start..row_end] {
            if color != current_color && char != ' ' {
                output.push_str(color);
                current_color = color;
            } else if char == ' ' && !current_color.is_empty() {
                output.push_str(C_RESET);
                current_color = "";
            }
            output.push(char);
        }
        output.push('\n');
    }
    output.push_str(C_RESET);

    output
}

#[pyfunction]
fn render_frame(
    width: usize,
    height: usize,
    edges: Vec<Edge>,
    nodes: Vec<Node>,
    labels: Vec<Label>,
) -> PyResult<String> {
    Ok(render_frame_core(width, height, &edges, &nodes, &labels))
}

#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[pymodule]
fn synapxis(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(render_frame, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    Ok(())
}

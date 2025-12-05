use pyo3::prelude::*;
use std::char;

// --- ANSI THEME PALETTE (Static References) ---
const C_RESET: &str = "\x1b[0m";
const C_EDGE_DIM: &str = "\x1b[90m";     // Dark Grey
const C_EDGE_BRIGHT: &str = "\x1b[97m";  // White (Focus)

const PALETTE: [&str; 7] = [
    "\x1b[38;5;208m", // 0: Orange
"\x1b[38;5;45m",  // 1: Cyan/Blue
"\x1b[38;5;118m", // 2: Bright Green
"\x1b[38;5;201m", // 3: Hot Pink
"\x1b[38;5;226m", // 4: Yellow
"\x1b[38;5;196m", // 5: Red
"\x1b[38;5;135m", // 6: Purple
];

#[pyfunction]
fn render_frame(
    width: usize,
    height: usize,
    edges: Vec<((i32, i32), (i32, i32), bool)>,
                nodes: Vec<(i32, i32, String, u8, bool)>,
                labels: Vec<(i32, i32, String, bool)>,
) -> String {

    // 1. Initialize Grids
    let mut mask_grid = vec![0u8; width * height];
    let mut bright_grid = vec![false; width * height];

    // 2. High-Res Line Drawing (Braille)
    for ((x0, y0), (x1, y1), is_dimmed) in edges {
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
                    (0, 0) => 0x01, (0, 1) => 0x02, (0, 2) => 0x04, (0, 3) => 0x40,
                    (1, 0) => 0x08, (1, 1) => 0x10, (1, 2) => 0x20, (1, 3) => 0x80,
                    _ => 0
                };

                mask_grid[idx] |= bit;
                if !is_dimmed { bright_grid[idx] = true; }
            }

            if curr_x == px1 && curr_y == py1 { break; }
            let e2 = 2 * err;
            if e2 >= dy { err += dy; curr_x += sx; }
            if e2 <= dx { err += dx; curr_y += sy; }
        }
    }

    // 3. Construct Output Buffer (Using &str to avoid allocations)
    // Default is (' ', C_RESET)
    let mut screen_buf: Vec<(char, &str)> = vec![(' ', C_RESET); width * height];

    // A. Fill with Braille
    for i in 0..(width * height) {
        let mask = mask_grid[i];
        if mask > 0 {
            let braille_char = char::from_u32(0x2800 + mask as u32).unwrap_or(' ');
            let color = if bright_grid[i] { C_EDGE_BRIGHT } else { C_EDGE_DIM };
            screen_buf[i] = (braille_char, color);
        }
    }

    // B. Overlay Nodes
    for (x, y, symbol, color_idx, is_dimmed) in nodes {
        if x >= 0 && x < width as i32 && y >= 0 && y < height as i32 {
            let idx = (y as usize) * width + (x as usize);
            let char_str = symbol.chars().next().unwrap_or('•');

            let c_code = if is_dimmed { C_EDGE_DIM }
            else { PALETTE.get(color_idx as usize).unwrap_or(&PALETTE[0]) };

            screen_buf[idx] = (char_str, c_code);
        }
    }

    // C. Overlay Labels
    for (start_x, y, text, is_dimmed) in labels {
        if y >= 0 && y < height as i32 {
            let label_color = if is_dimmed { C_EDGE_DIM } else { C_EDGE_BRIGHT };

            for (i, c) in text.chars().enumerate() {
                let x = start_x + (i as i32);
                if x >= 0 && x < width as i32 {
                    let idx = (y as usize) * width + (x as usize);
                    // Don't overwrite nodes
                    if !"⦿●•".contains(screen_buf[idx].0) {
                        screen_buf[idx] = (c, label_color);
                    }
                }
            }
        }
    }

    // 4. Serialize
    let mut output = String::with_capacity(width * height * 2);
    let mut current_color = "";

    for y in 0..height {
        let row_start = y * width;
        let row_end = row_start + width;

        for i in row_start..row_end {
            let (char, color) = screen_buf[i];

            if color != current_color && char != ' ' {
                output.push_str(color);
                current_color = color;
            } else if char == ' ' && current_color != "" {
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

#[pymodule]
fn synapxis_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(render_frame, m)?)?;
    Ok(())
}

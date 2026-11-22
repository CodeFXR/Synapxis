//! Integration test for the Synapxis Rust renderer.
//!
//! Exercises the pure-Rust ``render_frame_core`` directly. The
//! PyO3 wrapper (``render_frame``) is a thin shim around it, so a
//! regression in the core is a regression in the wheel.

#[test]
fn render_frame_emits_braille_for_a_line() {
    let edges = [((1, 1), (6, 1), false)];
    let nodes: [(i32, i32, String, u8, bool); 0] = [];
    let labels: [(i32, i32, String, bool); 0] = [];

    let output = synapxis::render_frame_core(8, 3, &edges, &nodes, &labels);

    // The 8x3 frame should contain at least one Braille-pattern
    // codepoint (U+2800..U+28FF) because the edge forces the
    // pixel grid to mark a horizontal line.
    let has_braille = output.chars().any(|c| matches!(c, '\u{2800}'..='\u{28FF}'));
    assert!(
        has_braille,
        "render_frame should emit at least one Braille codepoint, got: {output:?}"
    );
}

#[test]
fn render_frame_empty_grid_returns_reset() {
    let output = synapxis::render_frame_core(0, 0, &[], &[], &[]);
    assert_eq!(output, "\x1b[0m");
}

#[test]
fn render_frame_cjk_label_renders_visible_codepoints() {
    // Place the label at x=1 so the first wide char is fully on
    // screen. The wider 15x3 frame gives the trailing chars room.
    let labels = [(1, 1, "日本語".to_string(), false)];
    let output = synapxis::render_frame_core(15, 3, &[], &[], &labels);
    for c in "日本語".chars() {
        assert!(
            output.contains(c),
            "CJK codepoint {c:?} missing from output: {output:?}"
        );
    }
}

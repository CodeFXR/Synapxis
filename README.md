<div align="center">
  <img src="https://github.com/user-attachments/assets/b7309ed8-cd15-4129-b28f-5354c2ee4e58" alt="synapxis_icon" width="120" />

  <h1>Synapxis</h1>

  <p>
    <strong>The Terminal-Based Zettelkasten for High-Performance Thought.</strong>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Made%20with-Textual-orange?style=flat-square" alt="Textual" />
    <img src="https://img.shields.io/badge/Backend-Rust-black?style=flat-square&logo=rust" alt="Rust" />
    <img src="https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python" alt="Python" />
    <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License" />
  </p>

  <p>
    <a href="https://codefxr.com/docs/synapxis"><strong>Documentation</strong></a> · 
    <a href="https://codefxr.com"><strong>Website</strong></a> · 
    <a href="https://github.com/CodeFXR/Synapxis/issues"><strong>Report Bug</strong></a>
  </p>
</div>

<br>

<!-- ACTION ITEM: REPLACE THIS WITH A REAL SCREENSHOT OF YOUR APP -->
<p align="center">
  <img src="PATH_TO_YOUR_SCREENSHOT.png" alt="Synapxis Graph View Demo" width="100%" style="border-radius: 10px; border: 1px solid #333;" />
</p>

<br>

## Why Synapxis?

Synapxis combines the speed of a text editor with the insight of a graph database. It is designed for users who live in the terminal and demand performance.

- **Hybrid Engine:** Python handles the TUI while a compiled **Rust** backend calculates graph physics and layout in real-time.
- **High-Def Visuals:** Uses Unicode Braille patterns (2x4 dot matrix) for sub-pixel graph rendering directly in the console.
- **Flow State:** Type `[[` to instantly trigger a popup menu, link notes, and visualize connections without touching the mouse.
- **Dynamic Tagging:** Auto-clusters your graph based on `#tags`. Customize colors in settings to match your mental model.
- **Local & Private:** Your thoughts are stored in a local SQLite database (`notes.db`). No cloud, no tracking.

<br>

## Installation

Get started in seconds with the universal installer for Linux and macOS.

```bash
curl -fsSL https://snx.codefxr.com/install | bash
Note: Requires Python 3.8+. If you want the HD Graphics engine, ensure Rust is installed (curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh).
<br>
Controls
Context	Shortcut	Action
Global	Alt + N	Create New Note
Alt + G	Switch to Graph View
Editing	[[	Autocomplete Link
Alt + E	Export (PDF/HTML/MD)
Graph	Mouse Drag	Pan Camera / Move Nodes
Scroll	Zoom In / Out
F	Find Node
<br>
Architecture
Synapxis is built on a modern TUI stack:
Frontend: Textual (Python) for reactive TUI components.
Backend: Maturin + Rust for heavy graph algorithms.
Storage: SQLite (Async) for instant retrieval of notes and links.
<br>
<p align="center">
&copy; CodeFXR. All rights reserved.
</p>
```

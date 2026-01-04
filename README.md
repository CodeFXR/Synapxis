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

<p align="center">
  <img width="600" height="600" alt="main_demo" src="https://github.com/user-attachments/assets/8335afc7-55e1-43ea-8ceb-f6d12d4b744d" />
</p>

<br>

## Why Synapxis?

Synapxis combines the speed of a text editor with the insight of a graph database. It is designed for users who live in the terminal and demand performance.

- **Hybrid Engine:** Python handles the TUI while a compiled **Rust** backend calculates graph physics and layout in real-time.
- **High-Def Visuals:** Uses Unicode Braille patterns (2x4 dot matrix) for sub-pixel graph rendering directly in the console.
- **Flow State:** Type `[[` to instantly trigger a popup menu, link notes, and visualize connections without touching the mouse.
- **Dynamic Tagging:** Auto-clusters your graph based on `#tags`. Customize colors in settings to match your mental model.
- **Local & Private:** Your thoughts are stored in a local SQLite database (`notes.db`). No cloud, no tracking.

## Installation

Get started in seconds with the universal installer for Linux and macOS.

```bash
curl -fsSL https://snx.codefxr.com/install | bash

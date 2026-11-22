from importlib import import_module

try:
    render_frame = import_module(".synapxis", __name__).render_frame
except ImportError as exc:
    raise ImportError(
        "Synapxis requires its Rust renderer. Install a platform wheel or build from source with Rust."
    ) from exc

__all__ = ["render_frame"]

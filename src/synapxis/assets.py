from __future__ import annotations

import os
from importlib import resources
from pathlib import Path


def _env_override() -> Path | None:
    env = os.environ.get("SYNAPXIS_ASSETS_DIR")
    if not env:
        return None
    candidate = Path(env).expanduser()
    return candidate if candidate.is_dir() else None


def _packaged_assets() -> Path | None:
    try:
        with resources.as_file(
            resources.files("synapxis").joinpath("assets")
        ) as packaged:
            if packaged.is_dir():
                return Path(packaged)
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    return None


def _legacy_assets() -> Path | None:
    legacy = Path.home() / ".synapxis" / "assets"
    return legacy if legacy.is_dir() else None


def asset_root() -> Path:
    """Return the directory containing packaged assets.

    Order of resolution:
    1. ``SYNAPXIS_ASSETS_DIR`` environment variable (developer override).
    2. The ``assets/`` directory inside the ``synapxis`` Python package.
    3. The legacy ``assets/`` directory under ``~/.synapxis/``.

    Raises ``FileNotFoundError`` if none of the locations exist. The previous
    fallback silently created an empty directory next to the package install
    root; that masked broken installs behind a non-functional UI.
    """
    for source in (_env_override, _packaged_assets, _legacy_assets):
        root = source()
        if root is not None:
            return root
    raise FileNotFoundError(
        "No Synapxis assets directory found. Set SYNAPXIS_ASSETS_DIR, "
        "reinstall the package, or place assets under ~/.synapxis/assets/."
    )


def find_asset(*candidates: str) -> Path | None:
    """Return the first existing match for an asset.

    The search order mirrors ``asset_root()``: explicit override, packaged,
    legacy. Returns ``None`` if nothing matches.
    """
    for source in (_env_override, _packaged_assets, _legacy_assets):
        base = source()
        if base is None:
            continue
        for candidate in candidates:
            path = base / candidate
            if path.exists():
                return path
    return None

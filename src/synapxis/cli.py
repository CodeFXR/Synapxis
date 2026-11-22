"""Command-line entry point for Synapxis."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from typing import Any

PROJECT_NAME = "synapxis"


class CliError(RuntimeError):
    pass


def installed_version() -> str:
    try:
        return importlib.metadata.version(PROJECT_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise CliError(
            "Synapxis is not installed; run 'python -m pip install synapxis'."
        ) from exc


def parse_version(version: str) -> tuple[int, int, int] | None:
    value = version.strip().removeprefix("v")
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def command_help_text() -> str:
    return (
        "usage: synapxis [--version] [command] [args]\n\n"
        "Commands:\n"
        "  (no command)        Launch the terminal UI.\n"
        "  update              Show the package-manager upgrade command.\n"
        "  rollback [VERSION]  Show the command for installing a known version.\n"
        "  verify              Check the installed package.\n"
        "  --version           Print the installed version and exit.\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="synapxis",
        description="Synapxis terminal knowledge-graph app.",
        add_help=False,
    )
    parser.add_argument("--version", action="store_true")
    parser.add_argument("command", nargs="?")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def cmd_version(_: Any) -> int:
    print(f"synapxis {installed_version()}")
    return 0


def cmd_verify(_: Any) -> int:
    print(f"synapxis version: {installed_version()}")
    print(f"python: {sys.executable} ({sys.version.split()[0]})")

    package = importlib.util.find_spec("synapxis")
    if package is not None and package.origin:
        print(f"module file: {package.origin}")

    renderer = importlib.util.find_spec("synapxis.synapxis")
    if renderer is not None:
        try:
            import synapxis.synapxis as _native
            print(f"native renderer: loaded (version {_native.version()})")
        except (ImportError, AttributeError):
            print("native renderer: loaded (version <unknown>)")
    else:
        print("native renderer: missing (reinstall a platform wheel)")

    from synapxis.assets import asset_root, find_asset

    root = asset_root()
    print(f"asset root: {root}  (exists={root.exists()})")
    print(f"icon resolved: {find_asset('synapxis_icon.png') or 'missing'}")
    return 0


def cmd_update(remaining: list[str]) -> int:
    if remaining and remaining not in (["--check"], ["--apply"]):
        print("usage: synapxis update [--check|--apply]", file=sys.stderr)
        return 2
    print(f"Installed: {installed_version()}")
    install_root = Path(__file__).resolve().parent.parent.parent
    update_script = install_root / "update.sh"
    if update_script.exists():
        print(f"Run: bash {update_script}")
    else:
        print("Upgrade with: python -m pip install --upgrade synapxis")
    return 0


def cmd_rollback(remaining: list[str]) -> int:
    if len(remaining) > 1:
        print("usage: synapxis rollback [VERSION]", file=sys.stderr)
        return 2
    if not remaining:
        print("Install a known version with:")
        print("  python -m pip install --force-reinstall 'synapxis==<version>'")
        return 0

    version = remaining[0].removeprefix("v")
    if parse_version(version) is None:
        print(f"Invalid semantic version: {remaining[0]!r}", file=sys.stderr)
        return 2
    print(f"Rollback with: python -m pip install --force-reinstall 'synapxis=={version}'")
    return 0


COMMANDS = {
    "update": cmd_update,
    "rollback": cmd_rollback,
    "verify": cmd_verify,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--help":
        print(command_help_text())
        return 0
    if argv and argv[0] == "--version":
        return cmd_version(None)
    if not argv:
        return _launch_tui()

    command, remaining = argv[0], argv[1:]
    if command in COMMANDS:
        try:
            return COMMANDS[command](remaining)
        except CliError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(f"unknown command: {command}", file=sys.stderr)
    print(command_help_text())
    return 2


def _launch_tui() -> int:
    from synapxis.app_factory import cli_main

    cli_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ExportError(Exception):
    pass


@dataclass
class ExportRequest:
    title: str
    content: str
    format: str
    directory: Path
    timeout_seconds: float = 15.0


_RESERVATION_PERMS = 0o600


def _reserve_destination(directory: Path, base: str, extension: str) -> Path:
    """Atomically claim the next non-colliding destination path.

    Creates an empty file at the chosen path with ``O_CREAT | O_EXCL``
    so concurrent exporters cannot pick the same target. Returns the
    reserved path; callers must fill it in (via ``os.replace`` or a
    converter writing in-place) and unlink it on failure.
    """
    candidates = [directory / f"{base}.{extension}"]
    counter = 1
    while len(candidates) < 1000:
        candidates.append(directory / f"{base} ({counter}).{extension}")
        counter += 1
    for candidate in candidates:
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _RESERVATION_PERMS)
        except FileExistsError:
            continue
        os.close(fd)
        return candidate
    raise ExportError(
        f"Could not find a free filename for {base}.{extension!r} "
        f"after 1000 attempts."
    )


async def export_note(request: ExportRequest) -> Path:
    """Write the note to disk in the requested format.

    Collision policy: if the target file already exists, a numeric suffix is
    added (``note.md`` -> ``note (1).md`` -> ``note (2).md``).

    HTML and PDF conversions are delegated to ``pandoc`` and run with a hard
    timeout so the UI stays responsive.
    """
    from ..utils.parsing import sanitize_filename

    safe_title = sanitize_filename(request.title)
    extension = {"md": "md", "html": "html", "pdf": "pdf"}.get(request.format)
    if extension is None:
        raise ExportError(f"Unsupported export format: {request.format}")

    try:
        request.directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Cannot create export directory: {exc}") from exc

    target = await asyncio.to_thread(_reserve_destination, request.directory, safe_title, extension)

    try:
        if request.format == "md":
            await asyncio.to_thread(_write_text_file, target, request.content)
            return target

        if request.format in ("html", "pdf"):
            return await _run_pandoc(request, target)

        raise ExportError(f"Unsupported export format: {request.format}")
    except BaseException:
        with contextlib.suppress(OSError):
            target.unlink()
        raise


def _write_text_file(path: Path, content: str) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix=".export-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


async def _run_pandoc(request: ExportRequest, target: Path) -> Path:
    if request.format == "pdf" and not _weasyprint_available():
        raise ExportError(
            "PDF export requires the 'weasyprint' Python package and its "
            "system libraries (pango, cairo, gdk-pixbuf). Install with "
            "'pip install weasyprint' or use HTML export instead."
        )

    args = ["pandoc", "-f", "markdown"]
    if request.format == "html":
        args += ["-t", "html"]
    elif request.format == "pdf":
        args += ["--pdf-engine=weasyprint"]
    args += ["-o", str(target)]
    content_bytes = request.content.encode("utf-8")

    if shutil.which(args[0]) is None:
        raise ExportError(
            "pandoc is not installed. Install pandoc to export to this format."
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ExportError(f"Could not start pandoc: {exc}") from exc

    try:
        _stdout, stderr = await asyncio.wait_for(
            proc.communicate(content_bytes),
            timeout=request.timeout_seconds,
        )
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(ProcessLookupError):
                await proc.wait()
        raise ExportError(
            f"pandoc did not finish within {request.timeout_seconds:g} seconds."
        ) from None

    if proc.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        if message:
            raise ExportError(f"pandoc failed: {message}")
        raise ExportError("pandoc failed without reporting an error.")

    return target


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    return True

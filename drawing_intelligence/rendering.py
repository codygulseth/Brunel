"""Renderer boundary; local implementation uses installed Poppler without domain coupling."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
from shutil import which
from subprocess import run
from typing import Protocol

from .models import NormalizedBox


@dataclass(frozen=True)
class RenderResult:
    reference: str | None
    width: int
    height: int
    content_hash: str | None
    warning: str | None = None


class PageRenderer(Protocol):
    def render(
        self,
        pdf: Path,
        page_number: int,
        content_hash: str,
        *,
        dpi: int = 144,
        crop: NormalizedBox | None = None,
    ) -> RenderResult: ...


class PopplerPageRenderer:
    def __init__(self, output_root: Path, executable: Path | str = "pdftoppm"):
        self.output_root = output_root.resolve()
        self.executable = which(str(executable)) or str(executable)

    def render(
        self,
        pdf: Path,
        page_number: int,
        content_hash: str,
        *,
        dpi: int = 144,
        crop: NormalizedBox | None = None,
    ) -> RenderResult:
        key = sha256(f"{content_hash}:{page_number}:{dpi}:{crop}:v1".encode()).hexdigest()[:24]
        target = self.output_root / key
        image = target.with_suffix(".png")
        if not image.exists():
            self.output_root.mkdir(parents=True, exist_ok=True)
            crop_arguments: list[str] = []
            if crop is not None:
                full = self.render(pdf, page_number, content_hash, dpi=dpi)
                if full.reference is None:
                    return full
                crop_arguments = [
                    "-x",
                    str(round(crop.x_min * full.width)),
                    "-y",
                    str(round(crop.y_min * full.height)),
                    "-W",
                    str(max(1, round((crop.x_max - crop.x_min) * full.width))),
                    "-H",
                    str(max(1, round((crop.y_max - crop.y_min) * full.height))),
                ]
            command = [
                self.executable,
                "-png",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-r",
                str(dpi),
                "-singlefile",
                *crop_arguments,
                str(pdf),
                str(target),
            ]
            if self.executable.casefold().endswith((".cmd", ".bat")):
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *command]
            try:
                completed = run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, TimeoutError):
                return RenderResult(None, 1, 1, None, "page renderer unavailable")
            if completed.returncode:
                return RenderResult(None, 1, 1, None, "page render failed")
        data = image.read_bytes()
        width, height = _png_size(data)
        return RenderResult(f"render:{key}", width, height, sha256(data).hexdigest())


class NullPageRenderer:
    def render(
        self,
        pdf: Path,
        page_number: int,
        content_hash: str,
        *,
        dpi: int = 144,
        crop: NormalizedBox | None = None,
    ) -> RenderResult:
        return RenderResult(None, 1, 1, None, "renderer unavailable")


def _png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return (1, 1)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

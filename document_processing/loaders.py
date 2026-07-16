"""Local file validation and byte loading."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .errors import SourceFileNotFoundError, UnsupportedFileTypeError
from .models import FileType

SUPPORTED_SUFFIXES = {
    ".pdf": FileType.PDF,
    ".txt": FileType.TEXT,
    ".md": FileType.MARKDOWN,
    ".markdown": FileType.MARKDOWN,
}


@dataclass(frozen=True, slots=True)
class LoadedFile:
    path: Path
    filename: str
    file_type: FileType
    content: bytes
    content_hash: str


class LocalFileLoader:
    """Loads supported local files without retaining uploaded content in the repository."""

    def load(self, path: Path) -> LoadedFile:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise SourceFileNotFoundError(f"Source file does not exist: {path}")
        try:
            file_type = SUPPORTED_SUFFIXES[resolved.suffix.lower()]
        except KeyError as exc:
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{resolved.suffix or '(none)'}'; supported: {supported}"
            ) from exc
        content = resolved.read_bytes()
        return LoadedFile(
            path=resolved,
            filename=resolved.name,
            file_type=file_type,
            content=content,
            content_hash=sha256(content).hexdigest(),
        )

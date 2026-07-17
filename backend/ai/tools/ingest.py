"""INGEST: validación, hash de contenido y almacenamiento de la fuente.

El almacenamiento se abstrae tras ``StorageBackend`` (implementación local por
defecto), para poder cambiarlo (S3, etc.) sin tocar el pipeline.
"""

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ai.errors import FileTooLargeError, UnsupportedFileError

# Extensión -> (source_type, mime, firma mágica esperada al inicio del archivo)
_ALLOWED: dict[str, tuple[str, str, Optional[bytes]]] = {
    ".docx": (
        "document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK",
    ),
    ".pdf": ("document", "application/pdf", b"%PDF"),
    ".txt": ("text", "text/plain", None),
    ".md": ("text", "text/markdown", None),
}


class StorageBackend(ABC):
    """Interfaz de almacenamiento de fuentes."""

    @abstractmethod
    def save(self, content: bytes, name: str) -> str:
        """Guarda el contenido y devuelve su URI/ruta."""

    @abstractmethod
    def read(self, uri: str) -> bytes:
        """Lee el contenido almacenado."""


class LocalStorage(StorageBackend):
    """Almacenamiento en disco local."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, name: str) -> str:
        dest = self.base_dir / name
        dest.write_bytes(content)
        return str(dest)

    def read(self, uri: str) -> bytes:
        return Path(uri).read_bytes()


class IngestResult(BaseModel):
    """Resultado de la ingesta."""

    content_hash: str
    storage_uri: str
    source_type: str  # "document" | "text"
    filename: str
    mime: str
    size_bytes: int
    extension: str


def compute_hash(content: bytes) -> str:
    """SHA-256 hexadecimal del contenido."""
    return hashlib.sha256(content).hexdigest()


def ingest(
    filename: str,
    content: bytes,
    storage: StorageBackend,
    max_upload_mb: int = 10,
) -> IngestResult:
    """Valida MIME/tamaño, calcula hash y almacena la fuente."""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED:
        raise UnsupportedFileError(
            f"Extensión no soportada: '{ext}'. Permitidas: {sorted(_ALLOWED)}"
        )

    source_type, mime, magic = _ALLOWED[ext]

    max_bytes = max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise FileTooLargeError(f"El archivo supera el máximo de {max_upload_mb} MB.")
    if len(content) == 0:
        raise UnsupportedFileError("El archivo está vacío.")

    if magic is not None and not content.startswith(magic):
        raise UnsupportedFileError(
            f"El contenido no corresponde a un archivo {ext} válido."
        )

    content_hash = compute_hash(content)
    stored_name = f"{content_hash}{ext}"
    storage_uri = storage.save(content, stored_name)

    return IngestResult(
        content_hash=content_hash,
        storage_uri=storage_uri,
        source_type=source_type,
        filename=filename,
        mime=mime,
        size_bytes=len(content),
        extension=ext,
    )

"""Safe, read-only archive access. No file extraction and no execution of archive content."""
from __future__ import annotations
import io
import re
import zipfile
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def safe_entry(name: str) -> bool:
    """Avoid unsafe filenames even if consumers of exported archives extract them."""
    normalized=name.replace("\\", "/")
    parts=normalized.split("/")
    return (not normalized.startswith("/") and ":" not in parts[0]
            and all(p not in {"", ".", ".."} for p in parts))
MAX_PAGE_BYTES = 70 * 1024 * 1024
MAX_PIXELS = 60_000_000
MAX_PAGES = 1000


def natural_key(value: str):
    return [int(s) if s.isdigit() else s.casefold() for s in re.split(r"(\d+)", value)]


class Archive:
    def __init__(self, source: str | Path):
        self.path = Path(source).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.ext = self.path.suffix.lower()
        if self.ext == ".cbz":
            self.reader = zipfile.ZipFile(self.path)
            infos = [i for i in self.reader.infolist()
                     if not i.is_dir() and safe_entry(i.filename) and Path(i.filename).suffix.lower() in IMAGE_EXT
                     and not Path(i.filename).name.startswith(".")]
            oversized = [i.filename for i in infos if i.file_size > MAX_PAGE_BYTES]
            if oversized:
                self.reader.close()
                raise ValueError(f"Pagina troppo grande: {oversized[0]}")
            names = [i.filename for i in infos]
        elif self.ext == ".cbr":
            try:
                import rarfile
            except ImportError as exc:
                raise RuntimeError("Per CBR: pip install comictranslate-it[cbr] e 7-Zip/UnRAR") from exc
            try:
                self.reader = rarfile.RarFile(self.path)
                infos = [i for i in self.reader.infolist()
                         if not i.isdir() and safe_entry(i.filename) and Path(i.filename).suffix.lower() in IMAGE_EXT]
                oversized = [i.filename for i in infos if i.file_size > MAX_PAGE_BYTES]
                if oversized:
                    raise ValueError(f"Pagina troppo grande: {oversized[0]}")
                names = [i.filename for i in infos]
            except Exception as exc:
                raise RuntimeError("Non riesco a leggere il CBR: controlla RAR e l'estrattore installato") from exc
        else:
            raise ValueError("Formato non supportato: sono necessari .cbz o .cbr")
        self.names = sorted(names, key=natural_key)
        if not self.names or len(self.names) > MAX_PAGES:
            self.reader.close()
            raise ValueError("Archivio senza immagini, o con un numero eccessivo di pagine")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.reader.close()

    def raw(self, filename: str) -> bytes:
        if filename not in self.names:
            raise KeyError(filename)
        # Some RAR backends report inaccurate uncompressed lengths: enforce again after read.
        with self.reader.open(filename) as f:
            blob = f.read(MAX_PAGE_BYTES + 1)
        if len(blob) > MAX_PAGE_BYTES:
            raise ValueError(f"Pagina troppo grande: {filename}")
        return blob

    def image(self, filename: str) -> Image.Image:
        try:
            with Image.open(io.BytesIO(self.raw(filename))) as im:
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError(f"Immagine troppo grande: {filename}")
                return ImageOps.exif_transpose(im).convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f"Immagine non leggibile: {filename}") from exc

"""Project persistence, with atomic JSON replacement and original archive unchanged."""
import json
import os
import io
from PIL import Image
from pathlib import Path
from dataclasses import dataclass, field
from .models import Page
from .archives import Archive

PROJECT_VERSION = 1


@dataclass
class Project:
    source: str
    pages: list[Page] = field(default_factory=list)
    version: int = PROJECT_VERSION
    glossary: dict[str, str] = field(default_factory=dict)
    path: Path | None = None
    lettering_profile: dict = field(default_factory=dict)

    @classmethod
    def create(cls, source: str, project_path: str):
        with Archive(source) as archive:
            dimensions={}
            for name,raw in archive.iter_raw():
                with Image.open(io.BytesIO(raw)) as image:
                    width,height=image.size
                    if image.getexif().get(274,1) in (5,6,7,8):
                        width,height=height,width
                    if width*height>60_000_000:
                        raise ValueError(f"Pagina con troppi pixel: {name}")
                    dimensions[name]=(width,height)
            pages=[Page(name,*dimensions[name]) for name in archive.names]
        result = cls(source=str(Path(source).resolve()), pages=pages)
        result.save(project_path)
        return result

    @classmethod
    def load(cls, path: str):
        file = Path(path).resolve()
        data = json.loads(file.read_text(encoding="utf-8"))
        if data.get("version") != PROJECT_VERSION:
            raise ValueError("Versione del progetto non supportata")
        source = Path(data["source"])
        if not source.is_absolute():
            source = file.parent / source
        return cls(str(source.resolve()), [Page.from_dict(p) for p in data["pages"]],
                   data["version"], data.get("glossary", {}), file, data.get("lettering_profile", {}))

    def save(self, path: str | None = None):
        file = Path(path or self.path or "project.json").resolve()
        file.parent.mkdir(parents=True, exist_ok=True)
        source = Path(self.source).resolve()
        try:
            relative = os.path.relpath(source, file.parent)
        except ValueError:
            # Windows: source and project can live on separate drive letters.
            relative = str(source)
        data = {"version": self.version, "source": relative,
                "pages": [page.to_dict() for page in self.pages], "glossary": self.glossary,
                "lettering_profile": self.lettering_profile}
        temp = file.with_suffix(file.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, file)
        self.path = file

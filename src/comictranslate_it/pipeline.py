"""Pipeline: scan suggestions, reviewed translation, safe export."""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from .archives import Archive
from .project import Project
from .detection import scan_page
from .rendering import render_page
from .translation import translate_page


def scan(project: Project, min_conf: float=50, overwrite: bool=False) -> int:
    changes=0
    with Archive(project.source) as archive:
        for page in project.pages:
            if page.regions and not overwrite:
                continue
            page.regions=scan_page(archive.image(page.filename),min_conf)
            changes+=len(page.regions)
    project.save()
    return changes


def translate(project: Project, model: str="gpt-4.1-mini",base_url: str="https://api.openai.com/v1"):
    changed=0
    history=[]
    for page in project.pages:
        regions=[r for r in page.regions if r.original.strip() and not r.italian.strip()]
        if regions:
            transient=type(page)(page.filename,page.width,page.height,regions)
            out=translate_page(transient, project.glossary,history,model,base_url)
            for r in regions:
                r.italian=out[r.id]
                r.approved=False
                changed+=1
            project.save()  # checkpoint after every valid page
        history.append(" / ".join(r.italian for r in page.regions if r.italian.strip())[:1500])
    return changed


def export(project: Project, destination: str, font_path: str | None=None):
    """Do not rewrite the source. Preserve original page bytes when no region applied."""
    dest=Path(destination).resolve()
    if dest.suffix.lower() != ".cbz":
        raise ValueError("L'export deve essere .cbz (formato senza perdita)")
    if dest==Path(project.source).resolve():
        raise ValueError("Non è consentito sovrascrivere l'archivio originale")
    dest.parent.mkdir(parents=True,exist_ok=True)
    log=[]
    tmp=dest.with_suffix(".cbz.part")
    # Avoid filename collisions when modified JPG/WEBP pages become PNG.
    reserved={page.filename.casefold() for page in project.pages}
    used=set()
    try:
        with Archive(project.source) as archive,zipfile.ZipFile(tmp,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as output:
            for page in project.pages:
                if not any(r.approved and r.italian.strip() for r in page.regions):
                    # Skip expensive full-raster work and preserve original bytes unchanged.
                    output.writestr(page.filename,archive.raw(page.filename))
                    used.add(page.filename.casefold())
                    log.append({"page":page.filename,"modified":False,
                                "regions":[{"id":r.id,"applied":False,
                                            "message":"Non approvato oppure privo di traduzione"}
                                           for r in page.regions]})
                    continue
                image,reports=render_page(archive.image(page.filename),page.regions,font_path,
                                            target_fill=project.lettering_profile.get("target_line_fill",.68))
                applied=any(r.applied for r in reports)
                # Flatten output to RGB PNG iff modified. Original raw bytes remain otherwise.
                if applied:
                    buffer=io.BytesIO(); image.save(buffer,"PNG")
                    name=str(Path(page.filename).with_suffix(".png"))
                    if (name.casefold() in used or
                        (name.casefold() in reserved and name.casefold()!=page.filename.casefold())):
                        stem=Path(page.filename).with_suffix("")
                        attempt=1
                        while True:
                            name=f"{stem}__it_{attempt}.png"
                            if name.casefold() not in reserved and name.casefold() not in used:
                                break
                            attempt+=1
                    output.writestr(name,buffer.getvalue())
                else:
                    name=page.filename
                    output.writestr(name,archive.raw(page.filename))
                used.add(name.casefold())
                log.append({"page":page.filename,"modified":applied,
                            "regions":[r.__dict__ for r in reports]})
        tmp.replace(dest)
    finally:
        if tmp.exists(): tmp.unlink()
    logfile=dest.with_suffix(".report.json")
    logfile.write_text(json.dumps({"output":str(dest),"pages":log},ensure_ascii=False,indent=2),encoding="utf-8")
    return log
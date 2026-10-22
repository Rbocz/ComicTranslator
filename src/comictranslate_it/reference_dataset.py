"""Build a local, privacy-preserving bilingual chapter reference benchmark."""
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageOps
from .archives import Archive
from .reference_matching import match_references,save_matches
from .reference_benchmark import evaluate_arrays,write_profile,ReferenceError


def prepare_dataset(archive_path:str,references:list[str],outdir:str,
                    save_overlays:bool=False):
    """Pair Italian references with source pages, ignoring duplicate partial crops."""
    folder=Path(outdir).resolve()
    folder.mkdir(parents=True,exist_ok=True)
    pairing=match_references(archive_path,references)
    save_matches(pairing,str(folder/"matches.json"))
    by_page={}
    for item in pairing["matches"]:
        selected=item["selected"]
        if selected is None:continue
        previous=by_page.get(selected["filename"])
        if previous is None or selected["inliers"]>previous["selected"]["inliers"]:
            by_page[selected["filename"]]=item
    lookup={Path(path).name:path for path in references}
    results=[]
    with Archive(archive_path) as archive:
        for filename,item in sorted(by_page.items(),key=lambda x:x[1]["selected"]["page"]):
            with Image.open(lookup[item["italian_file"]]) as image:
                target=np.array(ImageOps.exif_transpose(image).convert("RGB"))
            source=np.asarray(archive.image(filename))
            index=item["selected"]["page"]
            overlay=str(folder/f"page_{index:03}_overlay.png") if save_overlays else None
            try:
                report=evaluate_arrays(source,target,overlay=overlay)
                report["archive_page"]=index
                report["italian_file"]=item["italian_file"]
                report["archive_entry"]=filename
                (folder/f"page_{index:03}_metrics.json").write_text(
                    json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                results.append(report)
            except ReferenceError as exc:
                results.append({"archive_page":index,
                    "italian_file":item["italian_file"],
                    "error":str(exc),"candidate_balloon_count":0,"balloons":[]})
    errors=[]
    good=[r for r in results if "error" not in r]
    profile=None
    try:
        profile=write_profile(good,str(folder/"lettering_profile.json"))
    except ReferenceError as exc:
        errors.append(str(exc))
    summary={"schema":1,"chapter_archive_pages":pairing["archive_pages"],
        "provided_references":len(references),
        "high_confidence_matches":sum(item["confidence"]=="high" for item in pairing["matches"]),
        "distinct_matched_pages":len(by_page),"processed_pages":len(good),
        "archive_page_numbers":[r["archive_page"] for r in results],
        "balloon_candidates":sum(r["candidate_balloon_count"] for r in good),
        "pages_without_detected_balloons":[r["archive_page"] for r in good if not r["candidate_balloon_count"]],
        "style_profile":profile,"style_is_provisional":True,"errors":errors,
        "notice":"Calibration only. Does not train detector, approve translations, or provide exact erasure masks."}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

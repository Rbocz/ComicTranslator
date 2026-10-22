"""Find matching pages in CBZ/CBR by artwork, not recognized text.

This module is offline. Only page numbers, paths and geometric scores are saved.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from io import BytesIO
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image,ImageOps
from .archives import Archive,MAX_PIXELS


@dataclass
class Candidate:
    page: int
    filename: str
    inliers: int
    matches: int
    inlier_fraction: float
    median_reprojection_error: float | None


def _describe(image: Image.Image,detector,max_edge:int=1000):
    im=ImageOps.exif_transpose(image).convert("RGB")
    im.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
    gray=cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2GRAY)
    return detector.detectAndCompute(gray,None)


def compare_descriptors(a,b,matcher=None):
    ka,da=a;kb,db=b
    if da is None or db is None or len(da)<16 or len(db)<16:
        return (0,0,0.,None)
    matcher=matcher or cv2.BFMatcher(cv2.NORM_L2)
    good=[m for m,n in matcher.knnMatch(da,db,k=2) if m.distance<.74*n.distance]
    if len(good)<10:return (0,len(good),0.,None)
    points_a=np.float32([ka[m.queryIdx].pt for m in good])
    points_b=np.float32([kb[m.trainIdx].pt for m in good])
    affine,inliers=cv2.estimateAffinePartial2D(points_a,points_b,method=cv2.RANSAC,
                                               ransacReprojThreshold=4,maxIters=2500)
    if affine is None or inliers is None:
        return (0,len(good),0.,None)
    scale=float(np.hypot(affine[0,0],affine[0,1]))
    if not .2<=scale<=5.0:
        return (0,len(good),0.,None)  # reject degenerate collapsed transforms
    mask=inliers.ravel().astype(bool)
    n=int(mask.sum())
    mapped=cv2.transform(points_a.reshape(-1,1,2),affine).reshape(-1,2)
    error=float(np.median(np.linalg.norm(mapped[mask]-points_b[mask],axis=1))) if n else None
    return (n,len(good),round(n/len(good),3),round(error,3) if error is not None else None)


def match_references(archive_path:str,reference_paths:list[str],min_inliers:int=35):
    """Require >=35 true inliers and >=2.5x advantage over the runner-up.

    Low-quality/ambiguous matches remain unselected instead of guessing.
    """
    if not reference_paths:raise ValueError("No Italian reference pages provided")
    sift=cv2.SIFT_create(nfeatures=900,contrastThreshold=.018)
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    refs=[]
    for path in reference_paths:
        with Image.open(path) as image:
            if image.width*image.height>MAX_PIXELS:
                raise ValueError(f"Reference exceeds pixel limit: {path}")
            refs.append((str(Path(path)),_describe(image,sift)))
    ranked={path:[] for path,_ in refs}
    with Archive(archive_path) as archive:
        indexed={name:i+1 for i,name in enumerate(archive.names)}
        count=len(indexed)
        for name,data in archive.iter_raw():
            with Image.open(BytesIO(data)) as image:
                if image.width*image.height>MAX_PIXELS:
                    raise ValueError(f"Archive page exceeds pixel limit: {name}")
                desc=_describe(image,sift)
            for path,ref in refs:
                n,m,frac,err=compare_descriptors(ref,desc,matcher)
                if n:
                    ranked[path].append(Candidate(indexed[name],name,n,m,frac,err))
    records=[]
    for path,values in ranked.items():
        values.sort(key=lambda x:(-x.inliers,-x.matches,x.page))
        best=values[0] if values else None
        runner=values[1] if len(values)>1 else None
        margin=round(best.inliers/max(1,runner.inliers),2) if best else 0
        good=bool(best and best.inliers>=min_inliers and margin>=2.5)
        records.append({"italian_file":Path(path).name,
                        "confidence":"high" if good else "needs_review",
                        "top_margin":margin,
                        "selected":asdict(best) if good else None,
                        "candidates":[asdict(v) for v in values[:3]]})
    return {"schema":1,"archive_pages":count,
            "method":"SIFT+RANSAC artwork registration",
            "reference_count":len(records),"matches":records,
            "warning":"Matches are not balloon annotations or pixel-perfect cleanup masks."}


def save_matches(report:dict,out:str):
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

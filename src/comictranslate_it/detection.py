"""Conservative bright-balloon detection with OCR inside recovered balloon contours.

Western-comics-specific learned detector is a future optional adapter. Every
found region is a *suggestion*: approved=False regardless of OCR confidence.
"""
from __future__ import annotations
import numpy as np
import cv2
from PIL import Image
from .models import Rect,Region


def find_balloons(image: Image.Image):
    """Find enclosed, high-luminance contours (not arbitrary white page regions).

    Returns (rect, actual polygon, filled interior mask). Enclosure heuristics
    are intentionally strict: colorful captions will need the learned detector.
    """
    arr=np.asarray(image.convert("RGB"))
    height,width=arr.shape[:2]
    light=np.uint8(np.all(arr>=224,axis=2))*255
    light=cv2.morphologyEx(light,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(light,connectivity=8)
    candidates=[]
    for index in range(1,count):
        x,y,w,h,area=(int(v) for v in stats[index])
        if min(w,h)<40 or area<1400 or area>width*height*.70:
            continue
        if x<=2 or y<=2 or x+w>=width-2 or y+h>=height-2:
            continue
        if area/(w*h)<.38:
            continue
        pixels=np.uint8(labels[y:y+h,x:x+w]==index)*255
        contours,_=cv2.findContours(pixels,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour=max(contours,key=cv2.contourArea)
        if cv2.contourArea(contour)<area*.62:
            continue
        outline=cv2.approxPolyDP(contour,.003*cv2.arcLength(contour,True),True)
        polygon=[[int(p[0][0])+x,int(p[0][1])+y] for p in outline]
        if len(polygon)<3:
            continue
        interior=np.zeros((h,w),np.uint8)
        cv2.drawContours(interior,[contour],-1,255,thickness=-1)
        interior=cv2.erode(interior,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
        candidates.append((Rect(x,y,x+w,y+h),polygon,interior))
    # Smallest shapes first so nested bright regions don't swallow others.
    return sorted(candidates,key=lambda item:item[0].width*item[0].height)


def guess_balloon(image: Image.Image, words: list[Rect]):
    if not words:return None
    for box,polygon,_ in find_balloons(image):
        if all(word.x1>=box.x1+3 and word.y1>=box.y1+3 and
               word.x2<=box.x2-3 and word.y2<=box.y2-3 for word in words):
            return box,polygon
    return None


def _extract_words(image: Image.Image, config: str="--psm 6",min_conf: float=50):
    try:
        import pytesseract
        import os
        from pathlib import Path
        from pytesseract import Output
        exe = os.environ.get("TESSERACT_CMD")
        if not exe and os.name=="nt":
            standard=Path(os.environ.get("ProgramFiles", "C:/Program Files"))/"Tesseract-OCR"/"tesseract.exe"
            if standard.exists():
                exe=str(standard)
        if exe:
            pytesseract.pytesseract.tesseract_cmd=exe
        results=pytesseract.image_to_data(image,lang="eng",config=config,output_type=Output.DICT)
    except Exception as exc:
        raise RuntimeError("OCR non disponibile: installare Tesseract con lingua inglese") from exc
    rows=[]
    for i,text in enumerate(results["text"]):
        text=text.strip()
        try:confidence=float(results["conf"][i])
        except (ValueError,TypeError):continue
        if confidence < min_conf or not text:
            continue
        x,y,w,h=(int(results[k][i]) for k in ("left","top","width","height"))
        if w<2 or h<3:continue
        line_key=(int(results["block_num"][i]),int(results["par_num"][i]),int(results["line_num"][i]))
        rows.append((text,Rect(x,y,x+w,y+h),confidence,line_key))
    return rows


def _region_from_words(rows,image,region_id,box,polygon,source,detected):
    by_line={}
    for text,rect,confidence,key in rows:
        by_line.setdefault(key,[]).append((text,rect,confidence))
    sorted_lines=sorted(by_line.values(),key=lambda line:min(item[1].y1 for item in line))
    source_text=" ".join(" ".join(item[0] for item in sorted(line,key=lambda item:item[1].x1)) for line in sorted_lines)
    words=[row[1] for row in rows]
    mean_conf=sum(row[2] for row in rows)/len(rows)/100
    capitals=sum(ch.isupper() for ch in source_text if ch.isalpha())
    alphas=max(1,sum(ch.isalpha() for ch in source_text))
    return Region(id=region_id,balloon=box,words=words,original=source_text,
                  kind="dialogue" if detected else "art_text",
                  shape="polygon" if detected else "rect",polygon=polygon,
                  detected=detected,approved=False,confidence=round(mean_conf,3),
                  source=source,uppercase=capitals/alphas>=.65,
                  preferred_lines=len(sorted_lines))


def scan_page(image: Image.Image, min_conf: float=50) -> list[Region]:
    """OCR closed white balloons first, then try full-page fallback for captions.

    Bright contour OCR is superior to page-wide Tesseract for many comics but
    not robust for drawings overlapping speech balloons. We don't approve it.
    """
    rgb=np.asarray(image.convert("RGB"))
    regions=[]
    candidates=find_balloons(image)
    for box,polygon,inside in candidates:
        x1,y1,x2,y2=box.as_tuple()
        crop=rgb[y1:y2,x1:x2].copy()
        crop[inside==0]=255  # remove border/art only in temporary OCR buffer
        rows=_extract_words(Image.fromarray(crop),"--psm 6",min_conf)
        if not rows:
            rows=_extract_words(Image.fromarray(crop),"--psm 11",min_conf)
        if not rows:
            continue
        absolute=[(text,Rect(r.x1+x1,r.y1+y1,r.x2+x1,r.y2+y1),confidence,key)
                  for text,r,confidence,key in rows]
        regions.append(_region_from_words(absolute,image,f"r{len(regions)+1:03}",box,polygon,
                                           "bright-contour+tesseract",True))
    # OCR fallback: add only words with high confidence outside detected balloons.
    full=_extract_words(image,"--psm 11",max(65,min_conf))
    used=lambda r: any(r.x1>=region.balloon.x1 and r.x2<=region.balloon.x2 and
                       r.y1>=region.balloon.y1 and r.y2<=region.balloon.y2 for region in regions)
    clusters={}
    for text,rect,conf,key in full:
        if used(rect):continue
        clusters.setdefault(key,[]).append((text,rect,conf,key))
    for key,rows in clusters.items():
        x1=min(r.x1 for _,r,_,_ in rows);y1=min(r.y1 for _,r,_,_ in rows)
        x2=max(r.x2 for _,r,_,_ in rows);y2=max(r.y2 for _,r,_,_ in rows)
        rect=Rect(max(0,x1-9),max(0,y1-9),min(image.width,x2+9),min(image.height,y2+9))
        # OCR-only rectangle has no closed balloon: never treat as verified.
        regions.append(_region_from_words(rows,image,f"r{len(regions)+1:03}",rect,[],
                                           "tesseract-only-unverified",False))
    return regions

"""Private, offline English/Italian comic reference comparison.

Estimates layout statistics from already-published translations. This is NOT
neural training or a pixel-perfect text difference mask. Input images stay local.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .detection import find_balloons
from .lettering import _largest_interval


class ReferenceError(ValueError):
    pass


def _rgb(path):
    with Image.open(path) as img:
        if img.width*img.height>60_000_000:
            raise ReferenceError("Image too large")
        return np.asarray(img.convert("RGB"))


def split_pages(img: np.ndarray):
    """Detect full-width white bands splitting stacked book pages."""
    white=(np.min(img,axis=2)>=245).mean(axis=1)>=.985
    changes=np.diff(np.r_[False,white,False].astype(np.int8))
    starts=np.flatnonzero(changes==1)
    ends=np.flatnonzero(changes==-1)
    spans=[];last=0
    for start,end in zip(starts,ends):
        if end-start>=7 and start>img.shape[0]*.17 and end<img.shape[0]*.86:
            if start-last>=120:spans.append((int(last),int(start)))
            last=int(end)
    if img.shape[0]-last>=120:spans.append((int(last),int(img.shape[0])))
    return spans or [(0,img.shape[0])]


def select_part(img: np.ndarray,part: int):
    spans=split_pages(img)
    if part<1 or part>len(spans):
        raise ReferenceError(f"Found {len(spans)} parts, requested {part}")
    a,b=spans[part-1]
    return img[a:b].copy(),(a,b),len(spans)


def register(source: np.ndarray, target: np.ndarray):
    """Fit rotation+scale+translation from SIFT matches on artwork."""
    gray_a=cv2.cvtColor(source,cv2.COLOR_RGB2GRAY)
    gray_b=cv2.cvtColor(target,cv2.COLOR_RGB2GRAY)
    sift=cv2.SIFT_create(nfeatures=7000)
    points_a,descriptors_a=sift.detectAndCompute(gray_a,None)
    points_b,descriptors_b=sift.detectAndCompute(gray_b,None)
    if descriptors_a is None or descriptors_b is None or len(points_a)<25 or len(points_b)<25:
        raise ReferenceError("Insufficient image detail for alignment")
    candidates=cv2.BFMatcher(cv2.NORM_L2).knnMatch(descriptors_a,descriptors_b,k=2)
    good=[m for m,n in candidates if m.distance<.72*n.distance]
    if len(good)<24:raise ReferenceError("English/Italian pages do not correspond reliably")
    a=np.float32([points_a[m.queryIdx].pt for m in good])
    b=np.float32([points_b[m.trainIdx].pt for m in good])
    matrix,inliers=cv2.estimateAffinePartial2D(
        a,b,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=7000,confidence=.995)
    if matrix is None or inliers is None:raise ReferenceError("Registration failed")
    ok=inliers.ravel().astype(bool)
    count=int(ok.sum())
    if count<25 or count/len(good)<.15:
        raise ReferenceError("Registration inliers too low")
    predicted=cv2.transform(a.reshape(-1,1,2),matrix).reshape(-1,2)
    rms=float(np.sqrt(np.mean(np.sum((predicted[ok]-b[ok])**2,axis=1))))
    if rms>3:raise ReferenceError("Registration residual too high")
    h,w=target.shape[:2]
    aligned=cv2.warpAffine(source,matrix,(w,h),borderValue=(255,255,255))
    valid=cv2.warpAffine(np.ones(gray_a.shape,np.uint8),matrix,(w,h),
                         flags=cv2.INTER_NEAREST)>0
    return aligned,valid,{"inliers":count,"matches":len(good),"rms_px":round(rms,3),
       "scale":round(float(np.hypot(matrix[0,0],matrix[0,1])),4),
       "affine":np.round(matrix,5).tolist()}


def _line_metrics(img,mask,rect):
    try:
        import pytesseract
        from pytesseract import Output
        x1,y1,x2,y2=rect.as_tuple()
        patch=img[y1:y2,x1:x2].copy()
        patch[mask[y1:y2,x1:x2]==0]=255
        result=pytesseract.image_to_data(Image.fromarray(patch),lang="ita",config="--psm 6",
                                         output_type=Output.DICT)
    except (ImportError,RuntimeError,OSError,ValueError):
        return {"line_count":None,"mean_line_fill":None,"ocr_word_count":0}
    grouped={}
    for i,token in enumerate(result["text"]):
        try:confidence=float(result["conf"][i])
        except (ValueError,TypeError):continue
        if not token.strip() or confidence<35:continue
        left=int(result["left"][i])+x1;top=int(result["top"][i])+y1
        width=int(result["width"][i]);height=int(result["height"][i])
        if width<2 or height<4:continue
        key=(result["block_num"][i],result["par_num"][i],result["line_num"][i])
        grouped.setdefault(key,[]).append((left,top,left+width,top+height))
    fills=[]
    for line in grouped.values():
        left=min(box[0] for box in line);right=max(box[2] for box in line)
        ylo=max(0,min(box[1] for box in line))
        yhi=min(img.shape[0],max(box[3] for box in line))
        if yhi-ylo<4:continue
        interval=_largest_interval(mask,ylo,yhi)
        if not interval or interval[1]-interval[0]<10:continue
        ratio=(right-left)/(interval[1]-interval[0])
        if .12<=ratio<=1.08:fills.append(min(1.,ratio))
    return {"line_count":len(fills) or None,
            "mean_line_fill":round(float(np.mean(fills)),3) if fills else None,
            "ocr_word_count":sum(len(v) for v in grouped.values())}


def evaluate(english: str,italian: str,part: int=1,overlay: str|None=None):
    return evaluate_arrays(_rgb(english),_rgb(italian),part,overlay)


def evaluate_arrays(raw: np.ndarray,target: np.ndarray,part: int=1,overlay: str|None=None):
    """Read both pages from memory; never extract scans into a public repository."""
    raw=np.asarray(raw,dtype=np.uint8);target=np.asarray(target,dtype=np.uint8)
    if raw.ndim!=3 or target.ndim!=3 or raw.shape[2]!=3 or target.shape[2]!=3:
        raise ReferenceError("Expected RGB images")
    if raw.shape[0]*raw.shape[1]>60_000_000:
        raise ReferenceError("Page is too large")
    if max(raw.shape[:2])>1900:
        ratio=1900/max(raw.shape[:2])
        raw=cv2.resize(raw,(round(raw.shape[1]*ratio),round(raw.shape[0]*ratio)),
                       interpolation=cv2.INTER_AREA)
    source_ratio=raw.shape[1]/raw.shape[0]
    target_ratio=target.shape[1]/target.shape[0]
    # A full-width panel gutter should not split a *single* complete page.
    if part==1 and abs(source_ratio/target_ratio-1)<.10:
        source=raw;span=(0,raw.shape[0]);parts=1
    else:
        source,span,parts=select_part(raw,part)
    aligned,valid,alignment=register(source,target)
    h,w=target.shape[:2]
    gray_a=cv2.cvtColor(aligned,cv2.COLOR_RGB2GRAY)
    gray_b=cv2.cvtColor(target,cv2.COLOR_RGB2GRAY)
    guide=target.copy()
    balloons=[]
    for rect,polygon,_ in find_balloons(Image.fromarray(target)):
        mask=np.zeros((h,w),np.uint8)
        cv2.fillPoly(mask,[np.asarray(polygon,dtype=np.int32)],255)
        mask=cv2.erode(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
        ok=(mask>0)&valid
        if np.count_nonzero(ok)<300:continue
        changed=float(np.mean(np.abs(gray_a[ok].astype(np.int16)-
                                     gray_b[ok].astype(np.int16))>45))
        balloons.append({"box_it":list(rect.as_tuple()),
                         "changed_pixel_fraction":round(changed,3),
                         **_line_metrics(target,mask,rect)})
        cv2.rectangle(guide,(rect.x1,rect.y1),(rect.x2,rect.y2),(40,230,65),2)
    # RGB changes in color-rich illustration are *not* an exact preservation test:
    # resizing, compressions and color grading all contribute to this estimate.
    color_area=(np.ptp(target,axis=2)>35)&valid
    diff=(float(np.mean(np.abs(target[color_area].astype(np.float32)-
                                aligned[color_area].astype(np.float32))))
          if np.any(color_area) else None)
    if overlay:
        path=Path(overlay);path.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(guide).save(path)
    return {"schema":1,"source_part":part,"parts_in_english_file":parts,
            "source_y_range":list(span),"target_dimensions":[w,h],
            "alignment":alignment,"candidate_balloon_count":len(balloons),
            "balloons":balloons,
            "illustration_mean_abs_difference":round(diff,2) if diff is not None else None,
            "note":"Measurements are approximate; detector misses irregular balloons, OCR may miss words."}


def write_profile(reports:list[dict],output:str):
    fills=[r["mean_line_fill"] for report in reports for r in report["balloons"]
           if r["mean_line_fill"] is not None and r["ocr_word_count"]>=2
           and (r.get("line_count") is None or 1<=r["line_count"]<=7)]
    if len(fills)<3:
        raise ReferenceError("Not enough measured Italian dialogue lines for calibration")
    target=round(float(np.clip(np.median(fills),.50,.86)),3)
    profile={"schema":1,"sample_balloon_count":len(fills),
             "target_line_fill":target,
             "method":"median OCR line width / available balloon span",
             "review_status":"provisional",
             "warning":"Small automatically detected OCR sample: some multi-balloon groups may remain. Not model training."}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding="utf-8")
    return profile

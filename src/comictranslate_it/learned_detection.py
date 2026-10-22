"""Optional RT-DETRv2 ONNX detector; output is REVIEW-ONLY rectangles.

The model predicts boxes, not exact balloon/text pixel masks. Do not pass its
boxes to erasure, automatically approve edits, or call them segmentation.
Original model: ogkalu/comic-text-and-bubble-detector (Apache-2.0).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
from urllib.request import urlopen, Request

import cv2
import numpy as np
from .shape_refinement import refine_light_surface
from PIL import Image

MODEL_REPOSITORY = "ogkalu/comic-text-and-bubble-detector"
MODEL_REVISION = "43838e758e4a097f7dc42f001ac8c8b79ed6ebe5"
MODEL_FILENAME = "detector-v4-s_int8.onnx"
# SHA-256 as published by the original model host for the immutable revision.
MODEL_SHA256 = "39c71e6c7ba356ae14cbfe8033c104d093230cc427b50e6f72f4623f78f2975b"
MODEL_URL = (f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/"
             f"{MODEL_REVISION}/{MODEL_FILENAME}")
CLASS_NAMES = {0:"bubble", 1:"text_bubble", 2:"text_free"}
INPUT_SIZE = (640, 640)
MAX_MODEL_BYTES = 25 * 1024 * 1024


class ModelNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class Detection:
    cls: int
    score: float
    box: tuple[int,int,int,int]


def verify_model_file(path: str | Path) -> bool:
    file=Path(path)
    if not file.is_file():return False
    digest=hashlib.sha256()
    with file.open("rb") as data:
        for chunk in iter(lambda:data.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()==MODEL_SHA256


def fetch_model(destination: str | Path) -> Path:
    """Explicit download only; fail closed on mismatch, no untrusted weights run."""
    dest=Path(destination).expanduser().resolve()
    if dest.is_file():
        if verify_model_file(dest):return dest
        raise ModelNotReady(f"Il file esistente non corrisponde al modello verificato: {dest}")
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+".part")
    digest=hashlib.sha256()
    total=0
    try:
        with urlopen(Request(MODEL_URL,headers={"User-Agent":"ComicTranslate-IT/0.5"}),timeout=40) as response, temp.open("wb") as file:
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>MAX_MODEL_BYTES:raise ModelNotReady("Modello oltre il limite previsto")
                digest.update(chunk);file.write(chunk)
        if digest.hexdigest()!=MODEL_SHA256:
            raise ModelNotReady("Checksum SHA-256 errato: download non utilizzabile")
        os.replace(temp,dest)
        return dest
    except (OSError,TimeoutError) as exc:
        raise ModelNotReady(f"Download modello non riuscito: {exc}") from exc
    finally:
        temp.unlink(missing_ok=True)


def preprocess(image: Image.Image) -> dict[str,np.ndarray]:
    """Match v4-s INT8 ONNX interface: RGB/255 stretched to 640 square.

    The graph postprocess expects original dimensions in [width, height] order.
    """
    rgb=np.asarray(image.convert("RGB"),dtype=np.uint8)
    image640=cv2.resize(rgb,INPUT_SIZE,interpolation=cv2.INTER_LINEAR)
    data=np.transpose(image640.astype(np.float32)/255.0,(2,0,1))[None]
    sizes=np.array([[image.width,image.height]],dtype=np.int64)
    return {"images":np.ascontiguousarray(data),"orig_target_sizes":sizes}


def _iou_box(a,b):
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    intersection=max(0,x2-x1)*max(0,y2-y1)
    da=max(0,a[2]-a[0])*max(0,a[3]-a[1])
    db=max(0,b[2]-b[0])*max(0,b[3]-b[1])
    return intersection/max(1,da+db-intersection)


def postprocess(raw: dict, width:int,height:int,score_threshold:float=.3, nms_iou:float=.65) -> list[Detection]:
    """Validate ONNX output shapes/classes before filtering overlapping boxes."""
    if width<=0 or height<=0:raise ValueError("Dimensioni immagine non valide")
    if not 0<=score_threshold<=1 or not 0<nms_iou<1:
        raise ValueError("Soglie del detector non valide")
    try:
        labels=np.asarray(raw["labels"]).reshape(-1)
        boxes=np.asarray(raw["boxes"])
        scores=np.asarray(raw["scores"]).reshape(-1)
    except (KeyError,TypeError,ValueError) as exc:
        raise ModelNotReady("Output ONNX non compatibile con il modello atteso") from exc
    if boxes.ndim==3 and boxes.shape[0]==1:boxes=boxes[0]
    if boxes.ndim!=2 or boxes.shape[1]!=4 or len(labels)!=len(boxes) or len(scores)!=len(boxes):
        raise ModelNotReady("Output detector: dimensioni non valide")
    detections=[]
    for cls,score,coords in zip(labels,scores,boxes):
        if int(cls) not in CLASS_NAMES or not np.isfinite(score) or float(score)<score_threshold:continue
        if not np.all(np.isfinite(coords)):continue
        x1,y1,x2,y2=map(float,coords)
        x1=int(round(np.clip(x1,0,width)));x2=int(round(np.clip(x2,0,width)))
        y1=int(round(np.clip(y1,0,height)));y2=int(round(np.clip(y2,0,height)))
        if x2-x1<4 or y2-y1<4:continue
        detections.append(Detection(int(cls),float(score),(x1,y1,x2,y2)))
    detections.sort(key=lambda d:(-d.score,d.cls,d.box))
    kept=[]
    for d in detections:
        if any(old.cls==d.cls and _iou_box(d.box,old.box)>nms_iou for old in kept):continue
        kept.append(d)
    return kept


def _rect_polygon(box):
    x1,y1,x2,y2=box
    return [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]


def _text_in_bubble(text:Detection,bubble:Detection):
    a=text.box;b=bubble.box
    area=max(1,(a[2]-a[0])*(a[3]-a[1]))
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    cx=(a[0]+a[2])/2;cy=(a[1]+a[3])/2
    return b[0]<=cx<=b[2] and b[1]<=cy<=b[3] and intersection/area>=.60


def make_region_proposals(detections:list[Detection],image_size:tuple[int,int],
                          image:Image.Image | None=None) -> list[dict]:
    """Attach text detections to enclosing bubbles; unmatched text stays distinct.

    Bounding boxes remain *approximate* polygons. No pixel-perfect mask is
    inferred by this function. Multiple texts in one container remain flagged.
    """
    w,h=image_size
    bubbles=[d for d in detections if d.cls==0]
    texts=[d for d in detections if d.cls==1]
    free=[d for d in detections if d.cls==2]
    grouped={i:[] for i in range(len(bubbles))}
    loose=[]
    for text in texts:
        containing=[(i,b) for i,b in enumerate(bubbles) if _text_in_bubble(text,b)]
        if containing:
            best_i,_=min(containing,key=lambda pair:(
                (pair[1].box[2]-pair[1].box[0])*(pair[1].box[3]-pair[1].box[1]),-pair[1].score))
            grouped[best_i].append(text)
        else:loose.append(text)
    candidates=[]
    for i,b in enumerate(bubbles):
        candidates.append(("dialogue",b,"balloon_box_approx",len(grouped[i]),grouped[i]))
    for t in loose:
        candidates.append(("dialogue",t,"unattached_text_box",1,[t]))
    for t in free:
        candidates.append(("art_text",t,"free_text_box",1,[t]))
    candidates.sort(key=lambda v:(v[1].box[1],v[1].box[0],-v[1].score))
    result=[]
    for i,(kind,item,geometry,text_count,members) in enumerate(candidates,1):
        box=item.box
        outline=None
        quality=None
        if image is not None and kind=='dialogue':
            text_box=None
            if geometry=='balloon_box_approx' and members:
                text_box=(min(d.box[0] for d in members),min(d.box[1] for d in members),
                          max(d.box[2] for d in members),max(d.box[3] for d in members))
            proposal=refine_light_surface(image,box,text_box=text_box)
            if proposal is not None:
                outline,quality=proposal
        poly=[[round(x/w,6),round(y/h,6)] for x,y in (outline if outline else _rect_polygon(box))]
        result.append({"id":f"ml{i:03}","kind":kind,"polygon":poly,
            "source":"ogkalu_rtdetr_v4s_onnx", "confidence":round(item.score,4),
            "geometry":"light_surface_candidate" if outline else "bounding_box_only",
            "contour_quality":quality,"role":geometry,
            "text_region_count":text_count,"needs_review":True})
    return result


class LearnedDetector:
    def __init__(self,model_path:str | Path,session=None,provider:str="CPUExecutionProvider"):
        path=Path(model_path)
        if session is None:
            if not verify_model_file(path):
                raise ModelNotReady("Modello assente o checksum non valido. Usa detector-fetch prima.")
            try:import onnxruntime as ort
            except ImportError as exc:
                raise ModelNotReady("Installa onnxruntime: pip install comictranslate-it[detector]") from exc
            available=ort.get_available_providers()
            if provider not in available:
                raise ModelNotReady(f"Provider ONNX non disponibile: {provider}; disponibili: {available}")
            session=ort.InferenceSession(str(path),providers=[provider])
        self.session=session
        self.provider=provider
        input_names={value.name for value in session.get_inputs()}
        output_names={value.name for value in session.get_outputs()}
        if not {"images","orig_target_sizes"}<=input_names or not {"labels","boxes","scores"}<=output_names:
            raise ModelNotReady("Il file ONNX non espone input/output RT-DETR attesi")

    def detections(self,image:Image.Image,threshold:float=.3,detail_pass:bool=False):
        feed=preprocess(image)
        names=["labels","boxes","scores"]
        raw=dict(zip(names,self.session.run(names,feed)))
        found=postprocess(raw,image.width,image.height,threshold)
        if detail_pass and min(image.size)>=900:
            # Full page plus four overlapping crops to improve small-caption
            # coverage. This is slower and results remain review-only.
            w,h=image.size
            tw=round(w*.64);th=round(h*.64)
            for y in (0,h-th):
                for x in (0,w-tw):
                    crop=image.crop((x,y,x+tw,y+th))
                    out=dict(zip(names,self.session.run(names,preprocess(crop))))
                    for det in postprocess(out,tw,th,threshold):
                        x1,y1,x2,y2=det.box
                        found.append(Detection(det.cls,det.score,
                                               (x1+x,y1+y,x2+x,y2+y)))
            found.sort(key=lambda d:(-d.score,d.cls,d.box))
            dedup=[]
            for det in found:
                if any(prev.cls==det.cls and _iou_box(det.box,prev.box)>.52 for prev in dedup):
                    continue
                dedup.append(det)
            found=dedup
        return found

    def proposals(self,image:Image.Image,threshold:float=.3,detail_pass:bool=False):
        return make_region_proposals(self.detections(image,threshold,detail_pass),image.size,image=image)
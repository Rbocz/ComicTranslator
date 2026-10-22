"""Private, resolution-independent human labels and measurable balloon recall.

Annotations hold geometry only: no page raster or copyrighted dialogue.
Predictions are ALWAYS proposals, not evidence of correct translation.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from PIL import Image
from .detection import find_balloons

KINDS = ('dialogue', 'caption', 'thought', 'sfx', 'art_text')
SCHEMA = 1


def normalize_polygon(points: list[list[float]], width: int, height: int) -> list[list[float]]:
    if width <= 0 or height <= 0:
        raise ValueError('Invalid image dimensions')
    return [[round(float(x) / width, 6), round(float(y) / height, 6)] for x,y in points]


def denormalize_polygon(points: list[list[float]], width: int, height: int) -> list[list[int]]:
    return [[int(round(x*width)), int(round(y*height))] for x,y in points]


def validate_shape(shape: dict):
    if shape.get('kind') not in KINDS:
        raise ValueError('Unknown text category')
    p=shape.get('polygon')
    if not isinstance(p,list) or not 3<=len(p)<=128:
        raise ValueError('Polygon requires 3-128 vertices')
    pts=np.asarray(p,dtype=np.float64)
    if pts.shape!=(len(p),2) or not np.all(np.isfinite(pts)):
        raise ValueError('Invalid polygon vertices')
    if np.min(pts)<0 or np.max(pts)>1:
        raise ValueError('Normalized polygon outside [0, 1]')
    if abs(cv2.contourArea(np.float32(pts)))<0.000004:
        raise ValueError('Polygon is degenerate')


def load_annotations(path: str | Path, archive_name: str | None = None):
    file=Path(path)
    if file.exists():
        result=json.loads(file.read_text(encoding='utf-8'))
        if result.get('schema')!=SCHEMA or not isinstance(result.get('pages'),dict):
            raise ValueError('Unsupported annotations file')
        if archive_name is not None and result.get('archive_name')!=archive_name:
            raise ValueError('Annotations refer to a different archive')
        for page in result['pages'].values():
            if not isinstance(page.get('regions'),list):raise ValueError('Invalid annotations page')
            for shape in page['regions']:validate_shape(shape)
        return result
    return {'schema':SCHEMA,'archive_name':archive_name or '', 'pages':{}}


def save_annotations(data: dict, path: str | Path):
    for page in data.get('pages',{}).values():
        for region in page.get('regions',[]):validate_shape(region)
    file=Path(path)
    file.parent.mkdir(parents=True,exist_ok=True)
    tmp=file.with_suffix(file.suffix+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    os.replace(tmp,file)


def proposal_regions(image: Image.Image, detector: str = 'baseline', model=None,
                     threshold: float = .3) -> list[dict]:
    """All backends return review-only shapes; learned ONNX requires an explicit model."""
    if detector == 'onnx':
        if model is None:
            raise ValueError('ONNX detector requires a loaded model')
        return model.proposals(image,threshold)
    if detector != 'baseline':
        raise ValueError(f'Unknown detector backend: {detector}')
    return [{'kind':'dialogue','polygon':normalize_polygon(p,image.width,image.height),
             'source':'bright-contour', 'id':f'd{i:03}'}
            for i,(_,p,_) in enumerate(find_balloons(image),1)]


def _iou_matrix(gt: list[dict], pred: list[dict], raster: int = 512) -> np.ndarray:
    """Raster masks at identical normalized resolution, including thin polygons."""
    if not gt or not pred:return np.zeros((len(gt),len(pred)),dtype=np.float64)
    def masks(regions):
        output=[]
        for r in regions:
            mask=np.zeros((raster,raster),np.uint8)
            points=np.asarray([[min(raster-1,round(x*(raster-1))),
                                min(raster-1,round(y*(raster-1)))]
                               for x,y in r['polygon']],dtype=np.int32)
            cv2.fillPoly(mask,[points],1)
            output.append(mask.astype(bool))
        return output
    a=masks(gt);b=masks(pred)
    values=np.zeros((len(gt),len(pred)),dtype=np.float64)
    for i,m in enumerate(a):
        for j,n in enumerate(b):
            common=np.count_nonzero(m&n)
            union=np.count_nonzero(m|n)
            values[i,j]=common/union if union else 0
    return values


def measure_regions(gt: list[dict],pred: list[dict],threshold:float=.5):
    """Maximum-cardinality 1:1 matching avoids counting a merged region twice.

    The stable tie-breaker favours larger IoU, but TP always means >= threshold.
    Class accuracy is separately reported; recall is geometry-first.
    """
    if not 0<threshold<=1:raise ValueError('IoU threshold must be within (0,1]')
    for region in gt+pred:validate_shape(region)
    iou=_iou_matrix(gt,pred)
    candidates=[sorted([j for j in range(len(pred)) if iou[i,j]>=threshold],
                       key=lambda j:(-iou[i,j],j)) for i in range(len(gt))]
    claimed={}
    def augment(i,seen):
        for j in candidates[i]:
            if j in seen:continue
            seen.add(j)
            if j not in claimed or augment(claimed[j],seen):
                claimed[j]=i
                return True
        return False
    for i in sorted(range(len(gt)),key=lambda k:(len(candidates[k]), k)):
        augment(i,set())
    pairs=[{'truth':i,'prediction':j,'iou':round(float(iou[i,j]),4),
            'kind_correct':gt[i]['kind']==pred[j]['kind']}
           for j,i in sorted(claimed.items(),key=lambda v:v[1])]
    tp=len(pairs);fp=len(pred)-tp;fn=len(gt)-tp
    classes={}
    matched_truth={r['truth'] for r in pairs}
    for kind in KINDS:
        truth_ids=[i for i,r in enumerate(gt) if r['kind']==kind]
        class_found=sum(i in matched_truth for i in truth_ids)
        class_correct=sum(r['kind_correct'] for r in pairs if gt[r['truth']]['kind']==kind)
        classes[kind]={'truth':len(truth_ids),'located':class_found,
                       'location_recall':round(class_found/len(truth_ids),4) if truth_ids else None,
                       'correctly_classified':class_correct}
    # Fused detection: same prediction covers >=50% of *each* of multiple GT
    # polygons. This catches a large merged box even when its IoU is low.
    def coverage(polygon,reference):
        # Fraction of ground-truth pixels covered by one proposed region.
        masks=[]
        for r in (polygon,reference):
            m=np.zeros((512,512),np.uint8)
            points=np.asarray([[round(x*511),round(y*511)] for x,y in r['polygon']],np.int32)
            cv2.fillPoly(m,[points],1);masks.append(m.astype(bool))
        return np.count_nonzero(masks[0]&masks[1])/max(1,np.count_nonzero(masks[1]))
    fused=[j for j,r in enumerate(pred)
           if sum(coverage(r,truth)>=.5 for truth in gt)>=2]
    return {'threshold':threshold,'truth_count':len(gt),'prediction_count':len(pred),
            'tp':tp,'fp':fp,'fn':fn,
            'precision':round(tp/(tp+fp),4) if tp+fp else None,
            'recall':round(tp/(tp+fn),4) if tp+fn else None,
            'f1':round(2*tp/(2*tp+fp+fn),4) if 2*tp+fp+fn else None,
            'mean_matched_iou':round(sum(p['iou'] for p in pairs)/tp,4) if tp else None,
            'kind_correct':sum(p['kind_correct'] for p in pairs),
            'classes':classes,'fusion_risk_prediction_indices':fused,
            'pairs':pairs,
            'missed_truth_indices':[i for i in range(len(gt)) if i not in matched_truth],
            'false_prediction_indices':[j for j in range(len(pred)) if j not in claimed]}


def benchmark_archive(archive_path: str,annotations: dict,only_pages: list[int]|None=None,
                      detector: str = 'baseline', model=None, threshold: float = .3):
    from .archives import Archive
    output=[]
    with Archive(archive_path) as archive:
        for key,page in sorted(annotations['pages'].items(),key=lambda item:int(item[0])):
            number=int(key)
            if only_pages and number not in only_pages:continue
            if not 1<=number<=len(archive.names):raise ValueError(f'Invalid page: {number}')
            if page.get('filename')!=archive.names[number-1]:
                raise ValueError(f'Page name mismatch: {number}')
            if page.get('verified') is not True:
                continue  # Draft geometries must never contaminate measured recall
            im=archive.image(archive.names[number-1])
            gt=page['regions']
            predictions=proposal_regions(im,detector,model,threshold)
            report=measure_regions(gt,predictions)
            output.append({'page':number,'entry':archive.names[number-1],**report})
    if not output:raise ValueError('No manually verified pages selected')
    TP=sum(r['tp'] for r in output);FP=sum(r['fp'] for r in output);FN=sum(r['fn'] for r in output)
    return {'schema':1,'pages':output,'overall':{'tp':TP,'fp':FP,'fn':FN,
            'precision':round(TP/(TP+FP),4) if TP+FP else None,
            'recall':round(TP/(TP+FN),4) if TP+FN else None,
            'f1':round(2*TP/(2*TP+FP+FN),4) if (2*TP+FP+FN) else None},
            'detector':detector,'status':'Measured against human annotation; samples are not automatically validated.',
            'warning':'Baseline only; proposed shapes are not verified translations.'}
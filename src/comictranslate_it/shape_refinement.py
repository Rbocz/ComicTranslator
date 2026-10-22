"""Conservative, review-only approximate contours for light comics balloons.

The ONNX detector supplies coarse boxes, not pixel masks. This optional
geometric refinement tries to find a light enclosed surface around detected
text. Ambiguous findings remain rectangles. NEVER use these polygons as text
erasure masks or as automatic human-verified annotations.
"""
from __future__ import annotations
import cv2
import numpy as np
from PIL import Image


def refine_light_surface(image: Image.Image, box: tuple[int, int, int, int],
                         *, text_box: tuple[int, int, int, int] | None = None):
    """Return (pixel_polygon, geometric_coverage) or None.

    Works best on bright outlined balloons; colored or art-overlapping speech
    balloons often cannot be refined safely and return None.
    """
    width,height=image.size
    x1,y1,x2,y2=map(int,box)
    if not (0<=x1<x2<=width and 0<=y1<y2<=height):
        return None
    tx1,ty1,tx2,ty2=text_box if text_box else box
    bw=x2-x1;bh=y2-y1
    extra_x=max(12,int(bw*.80),int(bh*.8))
    extra_y=max(12,int(bh*1.50),int(bw*.60))
    lx=max(0,x1-extra_x);top=max(0,y1-extra_y)
    rx=min(width,x2+extra_x);bottom=min(height,y2+extra_y)
    if (rx-lx)*(bottom-top)>3_000_000:
        return None
    arr=np.asarray(image.convert("RGB").crop((lx,top,rx,bottom)))
    h,w=arr.shape[:2]
    if w<25 or h<20:
        return None
    minimum=np.min(arr,axis=2)
    maximum=np.max(arr,axis=2)
    bright=(minimum>=170)&((maximum.astype(np.int16)-minimum)<=70)
    mask=np.uint8(bright)*255
    kernel=max(3,min(9,int(round(min(bw,bh)*.10))|1))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(kernel,kernel)))
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    if n<=1:
        return None
    tl=max(0,min(w,tx1-lx));tt=max(0,min(h,ty1-top))
    tr=max(0,min(w,tx2-lx));tb=max(0,min(h,ty2-top))
    if tr-tl<3 or tb-tt<3:
        return None
    text_area=(tr-tl)*(tb-tt)
    winner=None
    for label in range(1,n):
        x,y,ww,hh,area=map(int,stats[label])
        if area<max(60,text_area*.28) or area>min(w*h*.83,1_300_000):
            continue
        # Reject components joined to large page gutters or escaping crop.
        if x<=1 or y<=1 or x+ww>=w-1 or y+hh>=h-1:
            continue
        component=np.uint8(labels==label)*255
        contours,_=cv2.findContours(component,cv2.RETR_EXTERNAL,
                                     cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour=max(contours,key=cv2.contourArea)
        filled=np.zeros((h,w),dtype=np.uint8)
        cv2.drawContours(filled,[contour],-1,255,-1)
        covered=np.count_nonzero(filled[tt:tb,tl:tr])/text_area
        if covered<.67:
            continue
        ratio=(ww*hh)/max(1,text_area)
        if not .9<=ratio<=30:
            continue
        if cv2.contourArea(contour)/max(1,ww*hh)<.32:
            continue
        score=covered-.08*abs(np.log(max(.1,ratio)/2))
        if winner is None or score>winner[0]:
            winner=(score,contour,covered)
    if winner is None:
        return None
    _,contour,covered=winner
    perimeter=cv2.arcLength(contour,True)
    approximate=cv2.approxPolyDP(contour,max(1.5,perimeter*.006),
                                  True).reshape(-1,2)
    if not 3<=len(approx)<=96:
        return None
    polygon=[[int(x)+lx,int(y)+top] for x,y in approximate]
    return polygon,round(float(covered),3)

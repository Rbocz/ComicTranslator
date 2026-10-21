"""Deterministic shape-aware text placement. All glyph pixels must lie in the safe mask."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .models import Region


class LayoutError(ValueError):
    pass


@dataclass
class Layout:
    font_size: int
    lines: list[str]
    positions: list[tuple[float,float]]
    ink_mask: Image.Image


def get_font(size: int, font_path: str | None = None):
    candidates = [font_path] if font_path else []
    candidates += ["DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf",
                   "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/impact.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(str(candidate), size)
        except (OSError, ValueError):
            continue
    raise LayoutError("Font TrueType non trovato: specificare --font con un .ttf/.otf")


def balloon_mask(size: tuple[int,int], region: Region, margin: int | None = None) -> np.ndarray:
    w,h=size
    img=np.zeros((h,w),np.uint8)
    r=region.balloon.clamp(w,h)
    if not r.valid():
        raise LayoutError("Area balloon non valida")
    if region.shape == "polygon":
        if len(region.polygon)<3:
            raise LayoutError("Poligono non definito")
        points=np.asarray(region.polygon,dtype=np.int32)
        cv2.fillPoly(img,[points],255)
    elif region.shape == "ellipse":
        cv2.ellipse(img,((r.x1+r.x2)//2,(r.y1+r.y2)//2),
                    (max(1,r.width//2),max(1,r.height//2)),0,0,360,255,-1)
    else:
        cv2.rectangle(img,(r.x1,r.y1),(r.x2-1,r.y2-1),255,-1)
    margin = region.margin if margin is None else margin
    if margin > 0:
        kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*margin+1,2*margin+1))
        img=cv2.erode(img,kernel)
    return img


def _largest_interval(mask: np.ndarray, y1: int, y2: int):
    h,w=mask.shape
    if y1<0 or y2>h or y2<=y1:
        return None
    columns=np.all(mask[y1:y2]>0,axis=0)
    padded=np.concatenate(([False],columns,[False]))
    changes=np.flatnonzero(np.diff(padded.astype(np.int8)))
    if len(changes)<2:
        return None
    spans=list(zip(changes[::2],changes[1::2]))
    return max(spans,key=lambda p:p[1]-p[0])


def _best_breaks(words: list[str], caps: list[float], font, target_fill: float = .68):
    n=len(caps)
    @lru_cache(None)
    def fit(line: int, start: int):
        if line == n:
            return (0, []) if start == len(words) else None
        best = None
        remaining_lines=n-line
        last_index=len(words)-(remaining_lines-1)
        for stop in range(start+1,last_index+1):
            snippet=" ".join(words[start:stop])
            width=font.getlength(snippet)
            if width > caps[line]-1:
                break
            rest=fit(line+1,stop)
            if rest is None:
                continue
            ratio=width/caps[line]
            # Prefer centered/comparable line lengths. Strongly disfavor isolated short words.
            penalty=((ratio-target_fill)**2)*14 + (4 if stop-start==1 and len(words)>n else 0)
            if line == n-1 and ratio < .30:
                penalty+=5
            score=penalty+rest[0]
            if best is None or score < best[0]:
                best=(score,[snippet]+rest[1])
        return best
    result=fit(0,0)
    return result[1] if result else None


def layout_text(region: Region, size: tuple[int,int], font_path: str | None = None, target_fill: float = .68):
    """Return layout only when the exact final glyph alpha stays within safe polygon.

    Never scale glyphs horizontally or render outside the region to force a fit.
    """
    if not 0.45 <= target_fill <= 0.90:
        raise LayoutError("Profilo lettering fuori intervallo")
    if not region.italian.strip():
        raise LayoutError("Traduzione italiana assente")
    if region.font_size_min < 8 or region.font_size_max < region.font_size_min:
        raise LayoutError("Limiti di dimensione font non validi")
    w,h=size
    safe=balloon_mask(size,region)
    yy,xx=np.nonzero(safe)
    if not len(xx):
        raise LayoutError("Nessuna area di lettering sicura")
    bounds=(int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1))
    center_y=(bounds[1]+bounds[3])/2
    words=(region.italian.upper() if region.uppercase else region.italian).split()
    if not words:
        raise LayoutError("Traduzione italiana assente")
    for fontsize in range(region.font_size_max,region.font_size_min-1,-1):
        font=get_font(fontsize,font_path)
        ascent,descent=font.getmetrics()
        line_height=max(fontsize+2, int((ascent+descent)*1.04))
        maxlines=min(16,len(words),int((bounds[3]-bounds[1])/line_height))
        candidates=([region.preferred_lines] if 1 <= region.preferred_lines <= maxlines else [])
        candidates += [n for n in range(1,maxlines+1) if n not in candidates]
        for numlines in candidates:
            centers_y=[center_y+(i-(numlines-1)/2)*line_height for i in range(numlines)]
            intervals=[]
            for cy in centers_y:
                # Testing a band of glyph height is more reliable than testing the central row.
                half=max(4,int(fontsize*.48))
                interval=_largest_interval(safe,int(cy-half),int(cy+half)+1)
                if not interval:
                    intervals=[];break
                intervals.append(interval)
            if len(intervals)!=numlines:
                continue
            caps=[max(0,b-a-2) for a,b in intervals]
            lines=_best_breaks(words,caps,font,target_fill)
            if lines is None:
                continue
            ink=Image.new("L",(w,h),0)
            drawer=ImageDraw.Draw(ink)
            positions=[]
            for line,(a,b),cy in zip(lines,intervals,centers_y):
                cx=(a+b)/2
                drawer.text((cx,cy),line,font=font,fill=255,anchor="mm",stroke_width=0)
                positions.append((cx,cy))
            pix=np.asarray(ink)
            # Exact pixel-level safety invariant on rendered glyph coverage.
            if np.any((pix>0) & (safe==0)):
                continue
            return Layout(fontsize,lines,positions,ink)
    raise LayoutError("Testo non inseribile nell'area: abbreviare la traduzione o modificare il balloon")

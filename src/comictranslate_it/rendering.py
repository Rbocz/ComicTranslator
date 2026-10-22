"""Strict raster editing: mask-driven erasure, then shape-safe typesetting."""
from __future__ import annotations
from dataclasses import dataclass, field
from PIL import Image
import numpy as np
import cv2
from .models import Region
from .lettering import balloon_mask, layout_text, LayoutError


@dataclass
class RegionReport:
    id: str
    applied: bool
    message: str
    font_size: int | None = None
    method: str | None = None


def text_erasure_mask(rgb: np.ndarray, region: Region, safe: np.ndarray):
    """Mask only likely dark glyph pixels inside OCR word boxes and safe balloon.
    Regions without OCR boxes are never automatically erased.
    """
    h,w=rgb.shape[:2]
    mask=np.zeros((h,w),dtype=np.uint8)
    if not region.words:
        return mask
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    for word in region.words:
        b=word.clamp(w,h)
        if not b.valid():
            continue
        x1,y1,x2,y2=b.as_tuple()
        # include 2px antialiasing halo; the mask is still clipped to the safe zone.
        x1=max(0,x1-2);y1=max(0,y1-2);x2=min(w,x2+2);y2=min(h,y2+2)
        patch=gray[y1:y2,x1:x2]
        if patch.size==0:
            continue
        # Threshold is only appropriate for light balloon areas.
        local_dark=np.uint8(patch < 242)*255
        mask[y1:y2,x1:x2]=np.maximum(mask[y1:y2,x1:x2],local_dark)
    if np.any(mask):
        mask=cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    mask[safe == 0]=0
    return mask


def erase_text(rgb: np.ndarray, region: Region, safe: np.ndarray):
    mask=text_erasure_mask(rgb,region,safe)
    if cv2.countNonZero(mask)==0:
        raise ValueError("Maschera OCR vuota: definire le parole originali prima della pulizia")
    # Determine if the surrounding balloon is essentially uniform light color.
    context=(safe>0)&(mask==0)
    pixels=rgb[context]
    light=pixels[np.min(pixels,axis=1)>220] if len(pixels) else np.empty((0,3))
    if len(light)>100 and len(light)>len(pixels)*0.4 and float(np.max(np.std(light,axis=0))) < 8:
        color=np.median(light,axis=0).astype(np.uint8)
        output=rgb.copy()
        output[mask>0]=color
        return output,mask,"flat-color"
    # The simple OpenCV fallback is deliberately limited to the user-approved mask.
    # Complex artwork should be reviewed; a learned inpainter can replace this adapter.
    inpainted=cv2.inpaint(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),mask,3,cv2.INPAINT_TELEA)
    output=rgb.copy()
    output[mask>0]=cv2.cvtColor(inpainted,cv2.COLOR_BGR2RGB)[mask>0]
    return output,mask,"opencv-inpaint"


def render_page(image: Image.Image, regions: list[Region], font_path: str | None=None,
                approval_required: bool=True, target_fill: float=.68):
    """Preserve image where no approved mask/glyph ink overlaps.

    Failed regions are skipped entirely; the original never gets a partial erase.
    """
    current=np.array(image.convert("RGB"),dtype=np.uint8)
    reports=[]
    occupied=np.zeros(current.shape[:2],dtype=bool)
    for region in regions:
        if approval_required and not region.approved:
            reports.append(RegionReport(region.id,False,"Da approvare: originale conservato"))
            continue
        if not region.italian.strip():
            reports.append(RegionReport(region.id,False,"Nessuna traduzione: originale conservato"))
            continue
        if not region.words:
            reports.append(RegionReport(region.id,False,"Coordinate testo originale mancanti"))
            continue
        try:
            safe=balloon_mask((image.width,image.height),region)
            if region.source.startswith('vision-api'):
                # Vision models provide approximate rectangles, not verified masks.
                # Fail closed on art/color-rich backgrounds rather than erasing art.
                bx=region.balloon.clamp(image.width,image.height)
                crop=current[bx.y1:bx.y2,bx.x1:bx.x2]
                valid=safe[bx.y1:bx.y2,bx.x1:bx.x2].astype(bool)
                sample=valid.copy()
                for word in region.words:
                    r=word.clamp(image.width,image.height)
                    sample[max(0,r.y1-bx.y1):max(0,r.y2-bx.y1),
                           max(0,r.x1-bx.x1):max(0,r.x2-bx.x1)]=False
                light=(crop.min(axis=2)>222)
                if sample.sum()<150 or float(np.mean(light[sample]))<.79:
                    raise ValueError('Balloon/sfondo non uniforme: revisione necessaria')
                for word in region.words:
                    r=word.clamp(image.width,image.height)
                    patch=current[r.y1:r.y2,r.x1:r.x2]
                    if patch.size and float(np.mean(patch.min(axis=2)<90))>.55:
                        raise ValueError('Testo troppo vicino a bordi/disegni: revisione necessaria')
            layout=layout_text(region,(image.width,image.height),font_path,target_fill)
            erased,erase_mask,method=erase_text(current,region,safe)
            alpha=np.asarray(layout.ink_mask,dtype=np.uint8)
            if np.any((alpha>0) & (safe==0)):
                raise ValueError("Lettering fuori area consentita")
            # Exact region safety: both alterations are masked by allowed zone.
            # Pillow anti-aliased glyph alpha preserves smooth font edges.
            opacity=alpha.astype(np.float32)[:,:,None]/255.0
            erased=np.uint8(np.round(erased*(1.0-opacity)+18.0*opacity))
            changes=np.any(erased!=current,axis=2)
            if np.any(changes & (safe==0)):
                raise ValueError("Modifica fuori balloon: operazione annullata")
            if np.any(changes & occupied):
                raise ValueError("Conflitto tra regioni: modifica annullata")
            occupied |= changes
            current=erased
            reports.append(RegionReport(region.id,True,"OK",layout.font_size,method))
        except (ValueError,LayoutError,TypeError) as exc:
            reports.append(RegionReport(region.id,False,f"Bloccato: {exc}"))
    return Image.fromarray(current,"RGB"),reports
"""End-to-end, resumable comic vision translation with user-provided cloud API.

No image or API key is transmitted without user confirmation in the caller.
Model geometry is an estimate; export preserves original art when unsafe.
"""
from __future__ import annotations
import base64
import io
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Callable

from PIL import Image, ImageOps
from .archives import Archive
from .models import Rect, Region
from .project import Project
from .pipeline import export

DEFAULT_MODELS={'Google Gemini':'gemini-2.5-flash','OpenAI':'gpt-4.1-mini'}

class ServiceError(RuntimeError):
    pass

PROMPT='''You are a senior English-to-Italian comics letterer, OCR and visual layout expert.
Analyze the supplied comic page image carefully in natural reading order (Western comics: panels left-to-right, top-to-bottom), including small captions and speech balloons.
For every English dialogue or narrative text container, return ONE object with:
- original: verbatim complete English text, retaining punctuation.
- italian: natural, faithful Italian translation concise enough for the same space, not an explanation.
- container_box: [left,top,right,bottom] bounds of the FULL WHITE/LIGHT SPEECH BALLOON OR CAPTION BOX, NOT just glyphs.
- line_boxes: list of tight rectangles for each original printed TEXT LINE only. These are for cautious ink removal; do not include border or artwork.
- kind: dialogue or caption. Do not include comic sound effects, logos, street signs, or decorative lettering in normal translation regions.
- uppercase: true if the source speech should be lettered in uppercase.
- certainty: integer 0..100 indicating your certainty in OCR AND boxes.
All box coordinates MUST be integers in the 0..1000 coordinate system of the IMAGE RECEIVED, including both axes.
If the bubble crosses a panel frame, keep the container bounds within the bubble; avoid tails when possible.
Prefer many precise line_boxes over one rectangle covering borders. Never invent words or boxes.
If a text is unreadable or lies on busy art rather than a light container, omit it; it will be listed as needing review.
Return valid JSON ONLY: {"regions":[{"original":"...","italian":"...","container_box":[...],"line_boxes":[[...]],"kind":"dialogue","uppercase":true,"certainty":90}]}.
Previous translated context (for terminology, not to copy): CONTEXT_PLACEHOLDER'''


def _image_jpeg(image: Image.Image, max_edge:int=1900) -> str:
    im=ImageOps.exif_transpose(image).convert('RGB')
    if max(im.size)>max_edge:
        im.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
    buf=io.BytesIO()
    im.save(buf,format='JPEG',quality=88,optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def _http_json(url,payload,headers,timeout=120):
    body=json.dumps(payload,ensure_ascii=False).encode('utf8')
    req=Request(url,data=body,headers={'Content-Type':'application/json',**headers},method='POST')
    try:
        with urlopen(req,timeout=timeout) as result:
            return json.load(result)
    except HTTPError as err:
        # Avoid accidental key disclosure in exception bodies.
        data=err.read(1200).decode('utf8','replace')
        raise ServiceError(f'API HTTP {err.code}: {data[:550]}') from None
    except (URLError,TimeoutError,OSError) as err:
        raise ServiceError(f'Connessione API non riuscita: {type(err).__name__}: {err}') from err


def _parse_response(text):
    if not isinstance(text,str):raise ServiceError('L’API non ha restituito testo')
    text=text.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$', '',text,flags=re.I).strip()
    try:
        value=json.loads(text)
    except json.JSONDecodeError as err:
        raise ServiceError(f'Risposta API non è JSON valido: {str(err)}') from err
    if not isinstance(value,dict) or not isinstance(value.get('regions'),list):
        raise ServiceError('La risposta API non contiene un elenco regions')
    if len(value['regions'])>100:raise ServiceError('Numero anomalo di regioni: pagina da rivedere')
    return value['regions']


def recognize_translate(image:Image.Image,provider:str,api_key:str,model:str,
                        context:str='',http_client:Callable|None=None) -> list[dict]:
    if provider not in DEFAULT_MODELS:raise ValueError('Provider non valido')
    if not api_key.strip():raise ServiceError('Inserisci la chiave API')
    if not model.strip() or not re.fullmatch(r'[\w.\-]+',model):raise ValueError('Nome modello non valido')
    prompt=PROMPT.replace('CONTEXT_PLACEHOLDER',context[-1800:])
    encoded=_image_jpeg(image)
    client=http_client or _http_json
    if provider=='Google Gemini':
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        payload={'contents':[{'role':'user','parts':[{'text':prompt},{'inline_data':{'mime_type':'image/jpeg','data':encoded}}]}],
                 'generationConfig':{'responseMimeType':'application/json','temperature':0.15,'maxOutputTokens':8192}}
        response=client(url,payload,{'x-goog-api-key':api_key.strip()})
        try:
            parts=response['candidates'][0]['content']['parts']
            out=''.join(p.get('text','') for p in parts)
        except (KeyError,IndexError,TypeError) as err:raise ServiceError('Gemini: risposta non valida o bloccata') from err
    else:
        payload={'model':model,'temperature':0.15,'response_format':{'type':'json_object'},'max_completion_tokens':8192,
                 'messages':[{'role':'system','content':'Reply ONLY valid JSON. No markdown.'},
                             {'role':'user','content':[{'type':'text','text':prompt},
                               {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+encoded,'detail':'high'}}]}]}
        response=client('https://api.openai.com/v1/chat/completions',payload,
                        {'Authorization':'Bearer '+api_key.strip()})
        try:out=response['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError) as err:raise ServiceError('OpenAI: risposta non valida') from err
    return _parse_response(out)


def _box(raw,w:int,h:int):
    if not isinstance(raw,(list,tuple)) or len(raw)!=4:return None
    if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in raw):return None
    x1,y1,x2,y2=map(float,raw)
    # Reject invalid model coordinates instead of clipping wildly incorrect output.
    if not (0<=x1<x2<=1000 and 0<=y1<y2<=1000):return None
    rect=Rect(round(x1*w/1000),round(y1*h/1000),round(x2*w/1000),round(y2*h/1000)).clamp(w,h)
    return rect if rect.valid() and rect.width>=8 and rect.height>=8 else None


def regions_from_response(items:list[dict],size:tuple[int,int],prefix:str='vision'):
    """Reject dubious coordinates and never approve unsupported/busy-art regions.

    Distinguish *automatic draft* from human-validated ground truth.
    """
    w,h=size
    output=[]
    for item in items:
        if not isinstance(item,dict):continue
        original=item.get('original','')
        italian=item.get('italian','')
        if not isinstance(original,str) or not isinstance(italian,str):continue
        original=original.strip();italian=italian.strip()
        if not original or not italian or len(original)>1200 or len(italian)>1600:continue
        balloon=_box(item.get('container_box'),w,h)
        if balloon is None:continue
        raw=item.get('line_boxes',[])
        if not isinstance(raw,list):continue
        line_boxes=[r for v in raw if (r:=_box(v,w,h)) is not None]
        # Each line box must be inside the intended light container with clearance from edges.
        inset=max(2,round(min(balloon.width,balloon.height)*.04))
        words=[r for r in line_boxes if r.x1>=balloon.x1+inset and r.y1>=balloon.y1+inset
               and r.x2<=balloon.x2-inset and r.y2<=balloon.y2-inset]
        if len(words)>24:words=[]
        try:certainty=float(item.get('certainty',0))
        except (TypeError,ValueError):certainty=0
        certainty=max(0,min(100,certainty))/100
        kind=item.get('kind')
        if kind not in ('dialogue','caption'):continue
        auto_safe=(certainty>=.70 and len(words)>=1 and
                   balloon.width>=48 and balloon.height>=28 and
                   all(r.width*r.height < balloon.width*balloon.height*.55 for r in words))
        margin=max(4,min(18,round(min(balloon.width,balloon.height)*.07)))
        output.append(Region(id=f'{prefix}{len(output)+1:03}',balloon=balloon,words=words,
                             original=original,italian=italian,kind=kind,
                             shape='rect',detected=True,approved=auto_safe,
                             confidence=certainty,source='vision-api-unverified',
                             uppercase=bool(item.get('uppercase',False)),
                             preferred_lines=min(10,max(0,len(words))),
                             font_size_max=min(46,max(18,round(balloon.height*.38))),
                             font_size_min=9,margin=margin,
                             notes='BOZZA AUTOMATICA: geometria e traduzione da revisionare'))
    # Drop near-duplicates from overlapping crops, higher confidence first.
    output.sort(key=lambda r:-r.confidence)
    unique=[]
    for item in output:
        r=item.balloon
        if any(_iou_rect(r,prev.balloon)>.43 for prev in unique):continue
        unique.append(item)
    unique.sort(key=lambda r:(r.balloon.y1,r.balloon.x1))
    for i,item in enumerate(unique,1):item.id=f'{prefix}{i:03}'
    return unique


def _iou_rect(a:Rect,b:Rect):
    area=max(0,min(a.x2,b.x2)-max(a.x1,b.x1))*max(0,min(a.y2,b.y2)-max(a.y1,b.y1))
    return area/max(1,a.width*a.height+b.width*b.height-area)


def _views(image:Image.Image,accurate:bool):
    w,h=image.size
    yield image,(0,0,w,h)
    if accurate and h>=1100 and h>1.3*w:
        # Overlapping halves to recover tiny caption OCR not legible full-page.
        height=round(h*.6)
        for y in [0,h-height]:yield image.crop((0,y,w,y+height)),(0,y,w,y+height)


def analyze_page(image,provider,api_key,model,context='',accurate=True,http_client=None):
    all_regions=[]
    for view,area in _views(image,accurate):
        raw=recognize_translate(view,provider,api_key,model,context,http_client)
        x,y,x2,y2=area
        mapped=[]
        for item in raw:
            if not isinstance(item,dict):continue
            clone=dict(item)
            for key in ('container_box',):
                box=clone.get(key)
                if isinstance(box,list) and len(box)==4:
                    clone[key]=[round((x+box[0]*(x2-x)/1000)/image.width*1000),
                                round((y+box[1]*(y2-y)/1000)/image.height*1000),
                                round((x+box[2]*(x2-x)/1000)/image.width*1000),
                                round((y+box[3]*(y2-y)/1000)/image.height*1000)]
            lines=[]
            for box in clone.get('line_boxes',[]):
                if not isinstance(box,list) or len(box)!=4:continue
                lines.append([round((x+box[0]*(x2-x)/1000)/image.width*1000),
                              round((y+box[1]*(y2-y)/1000)/image.height*1000),
                              round((x+box[2]*(x2-x)/1000)/image.width*1000),
                              round((y+box[3]*(y2-y)/1000)/image.height*1000)])
            clone['line_boxes']=lines
            mapped.append(clone)
        all_regions.extend(mapped)
    return regions_from_response(all_regions,image.size)


@dataclass
class JobStatus:
    pages_done:int=0
    pages_total:int=0
    regions:int=0
    last_page:int=0
    failed:int=0


def translate_chapter(source:str,project_path:str,provider:str,api_key:str,
                      model:str,first:int=1,last:int|None=None,accurate:bool=True,
                      notify:Callable|None=None,stop:Callable|None=None,
                      http_client=None):
    """Page-by-page checkpoint. Skip pages with prior valid regions on resume.

    A failed call leaves the original page unchanged and is recorded in .errors.json.
    """
    if not Path(source).is_file():raise FileNotFoundError(source)
    if Path(project_path).exists():
        project=Project.load(project_path)
        if Path(project.source).resolve()!=Path(source).resolve():raise ValueError('Progetto associato a un altro CBR')
    else:project=Project.create(source,project_path)
    count=len(project.pages)
    last=count if last is None else last
    if not 1<=first<=last<=count:raise ValueError(f'Intervallo pagine 1–{count} non valido')
    status=JobStatus(pages_total=last-first+1)
    history=[];errors={}
    with Archive(source) as archive:
        for number in range(first,last+1):
            if stop and stop():break
            page=project.pages[number-1]
            if page.regions:
                status.pages_done+=1;status.regions+=len(page.regions)
                if notify:notify(status,f'Pagina {number} già elaborata: ripresa senza nuova chiamata API')
                history.extend(r.italian for r in page.regions if r.italian)
                history=history[-9:]
                continue
            try:
                image=archive.image(page.filename)
                found=analyze_page(image,provider,api_key,model,' | '.join(history[-7:]),accurate,http_client)
                page.regions=found
                project.save()  # Write only after entire page has completed successfully.
                history.extend(r.italian for r in found)
                history=history[-9:]
                status.regions+=len(found)
                if not found:errors[str(number)]='Nessun testo rilevato: verifica questa pagina'
            except (ServiceError,ValueError,OSError) as err:
                errors[str(number)]=str(err)
                status.failed+=1
                if notify:notify(status,f'Pagina {number}: {err}')
                # Stop on billing/rate-limit errors; do not retry 45 paid requests.
                if '429' in str(err) or '401' in str(err) or '403' in str(err) or 'quota' in str(err).lower():
                    status.pages_done+=1
                    status.last_page=number
                    if notify:notify(status,f'Interrotto sulla pagina {number} per errore API: {err}')
                    break
            status.pages_done+=1;status.last_page=number
            if notify:notify(status,f'Pagina {number}/{last}: {len(page.regions)} blocchi tradotti')
    errorpath=Path(project_path).with_suffix('.errors.json')
    errorpath.write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    return project,status,errors


def export_chapter(project:Project,destination:str):
    return export(project,destination)
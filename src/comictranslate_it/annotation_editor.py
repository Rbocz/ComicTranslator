"""Simple local human ground-truth annotation editor. No cloud or OCR required.

Label text *containers* only (balloons/captions/SFX), not copyrighted dialogue.
Regions use normalized coordinates, so translation edition sizes may differ.
"""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import ImageTk
from .archives import Archive
from .annotations import (KINDS,load_annotations,save_annotations,normalize_polygon,
                          denormalize_polygon,validate_shape,proposal_regions)


COLORS={'dialogue':'#00e5ff','caption':'#ffe14a','thought':'#c084fc',
        'sfx':'#ff628a','art_text':'#81ed8b'}


class AnnotationEditor:
    def __init__(self, archive_path: str, output_path: str, first_page:int=1,
                 detector: str = "baseline", model_file: str | None = None, threshold: float = .3):
        self.archive_path=Path(archive_path).resolve()
        self.out_path=Path(output_path).resolve()
        with Archive(self.archive_path) as archive:
            self.names=list(archive.names)
        if not 1<=first_page<=len(self.names):raise ValueError('Page out of range')
        self.data=load_annotations(self.out_path,self.archive_path.name)
        self.detector_backend=detector
        self.threshold=threshold
        self.model=None
        if detector=='onnx':
            from .learned_detection import LearnedDetector
            if not model_file:raise ValueError('ONNX detector requires --model-file')
            self.model=LearnedDetector(model_file)
        self.page_index=first_page-1
        self.region_index=None
        self.pending=[]
        self.start=None
        self.root=tk.Tk()
        self.kind=tk.StringVar(master=self.root, value='dialogue')
        self.draw_mode=tk.StringVar(master=self.root, value='polygon')
        self.show_proposals=tk.BooleanVar(master=self.root, value=True)
        self.verified=tk.BooleanVar(master=self.root, value=False)
        self.root.title('ComicTranslate IT — Annotazioni ground truth')
        self.root.geometry('1320x900')
        try:
            self._build()
            self._open_page()
        except Exception:
            self.root.destroy()
            raise

    def _build(self):
        top=ttk.Frame(self.root,padding=7);top.pack(fill='x')
        ttk.Button(top,text='◀',command=lambda:self._move(-1)).pack(side='left')
        self.current=tk.StringVar(master=self.root, value='')
        ttk.Label(top,textvariable=self.current,width=42,anchor='center').pack(side='left')
        ttk.Button(top,text='▶',command=lambda:self._move(1)).pack(side='left')
        ttk.Label(top,text='Vai alla pagina:').pack(side='left',padx=(12,3))
        self.goto=tk.StringVar(master=self.root, value=str(self.page_index+1))
        ttk.Entry(top,textvariable=self.goto,width=6).pack(side='left')
        ttk.Button(top,text='Vai',command=self._jump).pack(side='left')
        ttk.Button(top,text='Salva (Ctrl+S)',command=self._save).pack(side='right')
        body=ttk.PanedWindow(self.root,orient='horizontal');body.pack(fill='both',expand=True)
        left=ttk.Frame(body);body.add(left,weight=4)
        right=ttk.Frame(body,padding=9);body.add(right,weight=1)
        tools=ttk.Frame(left,padding=5);tools.pack(fill='x')
        for text,value in [('Poligono (clic + Enter)','polygon'),('Rettangolo (trascina)','box')]:
            ttk.Radiobutton(tools,text=text,variable=self.draw_mode,value=value,
                            command=self._discard_pending).pack(side='left',padx=4)
        ttk.Checkbutton(tools,text='Mostra proposte automatiche',variable=self.show_proposals,
                        command=self._redraw).pack(side='left',padx=14)
        self.canvas=tk.Canvas(left,bg='#202020',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self._down)
        self.canvas.bind('<B1-Motion>',self._drag)
        self.canvas.bind('<ButtonRelease-1>',self._up)
        self.canvas.bind('<Double-Button-1>',lambda e:self._finish_polygon())
        self.canvas.bind('<Button-3>',lambda e:self._finish_polygon())
        self.canvas.bind('<Configure>',lambda e:self._redraw())
        ttk.Label(right,text='Etichetta',font=('Segoe UI',11,'bold')).pack(anchor='w')
        for kind,title in [('dialogue','Dialogo'),('caption','Didascalia'),('thought','Pensiero'),
                           ('sfx','Onomatopea'),('art_text','Testo nel disegno')]:
            ttk.Radiobutton(right,text=title,variable=self.kind,value=kind).pack(anchor='w')
        ttk.Label(right,text='Regioni verificate',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(16,2))
        self.list=tk.Listbox(right,height=16,exportselection=False)
        self.list.pack(fill='x')
        self.list.bind('<<ListboxSelect>>',self._selected)
        ttk.Button(right,text='Elimina regione',command=self._delete).pack(fill='x',pady=(7,0))
        ttk.Button(right,text='Correggi la categoria selezionata',command=self._relabel).pack(fill='x',pady=5)
        ttk.Button(right,text='Annulla ultimo vertice (Backspace)',command=self._undo).pack(fill='x')
        ttk.Checkbutton(right,text='Pagina interamente controllata (completa)',
                        variable=self.verified,command=self._mark_verified).pack(anchor='w',pady=(13,4))
        ttk.Label(right,text='Le linee tratteggiate sono SOLO suggerimenti: azzurro=balloon/testo, arancio=testo esterno. Il modello ONNX fornisce rettangoli approssimativi, NON contorni precisi. Annota ogni balloon manualmente prima di confermare la pagina.',wraplength=310,justify='left').pack(anchor='w',pady=(22,0))
        self.status=tk.StringVar(master=self.root, value='')
        ttk.Label(self.root,textvariable=self.status,padding=7,anchor='w').pack(fill='x')
        self.root.bind('<Control-s>',lambda e:self._save())
        self.root.bind('<Return>',lambda e:self._finish_polygon())
        self.root.bind('<BackSpace>',lambda e:self._undo())
        self.root.protocol('WM_DELETE_WINDOW',self._close)

    def _page(self):
        key=str(self.page_index+1)
        if key not in self.data['pages']:
            self.data['pages'][key]={'filename':self.names[self.page_index],
                'width':self.image.width,'height':self.image.height,'regions':[], 'verified':False}
        page=self.data['pages'][key]
        if page.get('filename')!=self.names[self.page_index]:
            raise ValueError('Source archive page changed: annotation mismatch')
        return page

    def _open_page(self):
        with Archive(self.archive_path) as archive:
            self.image=archive.image(self.names[self.page_index])
        self.suggestions=proposal_regions(self.image,self.detector_backend,self.model,self.threshold)
        self._page()
        self.verified.set(self._page().get('verified',False))
        self.current.set(f'Pagina {self.page_index+1}/{len(self.names)} — {self.names[self.page_index][-26:]}')
        self.goto.set(str(self.page_index+1))
        self.region_index=None;self.pending=[]
        self._refresh();self._redraw()

    def _refresh(self):
        self.list.delete(0,'end')
        for i,r in enumerate(self._page()['regions']):
            self.list.insert('end',f'{i+1:02}  {r["kind"]}  ({len(r["polygon"])} punti)')
        if self.region_index is not None and self.region_index<self.list.size():
            self.list.selection_set(self.region_index)
        status = 'REVISIONATA' if self._page().get('verified') else 'BOZZA'
        self.status.set(f'{len(self._page()["regions"])} regioni umane · {len(self.suggestions)} proposte · {status}')

    def _redraw(self):
        if not hasattr(self,'image') or not self.canvas.winfo_exists():return
        cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        self.scale=min(cw/self.image.width,ch/self.image.height,1.8)
        w=max(1,round(self.image.width*self.scale));h=max(1,round(self.image.height*self.scale))
        self.off=((cw-w)//2,(ch-h)//2)
        thumb=self.image.resize((w,h))
        self.photo=ImageTk.PhotoImage(thumb, master=self.canvas)
        canvas=self.canvas
        canvas.delete('all')
        canvas.create_image(*self.off,image=self.photo,anchor='nw')
        if self.show_proposals.get():
            for r in self.suggestions:
                coords=self._canvas_coords(r['polygon'])
                color='#ffad66' if r['kind']=='art_text' else '#76d7ff'
                canvas.create_polygon(*coords,outline=color,fill='',dash=(5,4),width=2)
                if r.get('source')=='ogkalu_rtdetr_v4s_onnx':
                    canvas.create_text(coords[0]+4,coords[1]+4,anchor='nw',
                        text=f"{r['role']} {r['confidence']:.2f}",fill=color,
                        font=('Arial',8,'bold'))
        for i,r in enumerate(self._page()['regions']):
            coords=self._canvas_coords(r['polygon'])
            canvas.create_polygon(*coords,fill='',outline=COLORS[r['kind']],
                                  width=4 if i==self.region_index else 2)
        if self.pending:
            coords=self._canvas_coords(normalize_polygon(self.pending,self.image.width,self.image.height))
            if len(coords)>=4:canvas.create_line(*coords,fill='#00ff8f',width=3)
            for x,y in zip(coords[::2],coords[1::2]):
                canvas.create_oval(x-4,y-4,x+4,y+4,fill='#00ff8f',outline='')
        if self.start and self.drag_end:
            a=self._to_canvas(*self.start);b=self._to_canvas(*self.drag_end)
            canvas.create_rectangle(*a,*b,outline='#00ff8f',width=3)

    def _canvas_coords(self,p):
        coords=[]
        for x,y in p:
            coords.extend([self.off[0]+x*self.image.width*self.scale,
                           self.off[1]+y*self.image.height*self.scale])
        return coords

    def _to_canvas(self,x,y):return (self.off[0]+x*self.scale,self.off[1]+y*self.scale)

    def _to_image(self,event):
        return (min(self.image.width,max(0,(event.x-self.off[0])/self.scale)),
                min(self.image.height,max(0,(event.y-self.off[1])/self.scale)))

    def _down(self,event):
        if self.draw_mode.get()=='polygon':
            self.pending.append(list(self._to_image(event)));self._redraw()
        else:
            self.start=self._to_image(event);self.drag_end=self.start

    def _drag(self,event):
        if self.start:
            self.drag_end=self._to_image(event);self._redraw()

    def _up(self,event):
        if not self.start:return
        x,y=self.start;endx,endy=self._to_image(event)
        self.start=None;self.drag_end=None
        if abs(endx-x)<5 or abs(endy-y)<5:return
        self._add_shape([[min(x,endx),min(y,endy)],[max(x,endx),min(y,endy)],
                         [max(x,endx),max(y,endy)],[min(x,endx),max(y,endy)]])

    def _add_shape(self,points):
        region={'id':f'gt{len(self._page()["regions"])+1:03}',
                'kind':self.kind.get(),
                'polygon':normalize_polygon(points,self.image.width,self.image.height)}
        try:validate_shape(region)
        except ValueError as exc:messagebox.showwarning('Regione non valida',str(exc));return
        self._page()['regions'].append(region)
        self._invalidate_review()
        self.pending=[]
        self._refresh();self._redraw()

    def _finish_polygon(self):
        if self.draw_mode.get()!='polygon' or not self.pending:return
        if len(self.pending)<3:
            self.status.set('Servono almeno tre vertici per completare il poligono')
            return
        points=self.pending[:]
        self.pending=[]
        self._add_shape(points)

    def _undo(self):
        if self.pending:self.pending.pop();self._redraw()

    def _discard_pending(self):
        self.pending=[];self.start=None;self.drag_end=None;self._redraw()

    def _selected(self,event=None):
        indices=self.list.curselection()
        self.region_index=int(indices[0]) if indices else None
        if self.region_index is not None:
            self.kind.set(self._page()['regions'][self.region_index]['kind'])
        self._redraw()

    def _delete(self):
        if self.region_index is None:return
        self._page()['regions'].pop(self.region_index)
        self._invalidate_review()
        self.region_index=None;self._refresh();self._redraw()

    def _relabel(self):
        if self.region_index is None:return
        self._page()['regions'][self.region_index]['kind']=self.kind.get()
        self._invalidate_review()
        self._refresh();self._redraw()

    def _mark_verified(self):
        self._page()['verified']=bool(self.verified.get())
        self._refresh()

    def _invalidate_review(self):
        self._page()['verified']=False
        self.verified.set(False)

    def _save(self):
        try:
            # Do not count unannotated pages as verified negatives.
            records={k:v for k,v in self.data['pages'].items() if v.get('regions') or v.get('verified')}
            saved={**self.data,'pages':records}
            save_annotations(saved,self.out_path)
            self.status.set(f'Salvato: {self.out_path} · {len(records)} pagine annotate')
        except Exception as exc:messagebox.showerror('Salvataggio fallito',str(exc))

    def _move(self,delta):
        destination=self.page_index+delta
        if not 0<=destination<len(self.names):return
        self._save();self.page_index=destination;self._open_page()

    def _jump(self):
        try:target=int(self.goto.get())-1
        except ValueError:return
        self._move(target-self.page_index)

    def _close(self):
        self._save();self.root.destroy()

    drag_end=None

    def run(self):self.root.mainloop()


def launch(archive_path:str, output_path:str, page:int=1,
           detector:str="baseline",model_file:str|None=None,threshold:float=.3):
    AnnotationEditor(archive_path,output_path,page,detector,model_file,threshold).run()
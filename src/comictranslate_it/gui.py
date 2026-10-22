"""Small dependency-light desktop review editor (Tkinter + Pillow).

No automatic operation here promotes a model suggestion to human approval.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import ImageTk, ImageDraw
from .archives import Archive
from .project import Project
from .models import Region,Rect
from .detection import scan_page
from .rendering import render_page
from .pipeline import export


class Editor:
    def __init__(self, project_path: str):
        self.project=Project.load(project_path)
        self.root=tk.Tk()
        self.root.title("ComicTranslate IT • Revisione professionale (v0.1)")
        self.root.geometry("1210x870")
        self.page_idx=0
        self.region_idx=None
        self.preview=False
        self.drag_start=None
        self.tool=tk.StringVar(value="seleziona")
        self.shape=tk.StringVar(value="rect")
        self.approved=tk.BooleanVar()
        self._updating=False
        self._scale=1.0
        self._offset=(0,0)
        self._build()
        self._show_page()

    def _build(self):
        root=self.root
        bar=ttk.Frame(root,padding=7);bar.pack(fill="x")
        ttk.Button(bar,text="◀ Pagina",command=lambda:self._navigate(-1)).pack(side="left")
        self.number=ttk.Label(bar,text="",width=23,anchor="center");self.number.pack(side="left")
        ttk.Button(bar,text="Pagina ▶",command=lambda:self._navigate(1)).pack(side="left")
        ttk.Button(bar,text="Rileva OCR",command=self._scan_current).pack(side="left",padx=10)
        ttk.Button(bar,text="Originale / anteprima",command=self._preview).pack(side="left")
        ttk.Button(bar,text="Salva progetto",command=self._save).pack(side="right")
        ttk.Button(bar,text="Esporta CBZ",command=self._export).pack(side="right",padx=7)

        center=ttk.PanedWindow(root,orient="horizontal");center.pack(fill="both",expand=True)
        visual=ttk.Frame(center);center.add(visual,weight=4)
        controls=ttk.Frame(center,padding=10);center.add(controls,weight=2)
        toolbox=ttk.Frame(visual,padding=5);toolbox.pack(fill="x")
        for name,value in [("Seleziona","seleziona"),("Disegna balloon","balloon"),("Segna testo da cancellare","testo")]:
            ttk.Radiobutton(toolbox,text=name,variable=self.tool,value=value).pack(side="left",padx=5)
        ttk.Label(toolbox,text="Forma:").pack(side="left",padx=(12,2))
        ttk.Combobox(toolbox,textvariable=self.shape,values=["rect","ellipse"],state="readonly",width=8).pack(side="left")
        self.canvas=tk.Canvas(visual,background="#333333",highlightthickness=0)
        self.canvas.pack(fill="both",expand=True)
        self.canvas.bind("<ButtonPress-1>",self._mouse_down)
        self.canvas.bind("<ButtonRelease-1>",self._mouse_up)
        self.canvas.bind("<Configure>",lambda event:self._redraw())

        ttk.Label(controls,text="Balloon / didascalie",font=("Segoe UI",12,"bold")).pack(anchor="w")
        self.list=tk.Listbox(controls,height=13,exportselection=False)
        self.list.pack(fill="x",pady=(5,8))
        self.list.bind("<<ListboxSelect>>",self._select_region)
        ttk.Button(controls,text="Elimina regione selezionata",command=self._delete).pack(fill="x")
        ttk.Label(controls,text="Inglese riconosciuto (modificabile)").pack(anchor="w",pady=(10,2))
        self.english=tk.Text(controls,height=5,wrap="word",undo=True)
        self.english.pack(fill="x")
        ttk.Label(controls,text="Traduzione italiana").pack(anchor="w",pady=(8,2))
        self.italian=tk.Text(controls,height=6,wrap="word",undo=True)
        self.italian.pack(fill="x")
        self.upper=tk.BooleanVar(value=True)
        ttk.Checkbutton(controls,text="Lettering MAIUSCOLO",variable=self.upper).pack(anchor="w",pady=(5,0))
        ttk.Checkbutton(controls,text="Approvo questa regione per l'export",variable=self.approved).pack(anchor="w")
        ttk.Button(controls,text="Applica modifiche al balloon",command=self._apply).pack(fill="x",pady=(6,0))
        self.info=tk.StringVar(value="")
        ttk.Label(controls,textvariable=self.info,wraplength=310,justify="left").pack(anchor="w",pady=8)
        ttk.Label(controls,text="Importante: disegna sia il balloon sia i rettangoli delle lettere inglesi da cancellare. Le modifiche vengono applicate solo dopo approvazione.",wraplength=310,justify="left",foreground="#915800").pack(anchor="w",pady=(6,0))
        self.status=tk.StringVar(value="")
        ttk.Label(root,textvariable=self.status,anchor="w",padding=5).pack(fill="x")
        root.bind("<Control-s>",lambda e:self._save())

    def _page(self):
        return self.project.pages[self.page_idx]

    def _get_image(self):
        with Archive(self.project.source) as archive:
            return archive.image(self._page().filename)

    def _show_page(self):
        self._updating=True
        self.number.configure(text=f"{self.page_idx+1} / {len(self.project.pages)} — {self._page().filename.split('/')[-1][:20]}")
        self._updating=False
        self.region_idx=None
        self._refresh_list()
        self._set_fields(None)
        self._redraw()

    def _refresh_list(self):
        self.list.delete(0,tk.END)
        for r in self._page().regions:
            state="✓" if r.approved else "!"
            caption=r.original or r.italian or "(senza OCR)"
            self.list.insert(tk.END,f"{state} {r.id}: {caption[:42]}")
        if self.region_idx is not None and self.region_idx < self.list.size():
            self.list.selection_set(self.region_idx)

    def _set_fields(self,r):
        self._updating=True
        for widget in (self.english,self.italian):
            widget.delete("1.0",tk.END)
        if r:
            self.english.insert("1.0",r.original)
            self.italian.insert("1.0",r.italian)
            self.upper.set(r.uppercase)
            self.approved.set(r.approved)
            self.info.set(f"{r.id} • {r.shape} • OCR box: {len(r.words)} • confidenza {r.confidence:.0%}\n"+
                          ("Balloon proposto da detector: richiede verifica" if r.detected else "Zona manuale/non verificata"))
        else:
            self.info.set("Seleziona una regione o disegnane una nuova")
            self.approved.set(False)
        self._updating=False

    def _select_region(self,event=None):
        if self._updating:return
        selected=self.list.curselection()
        if selected:
            self.region_idx=int(selected[0]);self._set_fields(self._page().regions[self.region_idx]);self._redraw()

    def _apply(self):
        if self.region_idx is None:
            messagebox.showinfo("Regione","Seleziona prima una regione.");return
        r=self._page().regions[self.region_idx]
        r.original=self.english.get("1.0",tk.END).strip()
        r.italian=self.italian.get("1.0",tk.END).strip()
        r.uppercase=self.upper.get()
        r.approved=self.approved.get()
        self.project.save();self._refresh_list();self._redraw()
        self.status.set(f"Salvato balloon {r.id}" )

    def _navigate(self,delta):
        target=self.page_idx+delta
        if 0<=target<len(self.project.pages):
            self.page_idx=target;self.preview=False;self._show_page()

    def _redraw(self):
        if not hasattr(self,"canvas") or not self.canvas.winfo_exists():return
        try:
            img=self._get_image()
        except Exception as exc:
            self.status.set(str(exc));return
        if self.preview:
            img,reports=render_page(img,self._page().regions,approval_required=False,
                                    target_fill=self.project.lettering_profile.get("target_line_fill",.68))
            bad=[f"{r.id}: {r.message}" for r in reports if not r.applied]
            self.status.set("ANTEPRIMA | "+("; ".join(bad[:3]) if bad else "Nessuna anomalia rilevata dal motore locale"))
        width=max(1,self.canvas.winfo_width());height=max(1,self.canvas.winfo_height())
        scale=min(width/img.width,height/img.height,1.5)
        self._scale=scale
        small=img.resize((max(1,int(img.width*scale)),max(1,int(img.height*scale))))
        self._offset=((width-small.width)//2,(height-small.height)//2)
        if not self.preview:
            painter=ImageDraw.Draw(small)
            for i,r in enumerate(self._page().regions):
                coords=[int(v*scale) for v in r.balloon.as_tuple()]
                outline="#38bdf8" if i!=self.region_idx else "#00f08d"
                if r.shape == "ellipse":
                    painter.ellipse(coords,outline=outline,width=3)
                else:
                    if r.shape=="polygon" and r.polygon:
                        points=[(int(x*scale),int(y*scale)) for x,y in r.polygon]
                        painter.line(points+[points[0]],fill=outline,width=3)
                    else:
                        painter.rectangle(coords,outline=outline,width=3)
                painter.text((coords[0],coords[1]),r.id,fill="#fcad00",stroke_width=2,stroke_fill="#111111")
                for word in r.words:
                    painter.rectangle([int(v*scale) for v in word.as_tuple()],outline="#facc15",width=1)
        self.photo=ImageTk.PhotoImage(small)
        self.canvas.delete("all")
        self.canvas.create_image(self._offset[0],self._offset[1],anchor="nw",image=self.photo)

    def _pixel(self,event):
        page=self._page()
        x=round((event.x-self._offset[0])/self._scale)
        y=round((event.y-self._offset[1])/self._scale)
        return (max(0,min(page.width,x)),max(0,min(page.height,y)))

    def _mouse_down(self,event):
        self.drag_start=self._pixel(event)

    def _mouse_up(self,event):
        if self.drag_start is None:return
        x1,y1=self.drag_start;x2,y2=self._pixel(event)
        self.drag_start=None
        if self.tool.get()=="seleziona":
            for i,r in enumerate(self._page().regions):
                box=r.balloon
                if box.x1<=x2<=box.x2 and box.y1<=y2<=box.y2:
                    self.region_idx=i;self._refresh_list();self._set_fields(r);self._redraw();return
            return
        rect=Rect(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2))
        if rect.width<8 or rect.height<8:
            self.status.set("Disegna un'area più grande");return
        if self.tool.get()=="balloon":
            ids={r.id for r in self._page().regions}
            i=1
            while f"r{i:03}" in ids:i+=1
            r=Region(id=f"r{i:03}",balloon=rect,shape=self.shape.get(),source="gui-manual")
            self._page().regions.append(r)
            self.region_idx=len(self._page().regions)-1
            self._set_fields(r)
        elif self.tool.get()=="testo":
            if self.region_idx is None:
                messagebox.showinfo("Area testo","Seleziona prima il balloon che contiene le lettere originali.");return
            r=self._page().regions[self.region_idx]
            if not (r.balloon.x1<=rect.x1 and r.balloon.y1<=rect.y1 and
                    rect.x2<=r.balloon.x2 and rect.y2<=r.balloon.y2):
                messagebox.showwarning("Area testo","Il rettangolo del testo deve stare nel balloon selezionato.");return
            r.words.append(rect)
        self.project.save();self._refresh_list();self._redraw()

    def _delete(self):
        if self.region_idx is None:return
        if messagebox.askyesno("Conferma","Eliminare questo balloon dal progetto?"):
            self._page().regions.pop(self.region_idx);self.region_idx=None
            self.project.save();self._refresh_list();self._set_fields(None);self._redraw()

    def _scan_current(self):
        if self._page().regions and not messagebox.askyesno("OCR","Sostituire tutte le regioni della pagina con i suggerimenti OCR?\nLe correzioni di questa pagina saranno perse."):
            return
        try:
            result=scan_page(self._get_image())
            self._page().regions=result;self.project.save()
            self.region_idx=None;self._refresh_list();self._set_fields(None);self._redraw()
            self.status.set(f"OCR: {len(result)} regioni. Verificare maschere e contenuto.")
        except Exception as exc:
            messagebox.showerror("Errore OCR",str(exc))

    def _preview(self):
        if self.region_idx is not None:
            self._apply()
        self.preview=not self.preview;self._redraw()

    def _save(self):
        if self.region_idx is not None:self._apply()
        self.project.save();self.status.set("Progetto salvato")

    def _export(self):
        if self.region_idx is not None:self._apply()
        dest=filedialog.asksaveasfilename(title="Esporta CBZ",defaultextension=".cbz",filetypes=[("Comic ZIP","*.cbz")])
        if not dest:return
        try:
            report=export(self.project,dest)
            applied=sum(r["applied"] for page in report for r in page["regions"])
            blocked=sum(not r["applied"] for page in report for r in page["regions"])
            messagebox.showinfo("Esportazione",f"Salvato CBZ:\n{dest}\n\nRegioni applicate: {applied}\nRegioni non applicate: {blocked}\nControlla il file .report.json")
        except Exception as exc:
            messagebox.showerror("Esportazione fallita",str(exc))

    def run(self):
        self.root.mainloop()


def launch(project_path):
    Editor(project_path).run()

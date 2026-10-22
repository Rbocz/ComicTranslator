"""Single-window complete chapter flow. Tk is only touched from the main thread."""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from PIL import ImageTk
from .full_translate import DEFAULT_MODELS,translate_chapter,export_chapter
from .project import Project
from .archives import Archive
from .rendering import render_page


class TranslateWindow:
    def __init__(self,parent=None,source_path:str=''):
        self.root=tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.root.title('ComicTranslator • Traduci fumetto completo')
        self.root.geometry('1260x855')
        self.root.minsize(960,675)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.source=tk.StringVar(master=self.root,value=source_path)
        self.directory=tk.StringVar(master=self.root,value=self.default_directory(source_path))
        self.provider=tk.StringVar(master=self.root,value='Google Gemini')
        self.model=tk.StringVar(master=self.root,value=DEFAULT_MODELS['Google Gemini'])
        self.key=tk.StringVar(master=self.root)
        self.startpage=tk.StringVar(master=self.root,value='1')
        self.endpage=tk.StringVar(master=self.root,value='')
        self.accurate=tk.BooleanVar(master=self.root,value=True)
        self.agree=tk.BooleanVar(master=self.root,value=False)
        self.lettering=tk.BooleanVar(master=self.root,value=True)
        self.status=tk.StringVar(master=self.root,value='Carica un fumetto, scegli provider e incolla una chiave API.')
        self.page_var=tk.StringVar(master=self.root,value='1')
        self._cancel=threading.Event();self._events=queue.Queue();self._worker=None
        self._project=None;self._project_path=None;self._outpath=None
        self._page_cache=None;self._selected_region=None;self._photo=None
        self._build();self.root.after(150,self._poll)

    @staticmethod
    def default_directory(source):
        return str(Path(source).resolve().parent/'ComicTranslator-Italiano') if source else ''

    def _build(self):
        root=self.root
        header=ttk.Frame(root,padding=(15,12));header.pack(fill='x')
        ttk.Label(header,text='TRADUCI UN INTERO FUMETTO',font=('Segoe UI',17,'bold')).pack(anchor='w')
        ttk.Label(header,text='CBR / CBZ  →  riconoscimento visivo  →  traduzione IT  →  lettering  →  CBZ finale').pack(anchor='w')
        config=ttk.Frame(root,padding=(15,6));config.pack(fill='x')
        config.columnconfigure(1,weight=1)
        ttk.Label(config,text='Fumetto inglese').grid(row=0,column=0,sticky='w',pady=4)
        ttk.Entry(config,textvariable=self.source).grid(row=0,column=1,sticky='ew',padx=8)
        ttk.Button(config,text='Sfoglia…',command=self._choose_source).grid(row=0,column=2)
        ttk.Label(config,text='Cartella di lavoro / output').grid(row=1,column=0,sticky='w',pady=4)
        ttk.Entry(config,textvariable=self.directory).grid(row=1,column=1,sticky='ew',padx=8)
        ttk.Button(config,text='Scegli disco…',command=self._choose_dir).grid(row=1,column=2)
        auth=ttk.Frame(root,padding=(15,5));auth.pack(fill='x')
        ttk.Label(auth,text='Servizio IA').pack(side='left')
        ttk.Combobox(auth,textvariable=self.provider,values=list(DEFAULT_MODELS),state='readonly',width=17).pack(side='left',padx=6)
        self.provider.trace_add('write',lambda *args:self.model.set(DEFAULT_MODELS[self.provider.get()]))
        ttk.Label(auth,text='Modello').pack(side='left')
        ttk.Entry(auth,textvariable=self.model,width=23).pack(side='left',padx=6)
        ttk.Label(auth,text='Chiave API').pack(side='left')
        ttk.Entry(auth,textvariable=self.key,show='•',width=37).pack(side='left',fill='x',expand=True,padx=6)
        ttk.Label(auth,text='(non viene salvata)').pack(side='left')
        options=ttk.Frame(root,padding=(15,6));options.pack(fill='x')
        ttk.Label(options,text='Da pagina').pack(side='left')
        ttk.Entry(options,textvariable=self.startpage,width=5).pack(side='left',padx=(5,12))
        ttk.Label(options,text='A pagina').pack(side='left')
        ttk.Entry(options,textvariable=self.endpage,width=5).pack(side='left',padx=(5,13))
        ttk.Label(options,text='(vuoto = ultima)').pack(side='left')
        ttk.Checkbutton(options,text='Analisi accurata (3 viste per pagina alta)',variable=self.accurate).pack(side='left',padx=14)
        ttk.Checkbutton(options,text='Esporta lettering automatico',variable=self.lettering).pack(side='left')
        consent=ttk.Frame(root,padding=(15,0));consent.pack(fill='x')
        ttk.Checkbutton(consent,text='Autorizzo l’invio delle immagini al servizio IA scelto. So che le API potrebbero avere costi.',variable=self.agree).pack(anchor='w')
        actions=ttk.Frame(root,padding=(15,8));actions.pack(fill='x')
        self.go=ttk.Button(actions,text='▶ TRADUCI TUTTO ED ESPORTA CBZ',command=self._start)
        self.go.pack(side='left',fill='x',expand=True)
        self.cancel=ttk.Button(actions,text='Interrompi dopo la pagina',command=self._stop,state='disabled')
        self.cancel.pack(side='left',padx=7)
        ttk.Button(actions,text='Apri progetto precedente',command=self._open_project).pack(side='left')
        progress=ttk.Frame(root,padding=(15,0));progress.pack(fill='x')
        self.bar=ttk.Progressbar(progress,maximum=100);self.bar.pack(side='left',fill='x',expand=True)
        ttk.Label(progress,textvariable=self.status,wraplength=525).pack(side='left',padx=10)
        split=ttk.Panedwindow(root,orient='horizontal');split.pack(fill='both',expand=True,padx=15,pady=9)
        preview=ttk.Frame(split);split.add(preview,weight=3)
        details=ttk.Frame(split);split.add(details,weight=2)
        page_toolbar=ttk.Frame(preview);page_toolbar.pack(fill='x')
        ttk.Button(page_toolbar,text='◀',command=lambda:self._jump(-1)).pack(side='left')
        ttk.Entry(page_toolbar,textvariable=self.page_var,width=5).pack(side='left',padx=6)
        ttk.Button(page_toolbar,text='▶',command=lambda:self._jump(1)).pack(side='left')
        ttk.Button(page_toolbar,text='Aggiorna anteprima',command=self._preview).pack(side='right')
        self.canvas=tk.Canvas(preview,bg='#242424',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True,pady=(6,0))
        self.canvas.bind('<Configure>',lambda e:self._preview() if self._project else None)
        ttk.Label(details,text='Testi rilevati (seleziona per correggere)').pack(anchor='w')
        self.list=tk.Listbox(details,exportselection=False,height=12)
        self.list.pack(fill='both',expand=True,pady=(4,8))
        self.list.bind('<<ListboxSelect>>',lambda e:self._select_region())
        ttk.Label(details,text='Inglese').pack(anchor='w')
        self.english=tk.Text(details,height=4,wrap='word');self.english.pack(fill='x')
        ttk.Label(details,text='Italiano (modificabile)').pack(anchor='w',pady=(6,0))
        self.italian=tk.Text(details,height=5,wrap='word');self.italian.pack(fill='x')
        row=ttk.Frame(details);row.pack(fill='x',pady=6)
        self.approved=tk.BooleanVar(master=self.root,value=False)
        ttk.Checkbutton(row,text='Applica questo testo',variable=self.approved).pack(side='left')
        ttk.Button(row,text='Salva correzione',command=self._save_edit).pack(side='right')
        row2=ttk.Frame(details);row2.pack(fill='x')
        ttk.Button(row2,text='Riesporta CBZ',command=self._reexport).pack(side='left',fill='x',expand=True)
        ttk.Button(row2,text='Apri cartella risultati',command=self._open_folder).pack(side='left',padx=7)
        ttk.Label(details,text='L’app conserva le pagine originali quando il testo non può essere sostituito in sicurezza. Controlla il report .report.json: nessun sistema OCR/lettering è infallibile.',wraplength=440).pack(anchor='w',pady=(8,2))

    def _choose_source(self):
        file=filedialog.askopenfilename(parent=self.root,title='Scegli CBR/CBZ inglese',filetypes=[('Fumetti','*.cbr *.cbz')])
        if file:
            self.source.set(file)
            if not self.directory.get():self.directory.set(self.default_directory(file))

    def _choose_dir(self):
        folder=filedialog.askdirectory(parent=self.root,initialdir=self.directory.get() or str(Path.home()))
        if folder:self.directory.set(folder)

    def _start(self):
        if self._worker and self._worker.is_alive():return
        source=Path(self.source.get());folder=Path(self.directory.get())
        if not source.is_file() or source.suffix.lower() not in ('.cbz','.cbr'):
            messagebox.showerror('Fumetto','Seleziona un archivio .cbr/.cbz valido',parent=self.root);return
        if not self.key.get().strip():messagebox.showerror('API','Inserisci una chiave API valida',parent=self.root);return
        if not self.agree.get():messagebox.showerror('Consenso','Conferma prima l’invio delle pagine al provider scelto.',parent=self.root);return
        try:
            first=int(self.startpage.get());last=int(self.endpage.get()) if self.endpage.get().strip() else None
            if first<1 or (last is not None and last<first):raise ValueError()
        except ValueError:
            messagebox.showerror('Pagine','Inserisci un intervallo valido.',parent=self.root);return
        provider=self.provider.get();api_key=self.key.get().strip();model=self.model.get().strip()
        accurate=self.accurate.get();lettering=self.lettering.get()
        calls=(last-first+1 if last is not None else 'tutte le')
        multiplier=3 if accurate else 1
        if not messagebox.askyesno('Conferma elaborazione API',f'Inviare {calls} pagine a {provider} per OCR e traduzione?\nModalità: fino a {multiplier} chiamate per pagina.\nL’operazione potrebbe avere un costo.\n\nI dati originali non verranno sovrascritti.',parent=self.root):return
        folder.mkdir(parents=True,exist_ok=True)
        self._project_path=str(folder/(source.stem+'.project.json'))
        self._outpath=str(folder/(source.stem+'_ITALIANO.cbz'))
        self._cancel.clear();self.go.configure(state='disabled');self.cancel.configure(state='normal')
        self.bar.configure(value=0);self.status.set('Preparazione archivio…')
        def work():
            try:
                def notify(s,msg):self._events.put(('progress',s.pages_done,s.pages_total,msg))
                project,status,errors=translate_chapter(str(source),self._project_path,provider,api_key,model,first,last,accurate,
                                              notify,self._cancel.is_set)
                if lettering:
                    self._events.put(('message','Esportazione in corso…'))
                    report=export_chapter(project,self._outpath)
                    applied=sum(r['applied'] for pg in report for r in pg['regions'])
                    blocked=sum(not r['applied'] for pg in report for r in pg['regions'])
                else:applied=blocked=0
                self._events.put(('done',status.pages_done,status.pages_total,len(errors),applied,blocked))
            except Exception as exc:self._events.put(('error',str(exc)))
            finally:
                api_key=''  # Not persisted to project or settings.
        self._worker=threading.Thread(target=work,daemon=True);self._worker.start()

    def _poll(self):
        try:
            while True:
                ev=self._events.get_nowait()
                if ev[0]=='progress':
                    _,done,total,message=ev
                    self.bar['value']=int(100*done/max(1,total));self.status.set(message)
                elif ev[0]=='message':self.status.set(ev[1])
                elif ev[0]=='error':
                    self.status.set('Errore: '+ev[1]);self.go.configure(state='normal');self.cancel.configure(state='disabled')
                    messagebox.showerror('ComicTranslator',ev[1],parent=self.root)
                elif ev[0]=='done':
                    _,done,total,failed,applied,blocked=ev
                    self.go.configure(state='normal');self.cancel.configure(state='disabled')
                    self.status.set(f'Elaborate {done}/{total} pagine, problemi API {failed}, lettering {applied} applicati, {blocked} da rivedere.')
                    self._load_project(self._project_path)
                    messagebox.showinfo('Elaborazione terminata',f'Pagine elaborate: {done}/{total}\nRiquadri applicati: {applied}\nRiquadri non applicati/da rivedere: {blocked}\n\nRisultato:\n{self._outpath if applied or blocked else self._project_path}\n\nControlla le pagine in anteprima.',parent=self.root)
        except queue.Empty:pass
        if self.root.winfo_exists():self.root.after(150,self._poll)

    def _stop(self):self._cancel.set();self.status.set('Stop richiesto. Termino la pagina corrente e salvo il progetto…')

    def _load_project(self,path):
        self._project=Project.load(path);self._project_path=path
        if not self._outpath:self._outpath=str(Path(path).with_name(Path(path).stem.replace('.project','')+'_ITALIANO.cbz'))
        self.page_var.set('1');self._preview()

    def _open_project(self):
        path=filedialog.askopenfilename(parent=self.root,title='Apri progetto precedente',filetypes=[('Progetti ComicTranslator','*.json')])
        if path:
            try:
                self._load_project(path)
                self.source.set(self._project.source)
                self.directory.set(str(Path(path).parent))
            except Exception as exc:messagebox.showerror('Progetto non valido',str(exc),parent=self.root)

    def _jump(self,delta):
        if not self._project:return
        try:n=int(self.page_var.get())+delta
        except ValueError:n=1
        n=min(len(self._project.pages),max(1,n));self.page_var.set(str(n));self._preview()

    def _preview(self):
        if not self._project:return
        try:
            number=int(self.page_var.get())
            if not 1<=number<=len(self._project.pages):return
            page=self._project.pages[number-1]
            with Archive(self._project.source) as archive:image=archive.image(page.filename)
            shown,reports=render_page(image,page.regions)
            self._page_cache=(number,image,shown)
            cw=max(220,self.canvas.winfo_width());ch=max(250,self.canvas.winfo_height())
            shown.thumbnail((cw-16,ch-16))
            self._photo=ImageTk.PhotoImage(shown,master=self.canvas)
            self.canvas.delete('all');self.canvas.create_image(cw//2,ch//2,image=self._photo)
            self.list.delete(0,tk.END)
            for i,r in enumerate(page.regions):
                marker='✓' if r.approved else '!'
                self.list.insert(tk.END,f'{marker} {i+1}. {r.original[:65]}')
            self._selected_region=None;self.english.delete('1.0','end');self.italian.delete('1.0','end')
            self.status.set(f'Pagina {number}/{len(self._project.pages)}: {len(page.regions)} regioni; {sum(r.applied for r in reports)} applicate')
        except Exception as exc:self.status.set('Anteprima: '+str(exc))

    def _select_region(self):
        if not self._project:return
        selection=self.list.curselection()
        if not selection:return
        idx=selection[0];number=int(self.page_var.get())
        r=self._project.pages[number-1].regions[idx];self._selected_region=idx
        self.english.delete('1.0','end');self.english.insert('1.0',r.original)
        self.italian.delete('1.0','end');self.italian.insert('1.0',r.italian)
        self.approved.set(r.approved)

    def _save_edit(self):
        if self._project is None or self._selected_region is None:return
        number=int(self.page_var.get());r=self._project.pages[number-1].regions[self._selected_region]
        r.italian=self.italian.get('1.0','end').strip();r.original=self.english.get('1.0','end').strip()
        r.approved=self.approved.get() and bool(r.italian)
        self._project.save();self._preview()

    def _reexport(self):
        if not self._project:return
        try:
            path=self._outpath or str(Path(self._project_path).with_suffix('.cbz'))
            report=export_chapter(self._project,path)
            count=sum(r['applied'] for p in report for r in p['regions'])
            self.status.set(f'CBZ aggiornato: {path} · {count} traduzioni inserite')
        except Exception as exc:messagebox.showerror('Export fallito',str(exc),parent=self.root)

    def _open_folder(self):
        if not self._project_path:return
        target=str(Path(self._project_path).parent)
        if os.name=='nt':os.startfile(target)
        else:messagebox.showinfo('Cartella risultati',target,parent=self.root)

    def close(self):
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno('Elaborazione in corso','Vuoi interrompere al termine della pagina corrente? La finestra rimarrà aperta fino al salvataggio.',parent=self.root):return
            self._stop();return
        self.key.set('');self.root.destroy()

    def run(self):self.root.mainloop()


def launch(parent=None,source_path=''):
    app=TranslateWindow(parent,source_path)
    if parent is None:app.run()
    return app
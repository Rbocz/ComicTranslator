"""File-picker entrypoint for users starting from a Windows batch launcher."""
import tkinter as tk
from tkinter import filedialog,messagebox
from pathlib import Path
from .project import Project
from .gui import launch


def main():
    root=tk.Tk();root.withdraw()
    file=filedialog.askopenfilename(title="Apri fumetto CBR/CBZ oppure progetto",
        filetypes=[("Fumetti o progetto","*.cbz *.cbr *.json"),
                   ("Tutti i file","*.*")])
    if not file:
        root.destroy();return
    source=Path(file)
    if source.suffix.lower()==".json":
        project_path=file
    else:
        project_path=str(source.with_suffix(".project.json"))
        if Path(project_path).exists():
            if not messagebox.askyesno("Progetto esistente", "Esiste già un progetto per questo fumetto. Vuoi aprirlo senza sovrascriverlo?"):
                root.destroy();return
        else:
            try:
                Project.create(file,project_path)
            except Exception as exc:
                messagebox.showerror("Importazione fallita",str(exc));root.destroy();return
            messagebox.showinfo("Progetto creato", "Il fumetto è stato importato senza modifiche. Nell'editor premi 'Rileva OCR' per individuare i balloon, oppure disegnali manualmente.")
    root.destroy()
    launch(project_path)


if __name__=="__main__":main()

"""A single guided Windows entrypoint for the first real detector trial.

No API key, CLI commands or Tesseract needed to review speech balloons.
Weights are downloaded ONLY after user confirmation, verified by SHA-256.
"""
from __future__ import annotations

import os
import json
import shutil
import tempfile
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .learned_detection import MODEL_FILENAME, verify_model_file, fetch_model


def user_data_directory() -> Path:
    """Keep model and annotations outside a downloaded/source checkout."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"])
    else:
        root = Path.home() / ".local" / "share"
    return root / "ComicTranslator"



def settings_path() -> Path:
    """Only this tiny settings file remains in the default Windows app-data folder."""
    return user_data_directory() / "settings.json"


def load_storage_directory() -> Path:
    """Use the user's chosen disk on subsequent launches; default is legacy AppData."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        path = Path(data["storage_directory"]).expanduser()
        if path.is_absolute():
            return path
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return user_data_directory()


def validate_storage_directory(directory: str | Path) -> Path:
    """Check that the requested drive exists and can be written to."""
    if not str(directory).strip():
        raise ValueError("Scegli una cartella per il modello sul secondo disco")
    root = Path(directory).expanduser()
    if not root.is_absolute():
        raise ValueError("La cartella deve avere un percorso assoluto (es. D:\\ComicTranslator)")
    root.mkdir(parents=True, exist_ok=True)
    # A failed disk mount or a read-only drive must be reported before download.
    with tempfile.NamedTemporaryFile(prefix="comictranslator-", dir=root, delete=True) as file:
        file.write(b"disk-check")
        file.flush()
    return root.resolve()


def save_storage_directory(root: Path) -> None:
    """Persist selection atomically; never store the potentially large model here."""
    root = validate_storage_directory(root)
    file = settings_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps({"storage_directory": str(root)}, indent=2), encoding="utf-8")
        os.replace(temporary, file)
    finally:
        temporary.unlink(missing_ok=True)


def move_verified_model(source: Path, destination: Path) -> Path:
    """Copy to selected disk, verify SHA-256, then remove the old model.

    On failure, keep the original intact and do not publish an unverified file.
    """
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination:
        if not verify_model_file(source):
            raise ValueError("Modello esistente non verificato")
        return destination
    if destination.exists():
        if verify_model_file(destination):
            return destination
        raise ValueError("Esiste già un file modello non valido nella cartella scelta")
    if not verify_model_file(source):
        raise ValueError("Non trovo un modello integro nel percorso precedente")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".transfer")
    try:
        shutil.copyfile(source, partial)
        if not verify_model_file(partial):
            raise ValueError("La copia sul secondo disco non ha superato la verifica SHA-256")
        os.replace(partial, destination)
        source.unlink()
    finally:
        partial.unlink(missing_ok=True)
    return destination


def annotation_path(archive: str | Path, root: Path | None = None) -> Path:
    source = Path(archive)
    # Same basename in two directories must not overwrite annotation files.
    import hashlib
    digest = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:10]
    return (root or user_data_directory()) / "annotations" / f"{source.stem[:60]}-{digest}.json"


def model_path(root: Path | None = None) -> Path:
    return (root or user_data_directory()) / "models" / MODEL_FILENAME


def validate_selection(archive: str, page: str) -> tuple[Path, int]:
    source = Path(archive).expanduser()
    if not source.is_file() or source.suffix.lower() not in {".cbr", ".cbz"}:
        raise ValueError("Scegli un fumetto .cbr o .cbz esistente")
    try:
        page_number = int(page)
    except ValueError as exc:
        raise ValueError("Il numero di pagina deve essere un intero") from exc
    if page_number < 1 or page_number > 1000:
        raise ValueError("Il numero di pagina deve essere compreso tra 1 e 1000")
    return source.resolve(), page_number


class StartWindow:
    def __init__(self, root: tk.Tk | None = None):
        self.root = root or tk.Tk()
        self.root.title("ComicTranslator — Avvio facile")
        self.root.geometry("760x520")
        self.root.minsize(620, 420)
        self.root.resizable(True, True)
        self.source = tk.StringVar(value="")
        self.page = tk.StringVar(value="5")
        self.storage = tk.StringVar(value=str(load_storage_directory()))
        self.status = tk.StringVar(value="Scegli il fumetto inglese che vuoi analizzare.")
        self._working = False
        self._construct()

    def _construct(self):
        panel = ttk.Frame(self.root, padding=22)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="ComicTranslator", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Riconosci i balloon e correggili, senza modificare le tavole originali.").pack(anchor="w", pady=(2, 22))
        ttk.Label(panel, text="1. Seleziona un fumetto .CBR o .CBZ").pack(anchor="w")
        file_row = ttk.Frame(panel)
        file_row.pack(fill="x", pady=(5, 13))
        ttk.Entry(file_row, textvariable=self.source).pack(side="left", fill="x", expand=True)
        ttk.Button(file_row, text="Sfoglia...", command=self._browse).pack(side="left", padx=(8, 0))
        row = ttk.Frame(panel)
        row.pack(fill="x")
        ttk.Label(row, text="2. Pagina da analizzare:").pack(side="left")
        ttk.Entry(row, width=6, textvariable=self.page).pack(side="left", padx=(10, 0))
        ttk.Label(row, text="(per Absolute Batman inizia da 5)").pack(side="left", padx=(12, 0))
        # Always show the storage selector BEFORE the download button.  The
        # previous build had a working _choose_storage() method but no UI
        # control calling it: models were silently directed to C:.
        ttk.Label(panel, text="3. Cartella per modello e annotazioni (puoi scegliere il disco F:)").pack(
            anchor="w", pady=(14, 0))
        storage_row = ttk.Frame(panel)
        storage_row.pack(fill="x", pady=(5, 7))
        self.storage_entry = ttk.Entry(storage_row, textvariable=self.storage)
        self.storage_entry.pack(side="left", fill="x", expand=True)
        self.storage_picker = ttk.Button(storage_row, text="Scegli cartella...", command=self._choose_storage)
        self.storage_picker.pack(side="left", padx=(8, 0))
        self.launch_button = ttk.Button(panel, text="4. ANALIZZA I BALLOON", command=self._start)
        self.launch_button.pack(fill="x", ipady=9, pady=(13, 8))
        ttk.Label(panel, textvariable=self.status, wraplength=580, foreground="#455a64").pack(anchor="w")
        ttk.Label(panel, text="Primo uso: verrà richiesta la conferma per scaricare il modello ONNX. Le pagine non sono inviate online.",
                  wraplength=580, foreground="#555555").pack(anchor="w", pady=(13, 0))

    def _browse(self):
        path = filedialog.askopenfilename(parent=self.root, title="Apri il fumetto inglese",
                                          filetypes=[("Fumetti", "*.cbr *.cbz"), ("Tutti i file", "*.*")])
        if path:
            self.source.set(path)

    def _choose_storage(self):
        # If the comic is on F:, start on that disk to avoid navigating out
        # of the default Windows AppData C: folder manually.
        comic = Path(self.source.get())
        initial = comic.parent if comic.is_file() else Path(self.storage.get())
        base = initial if initial.is_dir() else (initial.parent if initial.parent.is_dir() else Path.home())
        directory = filedialog.askdirectory(parent=self.root,
                     title="Scegli la cartella del modello sul secondo disco",
                     initialdir=str(base), mustexist=True)
        if directory:
            selected = Path(directory)
            # Choosing the root of a drive puts the app data in its own folder.
            if selected == Path(selected.anchor):
                selected = selected / "ComicTranslator-Dati"
            self.storage.set(str(selected))

    def _start(self):
        if self._working:
            return
        try:
            source, page = validate_selection(self.source.get(), self.page.get())
            storage_root = validate_storage_directory(self.storage.get())
            # Fast metadata check before prompting for any network activity.
            from .archives import Archive
            with Archive(source) as archive:
                if page > len(archive.names):
                    raise ValueError(f"Questo fumetto contiene {len(archive.names)} pagine, non {page}.")
        except Exception as exc:
            messagebox.showerror("Non posso aprire il fumetto", str(exc), parent=self.root)
            return

        path = model_path(storage_root)
        if verify_model_file(path):
            save_storage_directory(storage_root)
            self._open_editor(source, page, path, storage_root)
            return
        old_path = model_path(user_data_directory())
        if old_path != path and verify_model_file(old_path):
            relocate = messagebox.askyesno(
                "Modello già presente sul primo disco",
                f"Ho trovato un modello già scaricato in:\n{old_path}\n\n"
                f"Vuoi SPOSTARLO qui, senza riscaricarlo?\n{path}", parent=self.root)
            if relocate:
                try:
                    move_verified_model(old_path, path)
                    save_storage_directory(storage_root)
                    self._open_editor(source, page, path, storage_root)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Spostamento modello non riuscito", str(exc), parent=self.root)
                return
        agree = messagebox.askyesno(
            "Modello di riconoscimento",
            "Per individuare i balloon devo scaricare una sola volta il modello ONNX "
            f"dalla sua fonte originale, controllandone l'integrità.\n\nDestinazione:\n{path}\n\n"
            "Confermi il download in questa cartella? Le tavole restano sul tuo computer.",
            parent=self.root)
        if not agree:
            self.status.set("Download annullato. Riprova quando vuoi.")
            return
        try:
            save_storage_directory(storage_root)
        except OSError as exc:
            messagebox.showerror("Cartella non scrivibile", str(exc), parent=self.root)
            return
        self._working = True
        self.launch_button.state(["disabled"])
        self.status.set("Sto scaricando e verificando il modello. Connessione Internet necessaria solo ora...")
        threading.Thread(target=self._fetch_in_worker, args=(source, page, path, storage_root), daemon=True).start()

    def _fetch_in_worker(self, source: Path, page: int, path: Path, storage_root: Path):
        try:
            fetch_model(path)
            self.root.after(0, lambda: self._download_finished(source, page, path, storage_root, None))
        except Exception as exc:
            msg = str(exc)
            self.root.after(0, lambda: self._download_finished(source, page, path, storage_root, msg))

    def _download_finished(self, source: Path, page: int, path: Path, storage_root: Path, error: str | None):
        self._working = False
        self.launch_button.state(["!disabled"])
        if error:
            self.status.set("Impossibile scaricare il modello. Puoi riprovare.")
            messagebox.showerror("Download non riuscito", error, parent=self.root)
            return
        self.status.set("Modello pronto. Apro l'annotatore...")
        self._open_editor(source, page, path, storage_root)

    def _open_editor(self, source: Path, page: int, path: Path, storage_root: Path):
        if not verify_model_file(path):
            messagebox.showerror("Modello non valido", "File ONNX mancante o non verificato", parent=self.root)
            return
        try:
            from .annotation_editor import AnnotationEditor
            # Explicit constructor allows a friendly error before changing windows.
            editor = AnnotationEditor(str(source), str(annotation_path(source, storage_root)), page,
                                      "onnx", str(path))
        except Exception as exc:
            messagebox.showerror("Impossibile aprire l'annotatore", str(exc), parent=self.root)
            return
        self.root.withdraw()
        # AnnotationEditor manages its own Tk root and mainloop.
        try:
            editor.run()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    StartWindow().run()


if __name__ == "__main__":
    main()
"""Stable PyInstaller entrypoint, imported as a package (never as easy_start.py).

The executable's --self-test mode runs in CI on the FROZEN Windows binary,
so a Python-only unit test cannot accidentally hide a broken package.
"""
from __future__ import annotations
import json
import sys
import traceback
from pathlib import Path


def frozen_startup_test(marker: str) -> int:
    try:
        # Import the actual GUI implementation through the installed package.
        from comictranslate_it.easy_start import StartWindow
        from comictranslate_it.annotation_editor import AnnotationEditor
        from comictranslate_it.learned_detection import LearnedDetector, MODEL_FILENAME
        from comictranslate_it.archives import Archive, _configure_rar_backend
        import rarfile
        import onnxruntime

        _configure_rar_backend(rarfile)
        packaged = bool(getattr(sys, "frozen", False))
        bundled = Path(sys.executable).resolve().parent / "tools" / "7z.exe"
        valid_7zip = packaged and bundled.is_file() and Path(rarfile.SEVENZIP_TOOL).resolve() == bundled
        if not packaged or not valid_7zip:
            raise RuntimeError("7-Zip was not configured from the portable application folder")
        # The previous installer was shipped without a visible folder picker:
        # execute a frozen GUI construction test, not only an import check.
        ui = StartWindow()
        try:
            ui.root.update_idletasks()
            storage_button_visible = (
                ui.storage_picker.winfo_manager() == "pack"
                and ui.storage_entry.winfo_manager() == "pack"
                and ui.storage_picker.winfo_rooty() < ui.launch_button.winfo_rooty()
                and ui.storage_picker.winfo_rooty() + ui.storage_picker.winfo_height()
                <= ui.root.winfo_rooty() + ui.root.winfo_height()
            )
            if not storage_button_visible:
                raise RuntimeError("Storage folder picker is missing or hidden in the main window")
        finally:
            ui.root.destroy()
        payload = {
            "status": "ok",
            "frozen": packaged,
            "bundled_7zip": valid_7zip,
            "storage_picker_visible": storage_button_visible,
            "model": MODEL_FILENAME,
            "onnxruntime": onnxruntime.__version__
        }
        result = 0
    except Exception:
        payload = {"status": "failed", "error": traceback.format_exc()}
        result = 1
    Path(marker).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result


def main() -> int:
    if "--self-test" in sys.argv:
        if len(sys.argv) != 3 or sys.argv[1] != "--self-test":
            return 2
        return frozen_startup_test(sys.argv[2])
    from comictranslate_it.easy_start import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

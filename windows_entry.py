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
        from comictranslate_it.full_gui import TranslateWindow
        from comictranslate_it.full_translate import translate_chapter, export_chapter
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
                and ui.storage_picker.master.winfo_manager() == "pack"
                and ui.storage_picker.master in ui.launch_button.master.pack_slaves()
                and ui.launch_button.master.pack_slaves().index(ui.storage_picker.master)
                    < ui.launch_button.master.pack_slaves().index(ui.launch_button)
            )
            if not storage_button_visible:
                raise RuntimeError("Storage folder picker is missing or hidden in the main window")
            if ui.translate_button.winfo_manager() != "pack":
                raise RuntimeError("Complete-comic translation button was not rendered")
            translation=TranslateWindow(ui.root)
            try:
                translation.root.update_idletasks()
                if translation.go.winfo_manager() != "pack":
                    raise RuntimeError("Full translation UI missing its Start button")
                full_gui_valid=True
            finally:
                translation.root.destroy()
            # Regression: two live Tk roots used to throw "pyimage1 doesn't exist".
            import io
            import tempfile
            import zipfile
            from PIL import Image
            with tempfile.TemporaryDirectory(prefix="comictranslator-ui-") as directory:
                archive = Path(directory) / "page.cbz"
                image_buffer = io.BytesIO()
                Image.new("RGB", (180, 120), "white").save(image_buffer, "PNG")
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("p1.png", image_buffer.getvalue())
                # Real offline end-to-end test on the packaged executable.
                from PIL import ImageDraw
                from comictranslate_it.project import Project
                from comictranslate_it.models import Region
                import json as _json
                test_comic=Path(directory)/"synthetic-book.cbz"
                original=Image.new("RGB",(460,300),(40,70,95))
                drawer=ImageDraw.Draw(original)
                drawer.rounded_rectangle((60,45,400,250),radius=25,fill="white",outline="black",width=3)
                drawer.text((150,140),"HELLO",fill="black")
                out=io.BytesIO();original.save(out,"PNG")
                with zipfile.ZipFile(test_comic,"w") as z:z.writestr("p1.png",out.getvalue())
                def fake_api(url,payload,headers):
                    data={"regions":[{"original":"HELLO","italian":"CIAO",
                                      "container_box":[130,148,870,833],
                                      "line_boxes":[[320,450,440,535]],
                                      "kind":"dialogue","uppercase":True,"certainty":96}]}
                    return {"choices":[{"message":{"content":_json.dumps(data)}}]}
                project,status,errors=translate_chapter(str(test_comic),str(Path(directory)/"book.project.json"),
                    "OpenAI","TEST-KEY","gpt-4.1-mini",accurate=False,http_client=fake_api)
                result_path=str(Path(directory)/"book_it.cbz")
                export_report=export_chapter(project,result_path)
                export_valid=(status.pages_done==1 and not errors and
                    Path(result_path).is_file() and
                    any(r["applied"] for pg in export_report for r in pg["regions"]))
                if not export_valid:
                    raise RuntimeError("Offline full comic translation/export failed in frozen Windows EXE")
                editor = AnnotationEditor(str(archive), str(Path(directory) / "annotations.json"))
                try:
                    editor.root.update_idletasks()
                    editor._redraw()
                    editor_photo_valid = (
                        editor.root.tk.call("image", "type", str(editor.photo)) == "photo"
                        and editor.photo.tk is editor.canvas.tk
                        and editor.photo.tk is not ui.root.tk
                    )
                    if not editor_photo_valid:
                        raise RuntimeError("Editor bitmap was created in the wrong Tk window")
                finally:
                    editor.root.destroy()
        finally:
            ui.root.destroy()
        payload = {
            "status": "ok",
            "frozen": packaged,
            "bundled_7zip": valid_7zip,
            "storage_picker_visible": storage_button_visible,
            "editor_photo_valid": editor_photo_valid,
            "full_gui_valid": full_gui_valid,
            "full_export_valid": export_valid,
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

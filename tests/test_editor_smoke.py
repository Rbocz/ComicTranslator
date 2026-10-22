"""Graphical editor can start headlessly when Tk/Xvfb is available.

Run in CI with Xvfb, or use a headless local Linux session. The core test suite
continues to work without a GUI display.
"""
import io
import os
import zipfile
import pytest
from PIL import Image


def test_annotation_editor_ui_opens_and_saves(tmp_path):
    if os.environ.get('COMICTRANSLATE_TEST_GUI') != '1':
        pytest.skip('Tkinter requires DISPLAY or Xvfb')
    from comictranslate_it.annotation_editor import AnnotationEditor
    image=Image.new('RGB',(160,100),'white')
    blob=io.BytesIO();image.save(blob,format='PNG')
    archive=tmp_path/'demo.cbz'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('page1.png',blob.getvalue())
    destination=tmp_path/'annotations.json'
    app=AnnotationEditor(str(archive),str(destination))
    try:
        app.root.update_idletasks()
        assert app._page()['verified'] is False
        app._add_shape([[5,5],[50,5],[50,35],[5,35]])
        app.verified.set(True);app._mark_verified()
        app._save()
        assert destination.exists()
    finally:
        app.root.destroy()


def test_editor_image_uses_its_canvas_tk_interpreter(tmp_path):
    """Regression: the launcher and the editor use two distinct Tk roots.

    ImageTk.PhotoImage must be created in the editor canvas' interpreter,
    or Windows displays: image "pyimage1" doesn't exist.
    """
    import tkinter as tk
    if os.name != 'nt' and not os.environ.get('DISPLAY'):
        pytest.skip('Tkinter display unavailable')
    from comictranslate_it.annotation_editor import AnnotationEditor
    image = Image.new('RGB', (240, 160), 'white')
    blob = io.BytesIO()
    image.save(blob, 'PNG')
    archive = tmp_path / 'two_windows.cbz'
    with zipfile.ZipFile(archive, 'w') as target:
        target.writestr('page1.png', blob.getvalue())
    try:
        launcher_root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter unavailable on this CI runner: {exc}")
    editor = None
    try:
        editor = AnnotationEditor(str(archive), str(tmp_path / 'annotations.json'))
        editor.root.update_idletasks()
        editor._redraw()
        assert editor.root.tk.call('image', 'type', str(editor.photo)) == 'photo'
        assert editor.photo.tk is editor.canvas.tk
        assert editor.photo.tk is not launcher_root.tk
    finally:
        if editor is not None:
            editor.root.destroy()
        launcher_root.destroy()

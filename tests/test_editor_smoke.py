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
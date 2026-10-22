"""GUI-start regression: catches API key closure bugs which pipeline-only tests miss."""
import io
import os
import zipfile
import pytest
from PIL import Image


def test_start_button_uses_entered_api_key_and_shows_completed_project(tmp_path,monkeypatch):
    if os.name!='nt' and not os.environ.get('DISPLAY'):
        pytest.skip('requires GUI display')
    import tkinter as tk
    import comictranslate_it.full_gui as ui
    from comictranslate_it.full_translate import JobStatus
    from comictranslate_it.project import Project
    cbz=tmp_path/'test.cbz';buf=io.BytesIO();Image.new('RGB',(300,240),'white').save(buf,'PNG')
    with zipfile.ZipFile(cbz,'w') as z:z.writestr('page001.png',buf.getvalue())
    keys=[]
    def fake_translate(source,project_path,provider,key,model,first,last,accurate,notify,stop):
        keys.append(key)
        project=Project.create(source,project_path)
        return project,JobStatus(1,1,0,1,0),{}
    monkeypatch.setattr(ui,'translate_chapter',fake_translate)
    monkeypatch.setattr(ui,'export_chapter',lambda project,destination:[])
    monkeypatch.setattr(ui.messagebox,'askyesno',lambda *a,**k:True)
    monkeypatch.setattr(ui.messagebox,'showinfo',lambda *a,**k:None)
    try:root=tk.Tk()
    except tk.TclError as exc:pytest.skip(f"GUI not available on runner: {exc}")
    root.withdraw();app=None
    try:
        app=ui.TranslateWindow(root,str(cbz))
        app.directory.set(str(tmp_path/'out'))
        app.agree.set(True);app.key.set('TEST-NOT-PERSISTED')
        app._start();app._worker.join(timeout=3)
        assert not app._worker.is_alive()
        app.root.update();app._poll()
        assert keys==['TEST-NOT-PERSISTED']
        assert app.key.get()==''
        assert app._project is not None
    finally:
        if app is not None:app.close()
        root.destroy()
"""UI-independent checks of the one-click startup path."""
from pathlib import Path
import pytest

from comictranslate_it.easy_start import (
    user_data_directory, annotation_path, model_path, validate_selection,
)
from comictranslate_it.archives import _configure_rar_backend


def test_validate_archive_and_page(tmp_path):
    comic = tmp_path / "prova.cbr"
    comic.write_bytes(b"dummy")
    assert validate_selection(str(comic), "5") == (comic.resolve(), 5)
    for value in ["0", "1001", "x"]:
        with pytest.raises(ValueError):
            validate_selection(str(comic), value)
    with pytest.raises(ValueError):
        validate_selection(str(tmp_path / "no.cbr"), "5")


def test_safe_private_paths(tmp_path):
    path1 = tmp_path / "a" / "comic.cbr"
    path2 = tmp_path / "b" / "comic.cbr"
    assert annotation_path(path1, tmp_path) != annotation_path(path2, tmp_path)
    assert annotation_path(path1, tmp_path).parent == tmp_path / "annotations"
    assert model_path(tmp_path).suffix == ".onnx"


def test_private_default_location(monkeypatch, tmp_path):
    monkeypatch.setattr("comictranslate_it.easy_start.os.name", "posix")
    monkeypatch.setattr("comictranslate_it.easy_start.Path.home", lambda: tmp_path)
    assert user_data_directory() == tmp_path / ".local" / "share" / "ComicTranslator"


def test_bundled_7zip_discovery(monkeypatch, tmp_path):
    # Ensures 7-Zip can be configured without requiring PATH editing.
    class FakeRarfile:
        SEVENZIP_TOOL = "7z"
        invoked = False
        def tool_setup(self, force=False):
            self.invoked = force
    fake = FakeRarfile()
    bundled = tmp_path / "tools" / "7z.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"dummy")
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ComicTranslator.exe"))
    _configure_rar_backend(fake)
    assert fake.SEVENZIP_TOOL == str(bundled)
    assert fake.invoked


def test_chosen_storage_directory_persists_and_is_used(tmp_path, monkeypatch):
    import comictranslate_it.easy_start as mod
    config = tmp_path / 'config' / 'settings.json'
    disk_two = tmp_path / 'SECOND_DISK' / 'ComicTranslator'
    monkeypatch.setattr(mod, 'settings_path', lambda: config)
    root = mod.validate_storage_directory(disk_two)
    mod.save_storage_directory(root)
    assert mod.load_storage_directory() == root
    assert mod.model_path(root).parent == root / 'models'
    assert mod.annotation_path(tmp_path / 'issue.cbr', root).parent == root / 'annotations'
    assert not (tmp_path / 'config' / 'models').exists()


def test_chosen_storage_rejects_relative_paths(tmp_path):
    from comictranslate_it.easy_start import validate_storage_directory
    with pytest.raises(ValueError):
        validate_storage_directory('relative/subfolder')
    with pytest.raises(ValueError):
        validate_storage_directory('')


def test_existing_model_can_move_to_second_drive(tmp_path, monkeypatch):
    import comictranslate_it.easy_start as mod
    first = tmp_path / 'first' / 'models' / 'm.onnx'
    second = tmp_path / 'second' / 'models' / 'm.onnx'
    first.parent.mkdir(parents=True)
    first.write_bytes(b'model-for-simulation')
    monkeypatch.setattr(mod, 'verify_model_file', lambda p: Path(p).read_bytes() == b'model-for-simulation')
    assert mod.move_verified_model(first, second) == second
    assert second.read_bytes() == b'model-for-simulation'
    assert not first.exists()


def test_model_migration_failure_keeps_source(tmp_path, monkeypatch):
    import comictranslate_it.easy_start as mod
    first=tmp_path / 'first.onnx'
    second=tmp_path / 'other' / 'second.onnx'
    first.write_bytes(b'old')
    monkeypatch.setattr(mod, 'verify_model_file', lambda p: Path(p).read_bytes() == b'old')
    second.parent.mkdir()
    second.write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        mod.move_verified_model(first, second)
    assert first.read_bytes() == b'old'
    assert second.read_bytes() == b'corrupt'


def test_visible_storage_picker_is_present_and_before_analyze():
    """Regression: UI had a chooser method but never displayed its button."""
    import os
    import tkinter as tk
    if os.name != 'nt' and not os.environ.get('DISPLAY'):
        pytest.skip('Tkinter display unavailable')
    from comictranslate_it.easy_start import StartWindow
    try:
        app = StartWindow()
    except tk.TclError:
        pytest.skip('Tkinter display unavailable')
    try:
        app.root.update_idletasks()
        assert app.storage_picker.winfo_manager() == 'pack'
        assert app.storage_entry.winfo_manager() == 'pack'
        assert app.storage_picker.cget('command')
        storage_row = app.storage_picker.master
        panel = app.launch_button.master
        assert storage_row.winfo_manager() == 'pack'
        assert storage_row in panel.pack_slaves()
        assert panel.pack_slaves().index(storage_row) < panel.pack_slaves().index(app.launch_button)
    finally:
        app.root.destroy()
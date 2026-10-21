"""Minimal repository CI smoke checks; extended local test suite is pending port."""
import io
import zipfile
from PIL import Image
import numpy as np
import pytest
from comictranslate_it.archives import Archive, natural_key, safe_entry
from comictranslate_it.models import Rect, Region
from comictranslate_it.project import Project
from comictranslate_it.lettering import balloon_mask
from comictranslate_it.rendering import render_page


def test_safe_archive_entry():
    assert safe_entry("folder/001.png")
    assert not safe_entry("../escape.png")
    assert not safe_entry("/absolute.png")
    assert not safe_entry("C:\\escape.png")


def test_natural_sort():
    assert sorted(["page10.png", "page2.png", "page1.png"], key=natural_key) == [
        "page1.png", "page2.png", "page10.png"
    ]


def test_archive_project_roundtrip(tmp_path):
    archive = tmp_path / "demo.cbz"
    image = Image.new("RGB", (100, 80), "white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("page1.png", buf.getvalue())
    path = tmp_path / "project.json"
    project = Project.create(str(archive), str(path))
    assert len(project.pages) == 1
    again = Project.load(str(path))
    assert again.pages[0].width == 100
    with Archive(archive) as src:
        assert src.image(src.names[0]).size == (100, 80)


def test_unapproved_region_is_untouched():
    image = Image.new("RGB", (180, 120), "white")
    region = Region(
        id="b1", balloon=Rect(10, 10, 160, 100),
        words=[Rect(50, 30, 120, 50)],
        original="HELLO", italian="CIAO", approved=False
    )
    result, report = render_page(image, [region])
    assert not report[0].applied
    assert np.array_equal(np.asarray(result), np.asarray(image))


def test_balloon_safe_margin():
    region = Region(id="b1", balloon=Rect(10, 10, 100, 100), margin=5)
    mask = balloon_mask((120, 120), region)
    assert mask[55, 55] == 255
    assert mask[10, 10] == 0
    assert mask[0, 0] == 0

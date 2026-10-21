"""Tests use generated synthetic imagery; comic reference scans are never published."""
import json
import numpy as np
import cv2
import pytest
from PIL import Image
from comictranslate_it.reference_benchmark import (
    split_pages,select_part,register,write_profile,ReferenceError)
from comictranslate_it.project import Project
from comictranslate_it.models import Region,Rect
from comictranslate_it.lettering import layout_text


def test_split_composite_white_gutter():
    top=np.full((210,180,3),95,dtype=np.uint8)
    bottom=np.full((260,180,3),40,dtype=np.uint8)
    img=np.concatenate((top,np.full((12,180,3),255,dtype=np.uint8),bottom))
    assert split_pages(img)==[(0,210),(222,482)]
    page,span,n=select_part(img,2)
    assert span==(222,482) and n==2 and page.shape[0]==260
    with pytest.raises(ReferenceError):select_part(img,3)


def test_registration_print_scaling():
    rng=np.random.default_rng(12)
    original=np.full((350,530,3),220,dtype=np.uint8)
    for i in range(420):
        x=int(rng.integers(10,510));y=int(rng.integers(10,330))
        color=tuple(map(int,rng.integers(10,200,3)))
        cv2.line(original,(x,y),
                 (min(529,x+int(rng.integers(3,70))),min(349,y+int(rng.integers(3,30)))),color,2)
    translated=cv2.resize(original,(795,525))
    aligned,valid,info=register(original,translated)
    assert info["inliers"]>=25
    assert info["rms_px"]<3
    assert abs(info["scale"]-1.5)<.02
    assert np.mean(np.abs(aligned[valid].astype("float32")-
                          translated[valid].astype("float32")))<12


def test_profile_requires_evidence(tmp_path):
    sample={"balloons":[
        {"mean_line_fill":.73,"ocr_word_count":4},
        {"mean_line_fill":.81,"ocr_word_count":3},
        {"mean_line_fill":.76,"ocr_word_count":6}]}
    profile=write_profile([sample],str(tmp_path/"profile.json"))
    assert profile["target_line_fill"]==.76
    assert json.loads((tmp_path/"profile.json").read_text())==profile
    with pytest.raises(ReferenceError):
        write_profile([{"balloons":[sample["balloons"][0]]}],str(tmp_path/"no.json"))


def test_project_style_is_persisted(tmp_path):
    p=Project(source=str(tmp_path/"source.cbz"))
    p.lettering_profile={"target_line_fill":.756}
    p.save(str(tmp_path/"test.project.json"))
    assert Project.load(str(tmp_path/"test.project.json")).lettering_profile["target_line_fill"]==.756


def test_lettering_profile_is_bounded():
    r=Region(id="a",balloon=Rect(5,5,190,105),italian="CIAO")
    with pytest.raises(ValueError):
        layout_text(r,(200,120),target_fill=.1)

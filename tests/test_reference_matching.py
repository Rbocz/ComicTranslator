"""Synthetic artwork match tests; absolutely no copyrighted comic pages are committed."""
import io
import zipfile
import numpy as np
import cv2
from PIL import Image
from comictranslate_it.reference_matching import match_references,compare_descriptors
from comictranslate_it.project import Project


def make_page(seed,shape=(400,320)):
    rng=np.random.default_rng(seed)
    image=np.full((shape[0],shape[1],3),235,dtype=np.uint8)
    for i in range(310):
        x=int(rng.integers(0,shape[1]));y=int(rng.integers(0,shape[0]))
        p=(min(shape[1]-1,x+int(rng.integers(-70,70))),
           min(shape[0]-1,y+int(rng.integers(-50,50))))
        color=tuple(map(int,rng.integers(25,140,3)))
        cv2.line(image,(x,y),p,color,2)
        if i%3==0:cv2.circle(image,(x,y),int(rng.integers(3,13)),color,2)
    return Image.fromarray(image)


def test_missing_descriptors_never_match():
    assert compare_descriptors(([],None),([],None))[0]==0


def test_pair_archive_and_project_streaming(tmp_path):
    archive_path=tmp_path/"example.cbz"
    with zipfile.ZipFile(archive_path,"w") as out:
        for i in range(1,5):
            buffer=io.BytesIO();make_page(i).save(buffer,"PNG")
            out.writestr(f"p{i:02}.png",buffer.getvalue())
    translated=np.asarray(make_page(3).resize((480,600))).copy()
    cv2.rectangle(translated,(30,30),(200,100),(255,255,255),-1)
    target=tmp_path/"translation.png";Image.fromarray(translated).save(target)
    report=match_references(str(archive_path),[str(target)],min_inliers=30)
    row=report["matches"][0]
    assert row["confidence"]=="high"
    assert row["selected"]["page"]==3
    assert row["selected"]["filename"]=="p03.png"
    assert row["top_margin"]>=2.5
    project=Project.create(str(archive_path),str(tmp_path/"local.project.json"))
    assert len(project.pages)==4
    assert [p.width for p in project.pages]==[320]*4

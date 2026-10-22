"""Annotation validation and unbiased one-to-one detection scoring."""
import io
import json
import zipfile
import pytest
import numpy as np
from PIL import Image,ImageDraw
from comictranslate_it.annotations import (
    normalize_polygon,denormalize_polygon,validate_shape,
    load_annotations,save_annotations,measure_regions,benchmark_archive,
)


def shape(box,kind='dialogue'):
    a,b,c,d=box
    return {'kind':kind,'polygon':[[a,b],[c,b],[c,d],[a,d]]}


def test_roundtrip_resolution_independence():
    points=[[20,30],[80,30],[80,90],[20,90]]
    p=normalize_polygon(points,100,120)
    assert denormalize_polygon(p,100,120)==points
    assert denormalize_polygon(p,200,240)==[[40,60],[160,60],[160,180],[40,180]]


def test_invalid_shape_and_annotation_file(tmp_path):
    with pytest.raises(ValueError):validate_shape(shape((0,0,1.01,1)))
    with pytest.raises(ValueError):validate_shape({'kind':'dialogue','polygon':[[0,0],[0,0]]})
    good={'schema':1,'archive_name':'demo.cbz','pages':{'5':{
        'filename':'5.png','width':100,'height':100,
        'regions':[shape((.1,.1,.8,.8),'caption')]}}}
    path=tmp_path/'private_annotations.json'
    save_annotations(good,path)
    assert load_annotations(path,'demo.cbz')==good
    with pytest.raises(ValueError):load_annotations(path,'not_this_archive.cbz')
    assert not path.with_suffix('.json.tmp').exists()


def test_perfect_detection_and_kind_agreement():
    gt=[shape((.1,.1,.4,.4),'caption'),shape((.5,.5,.8,.8))]
    result=measure_regions(gt,[dict(x) for x in gt])
    assert (result['tp'],result['fp'],result['fn'])==(2,0,0)
    assert result['precision']==result['recall']==result['f1']==1
    assert result['kind_correct']==2
    assert result['classes']['caption']['location_recall']==1


def test_merged_detection_not_counted_twice():
    gt=[shape((.1,.1,.35,.35)),shape((.4,.1,.65,.35))]
    prediction=[shape((.08,.08,.69,.39))]
    r=measure_regions(gt,prediction,threshold=.15)
    assert r['tp']==1 and r['fn']==1
    assert r['fusion_risk_prediction_indices']==[0]


def test_missing_false_positives_and_bad_class():
    a=shape((.1,.1,.35,.35),'caption')
    b=shape((.6,.6,.9,.9),'dialogue')
    det=[shape((.1,.1,.35,.35),'dialogue'),shape((.4,.4,.5,.5),'dialogue')]
    r=measure_regions([a,b],det)
    assert (r['tp'],r['fp'],r['fn'])==(1,1,1)
    assert r['kind_correct']==0
    assert r['classes']['caption']['located']==1
    assert r['classes']['dialogue']['located']==0
    assert r['missed_truth_indices']==[1]


def test_empty_metrics_no_division_by_zero():
    r=measure_regions([],[])
    assert r['tp']==r['fp']==r['fn']==0
    assert r['precision'] is None and r['recall'] is None
    assert measure_regions([shape((.1,.1,.5,.5))],[])['recall']==0


def test_real_archive_evaluation_interface_uses_only_annotated_pages(tmp_path):
    buf=io.BytesIO()
    im=Image.new('RGB',(240,180),'black')
    draw=ImageDraw.Draw(im);draw.ellipse((45,35,175,120),fill='white')
    im.save(buf,format='PNG')
    archive=tmp_path/'comic.cbz'
    with zipfile.ZipFile(archive,'w') as zipf:
        zipf.writestr('a.png',buf.getvalue());zipf.writestr('b.png',buf.getvalue())
    labels={'schema':1,'archive_name':'comic.cbz','pages':{'1':{
        'filename':'a.png','width':240,'height':180,
        'regions':[shape((.2,.22,.75,.66))],'verified':True}}}
    result=benchmark_archive(str(archive),labels)
    assert len(result['pages'])==1
    assert result['pages'][0]['truth_count']==1
    assert 'recall' in result['overall']
    labels['pages']['1']['verified']=False
    with pytest.raises(ValueError, match='verified'):benchmark_archive(str(archive),labels)
    labels['pages']['1']['verified']=True
    labels['pages']['1']['filename']='wrong.png'
    with pytest.raises(ValueError):benchmark_archive(str(archive),labels)
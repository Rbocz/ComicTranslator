"""Contract tests for optional ONNX model; do not imply trained-model accuracy."""
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from comictranslate_it.learned_detection import (
    preprocess, postprocess, Detection, make_region_proposals,
    LearnedDetector, ModelNotReady, verify_model_file,
)
from comictranslate_it.annotations import proposal_regions, measure_regions


class _Named:
    def __init__(self,name): self.name=name


class FakeSession:
    """Test only: synthetic ONNX outputs, no weights or model inference."""
    def get_inputs(self):return [_Named('images'),_Named('orig_target_sizes')]
    def get_outputs(self):return [_Named('labels'),_Named('boxes'),_Named('scores')]
    def run(self,names,feed):
        assert names==['labels','boxes','scores']
        assert feed['images'].shape==(1,3,640,640)
        assert feed['images'].dtype==np.float32
        assert np.array_equal(feed['orig_target_sizes'],[[200,120]])
        return [np.array([[0,1,2,1]]),
                np.array([[[20,10,130,110],[35,30,95,55],
                           [145,40,190,68],[35,30,95,55]]],dtype=np.float32),
                np.array([[.96,.9,.85,.45]],dtype=np.float32)]


def test_preprocess_stretches_rgb_to_640_and_keeps_w_h():
    image=Image.new('RGB',(200,120),(255,0,80))
    data=preprocess(image)
    assert data['images'].shape==(1,3,640,640)
    assert data['images'][0,0,0,0]==1.
    assert data['images'][0,1,0,0]==0.
    assert data['orig_target_sizes'].dtype==np.int64
    assert data['orig_target_sizes'].tolist()==[[200,120]]


def test_postprocess_clamps_and_applies_class_specific_nms():
    data={'labels':np.array([[0,0,1,2,1,9]]),
          'boxes':np.array([[[10,10,300,300],[12,12,295,290],
                             [10,10,40,40],[-5,-1,40,40],
                             [30,30,30,31],[1,1,20,20]]]),
          'scores':np.array([[.95,.8,.9,.6,.8,.99]])}
    out=postprocess(data,100,90)
    assert [(d.cls,d.box) for d in out]==[(0,(10,10,100,90)),
        (1,(10,10,40,40)),(2,(0,0,40,40))]
    with pytest.raises(ValueError):postprocess(data,100,90,score_threshold=2)
    with pytest.raises(ModelNotReady):postprocess({'scores':[1]},100,90)


def test_group_text_in_balloon_and_leave_free_text_to_review():
    entries=[Detection(0,.95,(20,10,130,110)),
             Detection(1,.9,(35,30,95,55)),
             Detection(2,.85,(145,40,190,68))]
    proposals=make_region_proposals(entries,(200,120))
    assert len(proposals)==2
    dialogue=next(p for p in proposals if p['kind']=='dialogue')
    assert dialogue['text_region_count']==1
    assert dialogue['role']=='balloon_box_approx'
    assert dialogue['geometry']=='bounding_box_only'
    assert all(p['needs_review'] for p in proposals)
    assert all(0<=x<=1 for p in proposals for point in p['polygon'] for x in point)


def test_fake_onnx_session_is_compatible_but_not_accuracy_benchmark():
    detector=LearnedDetector('unused.onnx',session=FakeSession())
    image=Image.new('RGB',(200,120),'white')
    regions=proposal_regions(image,'onnx',detector)
    assert len(regions)==2
    assert {r['kind'] for r in regions}=={'dialogue','art_text'}
    with pytest.raises(ValueError):proposal_regions(image,'onnx',None)
    with pytest.raises(ValueError):proposal_regions(image,'made_up')


def test_model_verification_rejects_untrusted_binary(tmp_path):
    path=tmp_path/'model.onnx';path.write_bytes(b'untrusted file')
    assert not verify_model_file(path)
    with pytest.raises(ModelNotReady):LearnedDetector(path)


def test_geometry_metrics_use_reviewed_annotation_not_synthetic_claim():
    gt=[{'kind':'dialogue','polygon':[[.1,.1],[.5,.1],[.5,.6],[.1,.6]]}]
    pred=[{'kind':'dialogue','polygon':[[.1,.1],[.5,.1],[.5,.6],[.1,.6]],
           'source':'mock','needs_review':True}]
    metrics=measure_regions(gt,pred)
    assert metrics['recall']==1
    assert metrics['precision']==1
    assert metrics['tp']==1
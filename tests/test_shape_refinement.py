"""Synthetic smoke tests: no commercial scans or learned weights in public CI."""
import numpy as np
from PIL import Image, ImageDraw
from comictranslate_it.shape_refinement import refine_light_surface
from comictranslate_it.learned_detection import Detection, make_region_proposals, LearnedDetector
from comictranslate_it.annotations import copy_proposals_as_draft


def balloon():
    img=Image.new('RGB',(460,300),(67,93,117))
    p=ImageDraw.Draw(img)
    p.rounded_rectangle((90,65,340,195),radius=25,fill='white',outline='black',width=5)
    p.polygon([(248,190),(292,248),(279,189)],fill='white')
    p.line([(248,190),(292,248)],fill='black',width=5)
    p.line([(292,248),(279,189)],fill='black',width=5)
    for y in (100,121,142):p.line((135,y,290,y),fill='black',width=4)
    return img


def test_light_contour_can_include_tail():
    hit=refine_light_surface(balloon(),(132,92,300,155))
    assert hit is not None
    poly,quality=hit
    assert len(poly)>=5 and quality>.7
    assert max(y for x,y in poly)>220
    assert min(x for x,y in poly)<120


def test_on_dark_art_and_white_page_gutter_falls_back_to_box():
    assert refine_light_surface(Image.new('RGB',(400,250),(65,82,97)),
                                (110,80,260,180)) is None
    assert refine_light_surface(Image.new('RGB',(400,200),'white'),
                                (120,70,260,130)) is None


def test_neural_box_and_contour_are_distinct_unapproved_suggestions():
    img=balloon()
    candidates=[Detection(1,.92,(135,91,295,152))]
    plain=make_region_proposals(candidates,img.size)
    refined=make_region_proposals(candidates,img.size,image=img)
    assert plain[0]['geometry']=='bounding_box_only'
    assert refined[0]['geometry']=='light_surface_candidate'
    assert refined[0]['contour_quality']>.67
    assert len(refined[0]['polygon'])>=5
    assert refined[0]['needs_review']


def test_detail_mode_uses_full_page_and_four_tiles():
    class Port:
        def __init__(self,name):self.name=name
    class Session:
        def __init__(self):self.runs=0
        def get_inputs(self):return [Port('images'),Port('orig_target_sizes')]
        def get_outputs(self):return [Port('labels'),Port('boxes'),Port('scores')]
        def run(self,names,feed):
            self.runs+=1
            assert feed['images'].shape==(1,3,640,640)
            return [np.array([[1]]),np.array([[[20,20,90,65]]],np.float32),
                    np.array([[.95]],np.float32)]
    session=Session()
    detector=LearnedDetector('unused.onnx',session=session)
    hits=detector.detections(Image.new('RGB',(1024,1280),'white'),detail_pass=True)
    assert session.runs==5
    assert len(hits)>=3
    assert any(d.box[0]>350 and d.box[1]>400 for d in hits)


def test_copy_does_not_approve_or_duplicate_drafts():
    page={'regions':[], 'verified':True}
    candidate={'kind':'dialogue','polygon':[[.1,.1],[.4,.1],[.4,.4],[.1,.4]]}
    assert copy_proposals_as_draft(page,[candidate])==1
    assert page['verified'] is False
    assert page['regions'][0]['needs_review']
    assert copy_proposals_as_draft(page,[candidate])==0
    assert len(page['regions'])==1

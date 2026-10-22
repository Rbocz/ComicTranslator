"""Offline full-chapter contract tests; no actual paid API calls."""
import io
import json
import zipfile
import pytest
from PIL import Image,ImageDraw
from comictranslate_it.full_translate import (
    _box, _parse_response, recognize_translate, regions_from_response,
    translate_chapter,export_chapter, ServiceError, analyze_page,
)
from comictranslate_it.project import Project

PAYLOAD={'regions':[{'original':'HELLO, BRUCE.','italian':'CIAO, BRUCE.',
 'container_box':[150,160,850,740],
 'line_boxes':[[250,360,700,430]],
 'certainty':96,'uppercase':True,'kind':'dialogue'}]}


def page():
    img=Image.new('RGB',(700,500),'#576674')
    draw=ImageDraw.Draw(img)
    draw.rounded_rectangle((90,68,610,420),radius=60,fill='white',outline='black',width=6)
    draw.text((240,200),'HELLO, BRUCE.',fill='black')
    return img


def test_vision_schema_and_bounds():
    assert _box([-1,2,300,400],700,500) is None
    assert _box([1,2,0,4],700,500) is None
    r=regions_from_response(PAYLOAD['regions'],page().size)
    assert len(r)==1 and r[0].approved
    assert r[0].original=='HELLO, BRUCE.'
    assert r[0].italian=='CIAO, BRUCE.'
    assert r[0].words
    assert regions_from_response([dict(PAYLOAD['regions'][0],certainty=30)],(700,500))[0].approved is False
    assert regions_from_response([dict(PAYLOAD['regions'][0],line_boxes=[[0,0,1000,1000]])],(700,500))[0].approved is False


def test_parse_openai_and_gemini_with_fake_client():
    def openai(url,payload,headers):
        assert url.endswith('/chat/completions') and headers['Authorization']=='Bearer TOKEN'
        assert payload['messages'][1]['content'][1]['type']=='image_url'
        return {'choices':[{'message':{'content':json.dumps(PAYLOAD)}}]}
    def gemini(url,payload,headers):
        assert ':generateContent' in url and headers['x-goog-api-key']=='TOKEN'
        assert payload['contents'][0]['parts'][1]['inline_data']['mime_type']=='image/jpeg'
        return {'candidates':[{'content':{'parts':[{'text':'```json\n'+json.dumps(PAYLOAD)+'\n```'}]}}]}
    for provider,client in [('OpenAI',openai),('Google Gemini',gemini)]:
        out=recognize_translate(page(),provider,'TOKEN','test-model','',client)
        assert out==PAYLOAD['regions']
    with pytest.raises(ServiceError):_parse_response('not json')
    with pytest.raises(ServiceError):_parse_response('{"not_regions":[]}')


def test_multiview_coordinate_mapping():
    image=page().resize((900,1600))
    def stub(url,payload,headers):
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(PAYLOAD)}]}}]}
    # Full page + 2 cropped vertical tiles; boxes map to original coordinate system.
    results=analyze_page(image,'Google Gemini','KEY','gemini-2.5-flash',accurate=True,http_client=stub)
    assert len(results)>=2
    assert all(r.balloon.y1>=0 and r.balloon.y2<=image.height for r in results)


def test_whole_chapter_resume_and_export(tmp_path):
    cbz=tmp_path/'demo.cbz';img=page()
    with zipfile.ZipFile(cbz,'w') as z:
        for i in range(1,4):
            buf=io.BytesIO();img.save(buf,format='PNG');z.writestr(f'p{i:03}.png',buf.getvalue())
    seen=[]
    def stub(url,payload,headers):
        seen.append(url)
        return {'choices':[{'message':{'content':json.dumps(PAYLOAD)}}]}
    project_file=tmp_path/'work'/ 'comic.project.json'
    project,status,errors=translate_chapter(str(cbz),str(project_file),'OpenAI','KEY','gpt-4.1-mini',
                                             accurate=False,http_client=stub)
    assert len(seen)==3 and status.pages_done==3 and not errors
    assert len(project.pages)==3
    assert all(len(p.regions)==1 for p in project.pages)
    out=tmp_path/'comic_it.cbz'
    reports=export_chapter(project,str(out))
    assert out.exists()
    assert len(reports)==3
    with zipfile.ZipFile(out) as z:
        assert len(z.namelist())==3
        assert any(entry['modified'] for entry in reports)
    again,status2,_=translate_chapter(str(cbz),str(project_file),'OpenAI','KEY','gpt-4.1-mini',
                                       accurate=False,http_client=stub)
    assert len(seen)==3 and status2.pages_done==3  # Resumed from checkpoint, zero paid calls
    assert again.pages[0].regions[0].italian=='CIAO, BRUCE.'


def test_billing_error_stops_future_requests_and_keeps_source(tmp_path):
    cbz=tmp_path/'demo.cbz';buf=io.BytesIO();page().save(buf,'PNG')
    with zipfile.ZipFile(cbz,'w') as z:
        for i in range(3):z.writestr(f'{i:02}.png',buf.getvalue())
    def err(*a,**k):raise ServiceError('API HTTP 429 quota limit')
    path=tmp_path/'work.json'
    project,status,errors=translate_chapter(str(cbz),str(path),'OpenAI','KEY','gpt-4.1-mini',
                                             accurate=False,http_client=err)
    assert status.pages_done==1 and status.failed==1 and len(errors)==1
    assert all(not pg.regions for pg in project.pages)
    assert cbz.is_file() and zipfile.is_zipfile(cbz)
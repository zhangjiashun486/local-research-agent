import json

from fastapi.testclient import TestClient
from local_app.api import app
from local_app import research

client=TestClient(app)

def test_invalid_depth_and_short_topic_are_rejected():
    assert client.post('/research',json={'topic':'x','loops':0}).status_code==422

def test_unknown_report_returns_404(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    assert client.get('/reports/not-real').status_code==404

def test_completed_report_survives_new_connection(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    monkeypatch.setattr(research,'load_model_settings',lambda:{'base_url':'http://127.0.0.1:1235/v1','model':'test-model'})
    monkeypatch.setattr(research.graph,'invoke',lambda *args,**kwargs:{'search_status':'success','research_loop_count':1,'running_summary':'Report with source','error_message':''})
    response=client.post('/research',json={'topic':'Python typing','loops':1})
    assert response.status_code==200
    saved=client.get('/reports/'+response.json()['id']).json()
    assert saved['status']=='completed' and saved['report']=='Report with source'
    assert client.get('/reports/'+saved['id']+'/download').text=='Report with source'


def test_missing_model_configuration_is_saved_as_failed_report(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    def missing_config():
        raise ValueError('Set LOCAL_RESEARCH_MODEL')
    monkeypatch.setattr(research,'load_model_settings',missing_config)
    response=client.post('/research',json={'topic':'Python typing','loops':1})
    assert response.status_code==200
    result=response.json()
    assert result['status']=='failed' and 'LOCAL_RESEARCH_MODEL' in result['error']
    assert client.get('/reports/'+result['id']).json()['status']=='failed'


def test_check_endpoint_scores_saved_report(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    report='## Summary\n'+'正文内容足够长。'*40+'\n\n ### Sources:\n* doc : https://example.com/doc'
    (tmp_path/'abc123.json').write_text(json.dumps({
        'id':'abc123','topic':'Python typing','status':'completed',
        'requested_loops':1,'actual_loops':1,'report':report,'error':'','seconds':1.5,
    },ensure_ascii=False),encoding='utf-8')
    response=client.get('/reports/abc123/check')
    assert response.status_code==200
    body=response.json()
    assert body['id']=='abc123' and body['total']==7 and body['passed']==7
    assert 'checks' in body and len(body['checks'])==7


def test_check_endpoint_returns_404_for_unknown(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    assert client.get('/reports/not-a-report/check').status_code==404


def test_check_endpoint_rejects_path_traversal(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    assert client.get('/reports/..%2f..%2fetc/check').status_code==404


def test_source_policy_filters_before_graph(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    monkeypatch.setattr(research,'load_model_settings',lambda:{'base_url':'http://127.0.0.1:1235/v1','model':'test-model'})
    captured={}
    def fake_invoke(state,config):
        captured['sources']=config['configurable'].get('source_urls')
        return {'search_status':'success','research_loop_count':1,'running_summary':'ok','error_message':''}
    monkeypatch.setattr(research.graph,'invoke',fake_invoke)
    urls=['https://a.com/1','https://a.com/2','https://a.com/3','https://b.com/1','https://a.com/1']
    result=research.run_research('topic',1,urls)
    assert captured['sources']==['https://a.com/1','https://a.com/2','https://b.com/1']
    assert [d['reason'] for d in result['sources_dropped']]==['同一域名最多 2 条','重复链接']


def test_all_sources_dropped_fails_without_calling_graph(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    called={'n':0}
    def boom(*a,**k):
        called['n']+=1
        raise AssertionError('graph should not be called')
    monkeypatch.setattr(research.graph,'invoke',boom)
    result=research.run_research('topic',1,['ftp://a.com/x'])
    assert result['status']=='failed'
    assert '来源策略' in result['error']
    assert result['sources_kept']==[]
    assert called['n']==0


def test_compare_endpoint_returns_diff(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    report='## Summary\n'+'正文内容足够长。'*40+'\n\n ### Sources:\n* a : https://a.example/x'
    base={'topic':'Python typing','status':'completed','requested_loops':1,'actual_loops':1,
          'error':'','seconds':1.0}
    (tmp_path/'a.json').write_text(json.dumps({**base,'id':'a','report':report},ensure_ascii=False),encoding='utf-8')
    (tmp_path/'b.json').write_text(json.dumps({**base,'id':'b','report':report+'\n* c : https://c.example/z'},ensure_ascii=False),encoding='utf-8')
    response=client.get('/reports/a/compare/b')
    assert response.status_code==200
    body=response.json()
    assert body['citations']['added']==['https://c.example/z']
    assert body['verdict']=='more_citations'


def test_compare_endpoint_404_when_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    assert client.get('/reports/a/compare/missing').status_code==404

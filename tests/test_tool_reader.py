import json
from langchain_core.messages import AIMessage, ToolMessage
from ollama_deep_researcher.configuration import Configuration
from ollama_deep_researcher.source_agent import run_source_agent

URL='https://example.com/article'


class Model:
    def __init__(self,responses):self.responses=iter(responses);self.messages=[]
    def bind_tools(self,*args,**kwargs):return self
    def invoke(self,messages):
        self.messages.append(list(messages))
        return next(self.responses)


def call(url=URL,name='read_webpage',call_id='c1'):
    return AIMessage(content='',tool_calls=[{'name':name,'args':{'url':url,'query':'Python typing'},'id':call_id}])


def reader(url,**kwargs):
    return {'url':url,'title':'Article','content':'Python type hints are not enforced at runtime.','final_url':url,'truncated':False}


def run(model,read=reader):return run_source_agent('Python typing',[URL],Configuration(language='en'),model=model,reader=read)


def test_real_tool_result_goes_back_with_matching_id_before_summary():
    model=Model([call(),AIMessage(content='Type hints are metadata [S1].')])
    result=run(model)
    returned=[m for m in model.messages[1] if isinstance(m,ToolMessage)]
    assert len(returned)==1 and returned[0].tool_call_id=='c1'
    assert json.loads(returned[0].content)['content'].startswith('Python')
    assert result['search_status']=='success'
    assert result['model_calls']==2 and result['tool_trace'][0]['status']=='success'
    assert result['source_excerpts'][0]['url']==URL


def test_model_cannot_skip_source_reading():
    result=run(Model([AIMessage(content='I already know the answer.')]))
    assert result['search_status']=='failed' and not result['running_summary']


def test_unrequested_url_and_unknown_tool_never_execute():
    calls=[]
    def read(*args,**kwargs):calls.append(args);return reader(*args,**kwargs)
    for response in [call('https://other.example/x'),call(name='shell')]:
        result=run(Model([response,AIMessage(content='Done')]),read)
        assert result['search_status']=='failed'
        assert result['tool_trace'][0]['status']=='rejected'
    assert not calls


def test_repeat_reads_are_cached_not_duplicated():
    calls=[]
    def read(url,**kw):calls.append(url);return reader(url)
    model=Model([call(),call(call_id='c2'),AIMessage(content='Grounded summary [S1].')])
    result=run(model,read)
    assert calls==[URL]
    assert result['tool_trace'][1]['status']=='cached'
    returned=[m for m in model.messages[2] if isinstance(m,ToolMessage)]
    assert 'content' not in json.loads(returned[-1].content)


def test_empty_and_failed_sources_cannot_become_factual_success():
    def empty(url,**kw):return {'url':url,'title':'Empty','content':''}
    def fail(*a,**k):raise TimeoutError('timed out')
    for read in (empty,fail):
        result=run(Model([call(),AIMessage(content='Invented answer')]),read)
        assert result['search_status'] in {'empty','failed'} and not result['running_summary']


def test_tool_call_budget_stops_infinite_model_requests():
    result=run(Model([call(call_id=str(i)) for i in range(20)]))
    assert result['search_status']=='failed'
    assert result['model_calls']<=4


def test_invalid_args_and_made_up_citation_are_rejected():
    bad=AIMessage(content='',tool_calls=[{'name':'read_webpage','args':{'url':URL,'extra':'value'},'id':'bad'}])
    assert run(Model([bad,AIMessage(content='Done')]))['tool_trace'][0]['status']=='rejected'
    result=run(Model([call(),AIMessage(content='Made up citation [S9].')]))
    assert result['search_status']=='failed'


def test_api_reader_mode_validation_and_saved_trace(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from local_app.api import app
    from local_app import research
    client=TestClient(app)
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    monkeypatch.setattr(research,'load_model_settings',lambda:{'base_url':'http://localhost/v1','model':'test'})
    seen={}
    def invoke(state,config):
        seen.update(config['configurable'])
        return {'search_status':'success','running_summary':'report','research_loop_count':1,'tool_trace':[{'tool':'read_webpage','status':'success'}],'model_calls':2,'source_excerpts':[{'url':URL,'content':'original'}]}
    monkeypatch.setattr(research.graph,'invoke',invoke)
    assert client.post('/research',json={'topic':'topic','reader_mode':'unknown'}).status_code==422
    assert client.post('/research',json={'topic':'topic','reader_mode':'agent'}).status_code==422
    result=client.post('/research',json={'topic':'topic','reader_mode':'agent','source_urls':[URL]}).json()
    assert seen['reader_mode']=='agent'
    saved=client.get('/reports/'+result['id']).json()
    assert saved['reader_mode']=='agent' and saved['model_calls']==2
    assert saved['tool_trace'][0]['tool']=='read_webpage'


def test_graph_dispatches_to_agent_instead_of_direct_fetch(monkeypatch):
    from ollama_deep_researcher import graph as flow, source_agent
    seen={}
    def agent(topic,urls,config,**kwargs):
        seen.update(topic=topic,urls=urls)
        return {'search_status':'success','error_message':'','running_summary':'Grounded [S1].','research_loop_count':1,'sources_gathered':['* Original : '+URL],'tool_trace':[{'status':'success'}],'model_calls':2}
    monkeypatch.setattr(source_agent,'run_source_agent',agent)
    result=flow.graph.invoke({'research_topic':'topic'},{'configurable':{'search_api':'provided_urls','source_urls':[URL],'reader_mode':'agent'}})
    assert seen=={'topic':'topic','urls':[URL]}
    assert result['model_calls']==2 and URL in result['running_summary']


def test_citation_ids_survive_reverse_read_order_and_partial_failure():
    second='https://example.org/second'
    model=Model([call(second),call(URL,call_id='c2'),AIMessage(content='First source [S1], second [S2].')])
    result=run_source_agent('topic',[URL,second],Configuration(),model=model,reader=reader)
    links='\n'.join(result['sources_gathered'])
    assert f'[S1] Article : {URL}' in links
    assert f'[S2] Article : {second}' in links
    def partial(url,**kwargs):
        if url==URL:raise TimeoutError('first source failed')
        return reader(url)
    model=Model([call(URL),call(second,call_id='c2'),AIMessage(content='Only the second source was read [S2].')])
    result=run_source_agent('topic',[URL,second],Configuration(),model=model,reader=partial)
    assert result['search_status']=='success'
    assert f'[S2] Article : {second}' in '\n'.join(result['sources_gathered'])
    assert URL not in '\n'.join(result['sources_gathered'])

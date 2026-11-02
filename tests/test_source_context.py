import pytest
from ollama_deep_researcher.utils import deduplicate_and_format_sources
from ollama_deep_researcher import graph as flow


def source(body, url='https://example.com/page'):
    return {'title':'Page','url':url,'content':body,'raw_content':body}


def test_body_sent_once_and_per_source_cap_cannot_be_bypassed():
    body='unique-first-paragraph\n'+'x'*9000+'end-outside-budget'
    text=deduplicate_and_format_sources({'results':[source(body)]},1000,True)
    assert text.count('unique-first-paragraph')==1
    assert 'end-outside-budget' not in text
    assert len(text)<4300


def test_all_sources_share_hard_total_context_budget():
    rows=[source(str(i)*10000,f'https://example.com/{i}') for i in range(5)]
    text=deduplicate_and_format_sources({'results':rows},1000,True,max_total_chars=6000)
    assert len(text)<=6000
    assert all(f'https://example.com/{i}' in text for i in range(5))


def test_missing_raw_content_falls_back_without_losing_source():
    row=source('usable content');row['raw_content']=None
    assert 'usable content' in deduplicate_and_format_sources({'results':[row]},1000,True)


@pytest.mark.parametrize('budget',[1,3])
def test_provided_urls_read_once_without_unused_model_query_calls(monkeypatch,budget):
    seen={'reads':0,'summary':0}
    def read(urls):
        seen['reads']+=1
        return {'results':[source('real document text')]}
    def forbidden(*a,**k): raise AssertionError('unused query/reflection called')
    def summary(*a,**k):
        seen['summary']+=1
        return {'running_summary':'A grounded summary'}
    monkeypatch.setattr(flow,'fetch_provided_sources',read)
    monkeypatch.setattr(flow,'generate_search_query_with_structured_output',forbidden)
    monkeypatch.setattr(flow,'summarize_sources',summary)
    # Graph holds registered node functions; stub the actual summary model instead.
    class Model:
        def __init__(self,**kw): pass
        def invoke(self,messages):
            from types import SimpleNamespace
            seen['summary']+=1
            return SimpleNamespace(content='A grounded summary')
    monkeypatch.setattr(flow,'ChatLMStudio',Model)
    result=flow.graph.invoke({'research_topic':'topic'},{'configurable':{'search_api':'provided_urls','source_urls':['https://example.com/page'],'llm_provider':'lmstudio','max_web_research_loops':budget}})
    assert seen=={'reads':1,'summary':1}
    assert result['research_loop_count']==1

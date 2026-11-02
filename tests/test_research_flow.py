import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ollama_deep_researcher.configuration import Configuration
from ollama_deep_researcher import graph as flow


def fake_dependencies(monkeypatch, results=None, error=None):
    calls = {"search": 0, "summary": 0}
    class LocalModel:
        def __init__(self, **kwargs): pass
        def invoke(self, messages):
            prompt = messages[-1].content
            if "query" in prompt.lower():
                return SimpleNamespace(content=json.dumps({"query":"python typing", "follow_up_query":"python type checking"}))
            calls["summary"] += 1
            return SimpleNamespace(content="Sources describe Python type annotations.")
    def search(*args, **kwargs):
        calls["search"] += 1
        if error: raise error
        return {"results": results if results is not None else [{"title":"Python docs","url":"https://docs.python.org/3/library/typing.html","content":"Type hints support static analysis.","raw_content":"Type hints support static analysis."}]}
    monkeypatch.setattr(flow,"ChatLMStudio",LocalModel)
    monkeypatch.setattr(flow,"duckduckgo_search",search)
    return calls


@pytest.mark.parametrize("budget", [1,3])
def test_complete_graph_respects_search_budget(monkeypatch,budget):
    calls=fake_dependencies(monkeypatch)
    result=flow.graph.invoke({"research_topic":"Python type hints"},{"configurable":{"llm_provider":"lmstudio","max_web_research_loops":budget}})
    assert calls["search"] == budget
    assert "https://docs.python.org/3/library/typing.html" in result["running_summary"]


@pytest.mark.parametrize("budget", [0,-1])
def test_nonpositive_budget_is_rejected(budget):
    with pytest.raises(ValidationError):Configuration(max_web_research_loops=budget)


def test_empty_results_do_not_produce_unsourced_model_summary(monkeypatch):
    calls=fake_dependencies(monkeypatch,results=[])
    result=flow.graph.invoke({"research_topic":"Unknown topic"},{"configurable":{"llm_provider":"lmstudio","max_web_research_loops":3}})
    assert calls["search"]==1
    assert calls["summary"]==0
    assert result["search_status"]=="empty"


def test_search_timeout_is_distinct_from_no_results(monkeypatch):
    calls=fake_dependencies(monkeypatch,error=TimeoutError("search timed out"))
    result=flow.graph.invoke({"research_topic":"A topic"},{"configurable":{"llm_provider":"lmstudio"}})
    assert calls["search"]==1
    assert result["search_status"]=="failed"
    assert "TimeoutError" in result["error_message"]


@pytest.mark.parametrize("content", ["invalid json", "null", "[]", '{"query":""}'])
def test_invalid_model_json_uses_nonempty_topic_fallback(monkeypatch,content):
    class Broken:
        def invoke(self,messages):return SimpleNamespace(content=content)
    monkeypatch.setattr(flow,"get_llm",lambda cfg:Broken())
    result=flow.generate_search_query_with_structured_output(Configuration(),[],None,"Python", "query","query")
    assert result["search_query"]=="Python"


def test_thinking_prefix_is_removed_before_json_parse(monkeypatch):
    class Reasoning:
        def invoke(self,messages):return SimpleNamespace(content='<think>internal</think>{"query":"actual query"}')
    monkeypatch.setattr(flow,"get_llm",lambda cfg:Reasoning())
    result=flow.generate_search_query_with_structured_output(Configuration(),[],None,"fallback","query","query")
    assert result["search_query"]=="actual query"

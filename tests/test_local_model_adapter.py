from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from ollama_deep_researcher.lmstudio import ChatLMStudio

def test_json_schema_format_and_flat_chat_result(monkeypatch):
    captured={}
    def generate(self,messages,*args,**kwargs):
        captured.update(kwargs)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='```json\n{"query":"Python"}\n```'))])
    monkeypatch.setattr(ChatOpenAI,'_generate',generate)
    model=ChatLMStudio(base_url='http://127.0.0.1:1235/v1',model='qwen3.5-9b',format='json')
    result=model._generate([HumanMessage(content='Return JSON')])
    assert captured['response_format']['type']=='json_schema'
    assert result.generations[0].message.content=='{"query":"Python"}'

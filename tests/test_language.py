import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from local_app import research
from local_app.api import app
from local_app.quality import check_report
from ollama_deep_researcher.configuration import Configuration
from ollama_deep_researcher import graph as flow
from ollama_deep_researcher.state import SummaryState


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_language_reaches_graph_and_survives_storage(monkeypatch, tmp_path, language):
    monkeypatch.setattr(research, 'OUTPUT', tmp_path)
    monkeypatch.setattr(research, 'load_model_settings', lambda: {'base_url': 'http://localhost/v1', 'model': 'test'})
    seen = {}
    def invoke(state, config):
        seen.update(config['configurable'])
        return {'search_status': 'success', 'running_summary': 'report', 'research_loop_count': 1}
    monkeypatch.setattr(research.graph, 'invoke', invoke)
    client = TestClient(app)
    response = client.post('/research', json={'topic': 'Python typing', 'source_urls': ['https://docs.python.org/3/library/typing.html'], 'language': language})
    assert response.status_code == 200
    data = response.json()
    assert seen.get('language') == language
    assert data['language'] == language
    assert client.get('/reports/' + data['id']).json()['language'] == language
    assert client.get('/reports').json()[0]['language'] == language
    assert json.loads((tmp_path / (data['id'] + '.json')).read_text(encoding='utf-8'))['language'] == language


def test_unknown_language_is_rejected():
    with pytest.raises(ValidationError):
        Configuration(language='fr')
    assert TestClient(app).post('/research', json={'topic': 'Python typing', 'language': 'fr'}).status_code == 422


def test_legacy_database_migrates_without_guessing_language(monkeypatch, tmp_path):
    monkeypatch.setattr(research, 'OUTPUT', tmp_path)
    with sqlite3.connect(tmp_path / 'research.sqlite3') as conn:
        conn.execute('CREATE TABLE reports (id TEXT PRIMARY KEY, topic TEXT NOT NULL, status TEXT NOT NULL, loops INTEGER NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL, error TEXT NOT NULL, seconds REAL NOT NULL)')
        conn.execute('INSERT INTO reports VALUES (?,?,?,?,?,?,?,?)', ('old', 'old topic', 'completed', 1, '2026-10-01', 'original report', '', 1))
    data = research.get_report('old')
    assert data['report'] == 'original report'
    assert 'language' in data and data['language'] is None
    assert research.list_reports()[0]['language'] is None


@pytest.mark.parametrize('language,heading', [('zh', '## 研究总结'), ('en', '## Summary')])
def test_generated_summary_has_language_instruction_and_headings(monkeypatch, language, heading):
    seen = []
    class Model:
        def __init__(self, **kwargs): pass
        def invoke(self, messages):
            seen.extend(m.content for m in messages)
            return SimpleNamespace(content='summary body')
    monkeypatch.setattr(flow, 'ChatLMStudio', Model)
    cfg = {'configurable': {'llm_provider': 'lmstudio', 'language': language}}
    state = SummaryState(research_topic='topic', search_status='success', web_research_results=['source text'], sources_gathered=['* Docs : https://docs.python.org/3/'])
    state.running_summary = flow.summarize_sources(state, cfg)['running_summary']
    assert ('简体中文' if language == 'zh' else 'English') in '\n'.join(seen)
    assert ('简体中文' if language == 'zh' else 'English') in seen[-1]
    report = flow.finalize_summary(state, cfg)['running_summary']
    assert report.startswith(heading + '\n')
    assert ('### 参考来源：' if language == 'zh' else '### Sources:') in report


def test_chinese_report_passes_same_structure_rules():
    result = {'report': '## 研究总结\n' + '资料中的相关信息。' * 40 + '\n### 参考来源：\n* Docs : https://docs.python.org/3/', 'status': 'completed', 'requested_loops': 1, 'actual_loops': 1, 'error': ''}
    checked = check_report(result)
    assert checked['passed'] == checked['total']


def test_api_omitted_language_keeps_english_default():
    from local_app.api import Request
    assert Request(topic='topic').language == 'en'

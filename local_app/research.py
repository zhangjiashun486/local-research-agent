from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import time
import uuid
from contextlib import closing

from ollama_deep_researcher.graph import graph
from .settings import load_model_settings
from .policy import DEFAULT_POLICY, apply_source_policy, explain

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'outputs'


def connection():
    OUTPUT.mkdir(exist_ok=True)
    conn=sqlite3.connect(OUTPUT/'research.sqlite3',isolation_level=None)
    conn.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, topic TEXT NOT NULL, status TEXT NOT NULL, loops INTEGER NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL, error TEXT NOT NULL, seconds REAL NOT NULL)')
    # Serialize additive migration; old reports retain NULL (unknown) language.
    try:
        conn.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in conn.execute('PRAGMA table_info(reports)')}
        if 'language' not in columns:
            conn.execute('ALTER TABLE reports ADD COLUMN language TEXT')
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    return conn


def run_research(topic:str,loops:int=1,source_urls=None,policy=None,language:str="en",reader_mode:str="direct")->dict:
    if language not in {"zh", "en"}:
        raise ValueError("Unsupported report language")
    if reader_mode not in {"direct", "agent"} or (reader_mode == "agent" and not source_urls):
        raise ValueError("Invalid reader mode or missing source URLs")
    flow_result={}
    job_id=uuid.uuid4().hex
    created=datetime.now(timezone.utc).isoformat()
    started=time.perf_counter()
    settings={'model': ''}
    kept, dropped = [], []
    if source_urls:
        kept, dropped = apply_source_policy(source_urls, policy or DEFAULT_POLICY)
        source_urls = kept
    try:
        if source_urls is not None and not kept and dropped:
            raise ValueError('来源策略过滤掉了全部链接：' + explain(dropped))
        settings=load_model_settings()
        config={'configurable':{'llm_provider':'lmstudio','lmstudio_base_url':settings['base_url'],'local_llm':settings['model'],'max_web_research_loops':loops,'fetch_full_page':False,'disable_reasoning':True,'max_output_tokens':768,'language':language,'reader_mode':reader_mode}}
        if source_urls:
            config['configurable'].update(search_api='provided_urls',source_urls=source_urls)
        result=graph.invoke({'research_topic':topic},config)
        flow_result=result
        status='completed' if result['search_status']=='success' else result['search_status']
        report=result['running_summary'];error=result.get('error_message','');actual_loops=result['research_loop_count']
    except Exception as exc:
        status='failed';report='';error=f'{type(exc).__name__}: {exc}';actual_loops=0
    elapsed=round(time.perf_counter()-started,3)
    result={'language':language,'id':job_id,'topic':topic,'status':status,'model':settings['model'],'requested_loops':loops,'actual_loops':actual_loops,'mode':'provided_urls' if source_urls else 'web_search','created_at':created,'report':report,'error':error,'seconds':elapsed,
            'sources_kept':kept,'sources_dropped':[{'url':d.url,'reason':d.reason} for d in dropped]}
    result.update(reader_mode=reader_mode, **{key:flow_result.get(key, default) for key,default in [('tool_trace',[]),('source_excerpts',[]),('model_calls',0),('context_chars',0)]})
    with closing(connection()) as conn:
        conn.execute('INSERT INTO reports (id,topic,status,loops,created_at,report,error,seconds,language) VALUES (?,?,?,?,?,?,?,?,?)',(job_id,topic,status,actual_loops,created,report,error,elapsed,language))
    (OUTPUT/(job_id+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUTPUT/(job_id+'.md')).write_text(report or error,encoding='utf-8')
    return result


def get_report(report_id:str):
    with closing(connection()) as conn:
        row=conn.execute('SELECT id,topic,status,loops,created_at,report,error,seconds,language FROM reports WHERE id=?',(report_id,)).fetchone()
    if not row:
        return None
    result=dict(zip(['id','topic','status','actual_loops','created_at','report','error','seconds','language'],row))
    from .quality import load_result
    metadata=load_result(OUTPUT,report_id) or {}
    for key in ('reader_mode','tool_trace','source_excerpts','model_calls','context_chars'):
        if key in metadata:result[key]=metadata[key]
    return result


def list_reports():
    with closing(connection()) as conn:
        rows=conn.execute('SELECT id,topic,status,loops,created_at,seconds,language FROM reports ORDER BY created_at DESC LIMIT 30').fetchall()
    return [dict(zip(['id','topic','status','actual_loops','created_at','seconds','language'],row)) for row in rows]

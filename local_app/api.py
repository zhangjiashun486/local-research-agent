from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from pydantic import BaseModel, Field, model_validator
from . import research as research_mod
from .research import run_research, get_report, list_reports
from .quality import check_report, load_result
from .compare import compare_reports

app=FastAPI(title='Local Research Agent',version='0.1.0')

class Request(BaseModel):
    language:Literal["zh", "en"]="en"
    reader_mode:Literal["direct", "agent"]="direct"
    topic:str=Field(min_length=3,max_length=300)
    loops:int=Field(default=1,ge=1,le=3)
    source_urls:list[str]=Field(default_factory=list,max_length=5)

    @model_validator(mode='after')
    def require_sources_for_agent(self):
        if self.reader_mode == 'agent' and not self.source_urls:
            raise ValueError('Tool reading requires supplied source URLs')
        return self

@app.get('/health')
def health():return {'status':'ok','provider':'local Bionic OpenAI-compatible API'}

@app.get('/i18n.js',include_in_schema=False)
def translations():
    return FileResponse(Path(__file__).parent/'i18n.js',media_type='text/javascript')

@app.get('/favicon.ico',include_in_schema=False)
def favicon():
    return FileResponse(Path(__file__).parent/'favicon.ico',media_type='image/x-icon')

@app.post('/research')
def research(request:Request):return run_research(request.topic,request.loops,request.source_urls,language=request.language,reader_mode=request.reader_mode)

@app.get('/reports')
def reports():return list_reports()

@app.get('/reports/{report_id}')
def report(report_id:str):
    result=get_report(report_id)
    if result is None:raise HTTPException(404,'Report not found')
    return result

@app.get('/reports/{report_id}/download',response_class=PlainTextResponse)
def download(report_id:str):return report(report_id)['report']

@app.get('/reports/{report_id}/check')
def report_check(report_id:str):
    data=load_result(research_mod.OUTPUT,report_id)
    if data is None:
        row=get_report(report_id)
        if row is None:raise HTTPException(404,'Report not found')
        data=row
    return check_report(data)

@app.get('/reports/{report_id}/compare/{other_id}')
def report_compare(report_id:str,other_id:str):
    before=load_result(research_mod.OUTPUT,report_id)
    after=load_result(research_mod.OUTPUT,other_id)
    if before is None or after is None:raise HTTPException(404,'Report not found')
    return compare_reports(before,after)

@app.get('/',response_class=HTMLResponse)
def index():return (Path(__file__).parent/'index.html').read_text(encoding='utf-8')

@app.get('/data-demo')
def data_demo():
    path=Path(__file__).resolve().parents[2]/'beginner-de-project/outputs/demo-20261013/dashboard.html'
    if not path.exists():raise HTTPException(404,'Run the data pipeline first')
    return FileResponse(path)

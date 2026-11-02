import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_app.research import run_research

parser=argparse.ArgumentParser()
parser.add_argument('--topic',default='How Python type annotations differ from runtime validation')
parser.add_argument('--loops',type=int,default=1)
parser.add_argument('--source',action='append',default=[])
args=parser.parse_args()
result=run_research(args.topic,args.loops,args.source)
print(json.dumps({k:v for k,v in result.items() if k!='report'},ensure_ascii=False,indent=2))
print(result['report'][:2000])
raise SystemExit(0 if result['status']=='completed' else 1)

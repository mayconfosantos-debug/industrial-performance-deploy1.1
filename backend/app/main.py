"""Industrial Performance API v1.0.4 — evidence-first screens and scoped filters."""
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import pandas as pd
from .data import load_book, active_path, simulate, central_data, SHEETS
from .analytics_v104 import subset, enrich, drill, DRILL_SOURCES

app=FastAPI(title='Industrial Performance API',version='1.0.4')

class SimulationRequest(BaseModel):
    plant:str='Planta Campinas'
    targets:dict[str,float]
    start:str|None=None
    end:str|None=None

class PublishRequest(BaseModel):
    path:str


def scoped(start=None,end=None):
    try:return subset(load_book(),start,end)
    except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc

@app.get('/health')
def health():return {'status':'ok','version':'1.0.4','active_base':active_path().name,'persistence':'demo_read_only'}

@app.get('/api/plants')
def plants():
    b=load_book();df=b.get('PCP',pd.DataFrame());vals=[] if df.empty else sorted(df.Fabrica.dropna().astype(str).unique().tolist())
    dates=sorted(pd.to_datetime(df.Data).dt.to_period('M').astype(str).unique().tolist()) if not df.empty else []
    return {'plants':vals,'months':dates,'active_base':active_path().name}

@app.get('/api/bootstrap/{screen}')
def bootstrap(screen:str,plant:str='Planta Campinas',start:str|None=None,end:str|None=None):
    if screen not in DRILL_SOURCES and screen not in {'alavancas','central-dados','qualidade-dados','mapeamentos','plano-acao','agente','relatorios','meu-plano','ajuda'}:raise HTTPException(404,'Tela desconhecida')
    book=scoped(start,end);raw=load_book();df=raw.get('PCP',pd.DataFrame());vals=[] if df.empty else sorted(df.Fabrica.dropna().astype(str).unique().tolist())
    selected=plant if plant in vals else (vals[0] if vals else plant)
    dates=sorted(pd.to_datetime(df.Data).dt.to_period('M').astype(str).unique().tolist()) if not df.empty else []
    payload=enrich(screen,book,selected,start,end)
    return {'plants':vals,'months':dates,'plant':selected,'active_base':active_path().name,'data':payload,'version':'1.0.4'}

@app.get('/api/dashboard/{screen}')
def get_dashboard(screen:str,plant:str='Planta Campinas',start:str|None=None,end:str|None=None):return enrich(screen,scoped(start,end),plant,start,end)

@app.get('/api/drilldown/{screen}')
def drilldown(screen:str,plant:str='Planta Campinas',dimension:str='',value:str='',start:str|None=None,end:str|None=None,limit:int=75):
    try:return drill(scoped(start,end),screen,plant,dimension,value,start,end,limit)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@app.post('/api/simulate')
def simulation(req:SimulationRequest):
    if any(not -1e12<v<1e12 for v in req.targets.values()):raise HTTPException(422,'Meta fora dos limites do simulador')
    return simulate(scoped(req.start,req.end),req.plant,req.targets)

@app.get('/api/data-lake')
def data_lake():
    result=central_data(load_book());result.update({'storage_status':'DEMO — somente leitura','publishable':False,'persistent':False,'message':'Upload e publicação durável requerem storage e controle de acesso. A Vercel não garante persistência de arquivos locais.'});return result

@app.post('/api/data-lake/upload',status_code=501)
async def upload_workbook(file:UploadFile=File(...)):
    raise HTTPException(501,'Publicação desabilitada no demo: falta storage persistente e autenticação. Nenhum upload será apresentado como publicado.')

@app.post('/api/data-lake/publish',status_code=501)
def publish(req:PublishRequest):
    raise HTTPException(501,'Publicação desabilitada no demo: storage persistente e controle de acesso pendentes.')

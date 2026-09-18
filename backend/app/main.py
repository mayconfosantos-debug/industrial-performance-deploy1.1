from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil, uuid
import pandas as pd
from typing import Optional

from .data import dashboard, dashboard_from_book, load_book, active_path, set_active, simulate, central_data, DATA_DIR, SHEETS, plant_filter, records

app = FastAPI(title="Industrial Performance API", version="1.0.4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimulationRequest(BaseModel):
    plant: str = "Planta Campinas"
    targets: dict[str, float]
    date_start: Optional[str] = None
    date_end: Optional[str] = None

@app.get("/health")
def health():
    return {"status":"ok","version":"1.0.4","active_base":active_path().name}

@app.get("/api/plants")
def plants():
    b=load_book(); df=b.get("PCP")
    vals=[] if df is None or df.empty else sorted(df["Fabrica"].dropna().astype(str).unique().tolist())
    return {"plants":vals,"active_base":active_path().name}


DATE_COLUMNS = ("Data", "Competencia")

def scoped_book(book, date_start=None, date_end=None):
    if not (date_start or date_end): return book
    try:
        start=pd.Timestamp(date_start) if date_start else None
        end=pd.Timestamp(date_end) if date_end else None
    except (ValueError,TypeError): raise HTTPException(400,"Data inválida. Use YYYY-MM-DD.")
    if start is not None and end is not None and start>end: raise HTTPException(400,"Período inicial posterior ao final.")
    out={}
    for sheet,df in book.items():
        col=next((c for c in DATE_COLUMNS if c in df.columns),None)
        if col is None or df.empty: out[sheet]=df;continue
        dates=pd.to_datetime(df[col],errors="coerce")
        mask=pd.Series(True,index=df.index)
        if start is not None:mask &= dates>=start
        if end is not None:mask &= dates<=end
        out[sheet]=df.loc[mask].copy()
    return out

def available_months(book):
    df=book.get("DRE_Gerencial",pd.DataFrame())
    if df.empty:return []
    return sorted(pd.to_datetime(df["Competencia"],errors="coerce").dropna().dt.strftime("%Y-%m").unique().tolist())

@app.get("/api/bootstrap/{screen}")
def bootstrap(screen: str, plant: str="Planta Campinas", date_start:Optional[str]=None,date_end:Optional[str]=None):
    raw=load_book(); df=raw.get("PCP")
    vals=[] if df is None or df.empty else sorted(df["Fabrica"].dropna().astype(str).unique().tolist())
    selected=plant if plant in vals else (vals[0] if vals else plant)
    book=scoped_book(raw,date_start,date_end)
    result=dashboard_from_book(screen,selected,book)
    return {"plants":vals,"plant":selected,"active_base":active_path().name,"months":available_months(raw),
            "scope":{"date_start":date_start,"date_end":date_end},"data":result}

@app.get("/api/dashboard/{screen}")
def get_dashboard(screen:str,plant:str="Planta Campinas",date_start:Optional[str]=None,date_end:Optional[str]=None):
    return dashboard_from_book(screen,plant,scoped_book(load_book(),date_start,date_end))

@app.post("/api/simulate")
def post_simulate(req:SimulationRequest):
    return simulate(scoped_book(load_book(),req.date_start,req.date_end),req.plant,req.targets)

DRILL_ALLOWED={
 "pcp":{"PCP"},"oee":{"Producao","Qualidade","Manutencao","Custos"},
 "capacidade":{"Capacidade","PCP"},"materiais":{"Supply","Padroes_Produto"},
 "logistica":{"Logistica","Pedidos_Logistica"},"financas":{"DRE_Gerencial","Custos"},
 "diagnostico":{"Producao","Qualidade","Manutencao","Capacidade","Supply","Pedidos_Logistica","PCP","DRE_Gerencial"},
 "cockpit":{"PCP","Producao","Qualidade","Capacidade","Pedidos_Logistica","DRE_Gerencial","Supply","Logistica"},
 "multiplantas":{"PCP","Producao","DRE_Gerencial","Cadastro_Dimensoes"},
 "alavancas":{"DRE_Gerencial","Capacidade","Padroes_Produto"},
 "central-dados":set(SHEETS),"qualidade-dados":set(SHEETS),"mapeamentos":set(SHEETS)
}

@app.get("/api/drilldown/{screen}")
def drilldown(screen:str,sheet:str,plant:str="Planta Campinas",field:Optional[str]=None,value:Optional[str]=None,
              date_start:Optional[str]=None,date_end:Optional[str]=None):
    if sheet not in DRILL_ALLOWED.get(screen,set()): raise HTTPException(400,"Fonte não liberada para este módulo.")
    book=scoped_book(load_book(),date_start,date_end)
    df=book.get(sheet,pd.DataFrame())
    if df.empty:return {"source":sheet,"count":0,"records":[],"message":"Sem registros no período/planta selecionados."}
    plant_col="Planta" if sheet=="DRE_Gerencial" else "Fabrica"
    if plant_col in df.columns and screen!="multiplantas":df=plant_filter(df,plant,plant_col)
    if field:
        if field not in df.columns:raise HTTPException(400,f"Coluna '{field}' não existe na fonte {sheet}.")
        df=df[df[field].astype(str)==str(value)]
    cols=[c for c in df.columns if c not in {'Grupo'}]
    numeric=[c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and c not in {'Semana_ISO'}]
    sums={c:float(pd.to_numeric(df[c],errors="coerce").sum()) for c in numeric}
    return {"source":sheet,"field":field,"value":value,"plant":plant,"count":len(df),"shown":min(len(df),80),
            "columns":cols,"totals":sums,"records":records(df[cols],80),
            "message":"Primeiras 80 linhas exibidas; totais cobrem todos os registros filtrados." if len(df)>80 else "Todos os registros filtrados exibidos."}

@app.get("/api/data-lake")
def data_lake():
    return central_data(load_book())

@app.post("/api/data-lake/upload")
async def upload_workbook(file: UploadFile = File(...)):
    suffix=Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx",".xls"}:
        raise HTTPException(400,"Nesta primeira versão publicável, o workbook ativo deve ser Excel. CSV/PDF/imagens entram no RAW, mas ainda não podem substituir o Standard Model sem mapeamento.")
    raise HTTPException(501,"Publicação persistente indisponível neste deploy serverless. Configurar storage privado antes de habilitar uploads de clientes.")

class PublishRequest(BaseModel):
    path: str

@app.post("/api/data-lake/publish")
def publish(req: PublishRequest):
    raise HTTPException(501,"Publicação exige armazenamento privado persistente e controle por organização; recurso ainda não habilitado.")


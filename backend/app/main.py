from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil, uuid
import pandas as pd

from .data import dashboard, dashboard_from_book, load_book, active_path, set_active, simulate, central_data, agent_query, DATA_DIR, SHEETS

app = FastAPI(title="Industrial Performance API", version="1.0.6")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimulationRequest(BaseModel):
    plant: str = "Planta Campinas"
    targets: dict[str, float]

@app.get("/health")
def health():
    return {"status":"ok","version":"1.0.6","active_base":active_path().name}

@app.get("/api/plants")
def plants():
    b=load_book(); df=b.get("PCP")
    vals=[] if df is None or df.empty else sorted(df["Fabrica"].dropna().astype(str).unique().tolist())
    return {"plants":vals,"active_base":active_path().name}


@app.get("/api/bootstrap/{screen}")
def bootstrap(screen: str, plant: str="Planta Campinas"):
    book=load_book()
    df=book.get("PCP")
    vals=[] if df is None or df.empty else sorted(df["Fabrica"].dropna().astype(str).unique().tolist())
    selected=plant if plant in vals else (vals[0] if vals else plant)
    return {"plants":vals,"plant":selected,"active_base":active_path().name,"data":dashboard_from_book(screen, selected, book)}

@app.get("/api/dashboard/{screen}")
def get_dashboard(screen: str, plant: str="Planta Campinas"):
    return dashboard(screen, plant)

@app.post("/api/simulate")
def post_simulate(req: SimulationRequest):
    return simulate(load_book(), req.plant, req.targets)


class AgentRequest(BaseModel):
    plant: str = "Planta Campinas"
    question: str

@app.post("/api/agent")
def post_agent(req: AgentRequest):
    return agent_query(load_book(), req.plant, req.question)

@app.get("/api/data-lake")
def data_lake():
    return central_data(load_book())

@app.post("/api/data-lake/upload")
async def upload_workbook(file: UploadFile = File(...)):
    suffix=Path(file.filename or "upload.xlsx").suffix.lower()
    if suffix not in {".xlsx",".xls"}:
        raise HTTPException(400,"Nesta primeira versão publicável, o workbook ativo deve ser Excel. CSV/PDF/imagens entram no RAW, mas ainda não podem substituir o Standard Model sem mapeamento.")
    uploads=DATA_DIR/"uploads"; uploads.mkdir(exist_ok=True)
    dest=uploads/f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
    with dest.open("wb") as f: shutil.copyfileobj(file.file,f)
    try:
        xls=pd.ExcelFile(dest); present=set(xls.sheet_names); missing=[s for s in SHEETS if s not in present]
        quality=[]
        for s in xls.sheet_names:
            df=pd.read_excel(dest,sheet_name=s); quality.append({"sheet":s,"rows":len(df),"columns":len(df.columns),"missing_cells":int(df.isna().sum().sum())})
        state="Resolvido" if not missing else "Provável / Confirmar"
        return {"file":dest.name,"path":str(dest),"state":state,"missing_required_sheets":missing,"quality":quality,"publishable":not missing}
    except Exception as e:
        raise HTTPException(400,f"Arquivo recebido no RAW, mas não foi possível interpretar o workbook: {e}")

class PublishRequest(BaseModel):
    path: str

@app.post("/api/data-lake/publish")
def publish(req: PublishRequest):
    p=Path(req.path)
    if not p.exists(): raise HTTPException(404,"Arquivo não encontrado no RAW.")
    xls=pd.ExcelFile(p); missing=[s for s in SHEETS if s not in set(xls.sheet_names)]
    if missing: raise HTTPException(400,{"message":"Workbook não pode ser publicado porque faltam objetos canônicos.","missing":missing})
    set_active(p)
    return {"status":"published","active_base":p.name}

from __future__ import annotations

from pathlib import Path
from typing import Any
from functools import lru_cache
import json
import math
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "active_base.json"
DEFAULT_FILE = DATA_DIR / "Industrial_Performance_Base_Teste_Completa_v073.xlsx"

SHEETS = [
    "Cadastro_Dimensoes","Padroes_Produto","Metas","Producao","Qualidade","Manutencao","Pessoas","Custos","PCP",
    "Capacidade","Supply","Logistica","Pedidos_Logistica","DRE_Gerencial","Responsaveis","Alavancas_Simulador",
    "Premissas_Simulador","Parametros_Diagnostico","Dicionario_Dados"
]


def _clean(v: Any):
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(float(v)) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if pd.isna(v):
        return None
    return v


def records(df: pd.DataFrame, n: int | None = None):
    if n is not None:
        df = df.head(n)
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def active_path() -> Path:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            p = Path(state.get("path", ""))
            if p.exists():
                return p
        except Exception:
            pass
    return DEFAULT_FILE


def set_active(path: Path):
    STATE_FILE.write_text(json.dumps({"path": str(path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_book_cache()


@lru_cache(maxsize=4)
def _load_book_cached(path_str: str, mtime_ns: int) -> dict[str, pd.DataFrame]:
    # Excel é a fonte do MVP, mas não deve ser relido a cada request.
    # A chave usa caminho + mtime: ao trocar/publicar a base, o cache muda automaticamente.
    path = Path(path_str)
    xls = pd.ExcelFile(path)
    out: dict[str, pd.DataFrame] = {}
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(path, sheet_name=sheet)
            for c in df.columns:
                if c in {"Data", "Competencia", "Data_Prometida", "Data_Entrega"}:
                    df[c] = pd.to_datetime(df[c], errors="coerce")
            out[sheet] = df
        except Exception:
            out[sheet] = pd.DataFrame()
    return out


def load_book(path: Path | None = None) -> dict[str, pd.DataFrame]:
    path = (path or active_path()).resolve()
    stat = path.stat()
    return _load_book_cached(str(path), stat.st_mtime_ns)


def clear_book_cache():
    _load_book_cached.cache_clear()


def plant_filter(df: pd.DataFrame, plant: str, col: str = "Fabrica") -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if plant and plant not in {"Todas","Todos","Grupo"} and col in df.columns:
        return df[df[col].astype(str) == plant].copy()
    return df.copy()


def month_label(dt) -> str:
    if pd.isna(dt):
        return ""
    return pd.Timestamp(dt).strftime("%b/%y")


def _target(book, indicator, default):
    m = book.get("Metas", pd.DataFrame())
    if not m.empty and "Indicador" in m.columns:
        row = m[m["Indicador"].astype(str).str.casefold() == indicator.casefold()]
        if not row.empty:
            return float(row.iloc[0]["Meta"])
    return default


def _dre_plant(book, plant):
    return plant_filter(book.get("DRE_Gerencial", pd.DataFrame()), plant, "Planta")


def _oee_components(book, plant, by_month=False):
    p = plant_filter(book.get("Producao", pd.DataFrame()), plant)
    q = plant_filter(book.get("Qualidade", pd.DataFrame()), plant)
    if p.empty or q.empty:
        return [] if by_month else {"availability":None,"performance":None,"quality":None,"oee":None}
    if by_month:
        rows=[]
        p=p.copy(); q=q.copy(); p["Month"]=p["Data"].dt.to_period("M").dt.to_timestamp(); q["Month"]=q["Data"].dt.to_period("M").dt.to_timestamp()
        for month in sorted(set(p["Month"].dropna())):
            pm=p[p["Month"]==month]; qm=q[q["Month"]==month]
            hrs=float(pm["Horas_Disponiveis"].sum())
            down=float(pm["Horas_Paradas"].sum())
            availability=1-down/hrs if hrs else np.nan
            weights=pm["Realizado"].clip(lower=0)
            performance=float(np.average(pm["Performance_Calc"],weights=weights)) if weights.sum() else float(pm["Performance_Calc"].mean())
            produced=float(qm["Produzido"].sum()); approved=float(qm["Aprovado"].sum())
            quality=approved/produced if produced else np.nan
            oee=availability*performance*quality
            rows.append({"period":month_label(month),"availability":availability,"performance":performance,"quality":quality,"oee":oee})
        return rows
    hrs=float(p["Horas_Disponiveis"].sum()); down=float(p["Horas_Paradas"].sum())
    availability=1-down/hrs if hrs else np.nan
    weights=p["Realizado"].clip(lower=0)
    performance=float(np.average(p["Performance_Calc"],weights=weights)) if weights.sum() else float(p["Performance_Calc"].mean())
    produced=float(q["Produzido"].sum()); approved=float(q["Aprovado"].sum())
    quality=approved/produced if produced else np.nan
    return {"availability":availability,"performance":performance,"quality":quality,"oee":availability*performance*quality}


def _pcp_metrics(df: pd.DataFrame):
    if df.empty:
        return {"mape":None,"wape":None,"bias":None,"forecast":0,"plan":0,"produced":0,"adherence":None}
    f=df["Forecast"].astype(float); r=df["Produzido"].astype(float)
    ape=[]
    for fv,rv in zip(f,r):
        if rv==0 and fv==0: continue
        if rv==0 and fv>0: continue
        if rv>0 and fv==0: ape.append(1.0)
        elif rv>0: ape.append(abs(rv-fv)/abs(rv))
    mape=float(np.mean(ape)) if ape else np.nan
    denom=float(np.abs(r).sum())
    wape=float(np.abs(r-f).sum()/denom) if denom else np.nan
    bias=float((f-r).sum()/denom) if denom else np.nan
    plan=float(df["MRP_Plano"].sum()); prod=float(df["Produzido"].sum())
    return {"mape":mape,"wape":wape,"bias":bias,"forecast":float(f.sum()),"plan":plan,"produced":prod,"adherence":prod/plan if plan else np.nan}


def _finance_summary(book, plant):
    d=_dre_plant(book,plant)
    if d.empty: return {}
    additive=[
        "Receita_Bruta","Impostos_Deducoes","Receita_Liquida","Insumos_MP","MOD","GGF_Frete","GGF_Energia",
        "GGF_Manutencao","GGF_Contratos_Servicos","GGF_Outros","Margem_Industrial","Custos_Fixos_Industriais",
        "Resultado_Industrial","Desp_Administrativas","Desp_Comerciais","Desp_Logisticas_sem_Frete","Outros_OPEX",
        "EBITDA_Gerencial","Volume_Vendido","Consumo_MP_kg","Consumo_Energia_kWh"
    ]
    vals={c:float(pd.to_numeric(d[c],errors="coerce").fillna(0).sum()) for c in additive if c in d.columns}
    revenue=vals.get("Receita_Liquida",0)
    ebitda=vals.get("EBITDA_Gerencial",0)
    volume=vals.get("Volume_Vendido",0)
    mpkg=vals.get("Consumo_MP_kg",0)
    conv=vals.get("MOD",0)+vals.get("GGF_Frete",0)+vals.get("GGF_Energia",0)+vals.get("GGF_Manutencao",0)+vals.get("GGF_Contratos_Servicos",0)+vals.get("GGF_Outros",0)
    vals["EBITDA_Margem_calc"]=ebitda/revenue if revenue else np.nan
    vals["Custo_Conversao_un"]=conv/volume if volume else np.nan
    # Taxas/preços nunca são somados entre competências.
    vals["Preco_Medio_MP_kg"]=vals.get("Insumos_MP",0)/mpkg if mpkg else np.nan
    for c in ["Estoque_Dias","Prazo_Fornecedor_Dias","Prazo_Cliente_Dias"]:
        if c in d.columns:
            vals[c]=float(pd.to_numeric(d[c],errors="coerce").mean())
    return vals

def cockpit(book, plant):
    comp=_oee_components(book,plant)
    pcp=plant_filter(book.get("PCP",pd.DataFrame()),plant)
    pcp_m=_pcp_metrics(pcp)
    cap=plant_filter(book.get("Capacidade",pd.DataFrame()),plant)
    sup=plant_filter(book.get("Supply",pd.DataFrame()),plant)
    log=plant_filter(book.get("Logistica",pd.DataFrame()),plant)
    fin=_finance_summary(book,plant)
    produced=float(pcp["Produzido"].sum()) if not pcp.empty else 0
    otif=float(log["Pedidos_OTIF"].sum()/log["Pedidos_Total"].sum()) if not log.empty and log["Pedidos_Total"].sum() else np.nan
    cap_util=float(cap["Producao_Real_Un"].sum()/cap["Capacidade_Nominal_Un"].sum()) if not cap.empty and cap["Capacidade_Nominal_Un"].sum() else np.nan
    supply_adh=float(sup["Aderencia_Fornecedor"].mean()) if not sup.empty else np.nan
    supply_cov=float(sup["Cobertura_Dias"].mean()) if not sup.empty else np.nan
    target_oee=_target(book,"OEE",.85); target_pcp=_target(book,"Aderência PCP",.98); target_otif=_target(book,"OTIF",.95); target_cap=_target(book,"Utilização Capacidade",.80)
    # health is normalized achievement, capped to avoid one metric overpowering the index
    ratios={
        "OEE": min((comp["oee"] or 0)/target_oee,1.15),
        "PCP": min((pcp_m["adherence"] or 0)/target_pcp,1.15),
        "Capacidade": min((cap_util or 0)/target_cap,1.15),
        "Materiais": min((supply_adh or 0)/.95,1.15),
        "OTIF": min((otif or 0)/target_otif,1.15),
    }
    weights={"OEE":.35,"PCP":.20,"Capacidade":.15,"Materiais":.15,"OTIF":.15}
    health=sum(ratios[k]*weights[k] for k in weights)*100
    # real monthly series
    oee_month=_oee_components(book,plant,True)
    pcp2=pcp.copy(); log2=log.copy(); d=_dre_plant(book,plant)
    if not pcp2.empty: pcp2["Month"]=pcp2["Data"].dt.to_period("M").dt.to_timestamp()
    if not log2.empty: log2["Month"]=log2["Competencia"].dt.to_period("M").dt.to_timestamp()
    if not d.empty: d=d.copy(); d["Month"]=d["Competencia"].dt.to_period("M").dt.to_timestamp()
    series=[]
    for row in oee_month:
        period=row["period"]; month=pd.to_datetime(period,format="%b/%y")
        pm=pcp2[pcp2["Month"]==month] if not pcp2.empty else pcp2
        lm=log2[log2["Month"]==month] if not log2.empty else log2
        dm=d[d["Month"]==month] if not d.empty else d
        ad=float(pm["Produzido"].sum()/pm["MRP_Plano"].sum()) if not pm.empty and pm["MRP_Plano"].sum() else np.nan
        ot=float(lm["Pedidos_OTIF"].sum()/lm["Pedidos_Total"].sum()) if not lm.empty and lm["Pedidos_Total"].sum() else np.nan
        mg=float(dm["EBITDA_Gerencial"].sum()/dm["Receita_Liquida"].sum()) if not dm.empty and dm["Receita_Liquida"].sum() else np.nan
        series.append({"period":period,"oee":row["oee"],"adherence":ad,"otif":ot,"margin":mg})
    # opportunity values grounded in data
    materials_loss=0
    if not sup.empty:
        materials_loss=float(((sup["Consumo_Real_kg"]-sup["Consumo_Padrao_kg"]).clip(lower=0)*sup["Preco_MP_R$_kg"]).sum())
    orders=plant_filter(book.get("Pedidos_Logistica",pd.DataFrame()),plant)
    logistics_risk=float(orders["Receita_em_Risco_R$"].sum()) if not orders.empty else 0
    cap_margin=(fin.get("Margem_Industrial",0)/fin.get("Volume_Vendido",1)) if fin.get("Volume_Vendido",0) else 0
    capacity_value=float(cap["Volume_Monetizavel_Un"].sum()*cap_margin) if not cap.empty else 0
    pcp_short=max(float(pcp["MRP_Plano"].sum()-pcp["Produzido"].sum()),0) if not pcp.empty else 0
    pcp_value=pcp_short*cap_margin
    # OEE operational exposure based on direct scrap/rework + downtime cost from costs
    q=plant_filter(book.get("Qualidade",pd.DataFrame()),plant); c=plant_filter(book.get("Custos",pd.DataFrame()),plant)
    quality_loss=float(c["Custo_MP"].sum() * (q["Refugo"].sum()/q["Produzido"].sum())) if not c.empty and not q.empty and q["Produzido"].sum() else 0
    maint=float(c["Custo_Manutencao"].sum()) if not c.empty else 0
    oee_value=quality_loss+maint
    opps=[
        {"name":"Perdas de Produção & OEE","pillar":"Produção & OEE","impact":oee_value},
        {"name":"Desvios de materiais","pillar":"Materiais & Supply","impact":materials_loss},
        {"name":"Pedidos logísticos em risco","pillar":"Logística","impact":logistics_risk},
        {"name":"Capacidade monetizável","pillar":"Capacidade","impact":capacity_value},
        {"name":"Baixa aderência ao plano","pillar":"PCP & Aderência","impact":pcp_value},
    ]
    opps=sorted(opps,key=lambda x:x["impact"],reverse=True)
    status=[]
    for name,val,target in [("OEE",comp["oee"],target_oee),("Aderência PCP",pcp_m["adherence"],target_pcp),("Capacidade",cap_util,target_cap),("Aderência fornecedores",supply_adh,.95),("OTIF",otif,target_otif)]:
        state="good" if val is not None and val>=target else "warn" if val is not None and val>=target*.9 else "bad"
        status.append({"name":name,"value":val,"target":target,"state":state})
    # O Cockpit usa o mesmo conjunto monetizado do Diagnóstico para que o Pareto financeiro reconcilie
    # e para não somar receita em risco, causas de OEE e capacidade duas vezes.
    diag=diagnosis_screen(book,plant)
    opps=[{"name":p["problem"],"pillar":p["front"],"impact":p.get("impact",0),"evidence":p.get("evidence")} for p in diag.get("priced_problems",[])[:5]]
    money_total=float(diag.get("cards",{}).get("impact",0) or 0)
    return {
        "plant":plant,"kpis":{"production":produced,"oee":comp["oee"],"adherence":pcp_m["adherence"],"conversion_cost":fin.get("Custo_Conversao_un"),"ebitda":fin.get("EBITDA_Gerencial"),"ebitda_margin":fin.get("EBITDA_Margem_calc"),"otif":otif},
        "series":series,"health":{"score":health,"status":status},"opportunities":opps,"money_total":money_total,
        "pillar":[
            {"name":"PCP & Aderência","value":pcp_m["adherence"],"target":target_pcp},
            {"name":"Produção & OEE","value":comp["oee"],"target":target_oee},
            {"name":"Capacidade","value":cap_util,"target":target_cap},
            {"name":"Materiais & Supply","value":supply_adh,"target":.95},
            {"name":"Logística","value":otif,"target":target_otif},
            {"name":"Finanças & DRE","value":fin.get("EBITDA_Margem_calc"),"target":None},
        ],
        "executive":{"coverage_days":supply_cov,"top":opps[0] if opps else None}
    }


def multiplant(book):
    plants=sorted(book.get("PCP",pd.DataFrame())["Fabrica"].dropna().astype(str).unique().tolist())
    rows=[]
    total_prod=0; total_rev=0; total_ebitda=0
    for p in plants:
        comp=_oee_components(book,p); fin=_finance_summary(book,p); pcp=plant_filter(book.get("PCP",pd.DataFrame()),p)
        prod=float(pcp["Produzido"].sum()) if not pcp.empty else 0; total_prod+=prod; total_rev+=fin.get("Receita_Liquida",0); total_ebitda+=fin.get("EBITDA_Gerencial",0)
        rows.append({"plant":p,"production":prod,"oee":comp["oee"],"availability":comp["availability"],"performance":comp["performance"],"quality":comp["quality"],"conversion_cost":fin.get("Custo_Conversao_un")})
    best=max(rows,key=lambda x:x["oee"] or 0) if rows else None; worst=min(rows,key=lambda x:x["oee"] or 9) if rows else None
    # monthly OEE per plant
    evolution=[]
    for p in plants:
        for r in _oee_components(book,p,True): evolution.append({"plant":p,**r})
    return {"cards":{"plants":len(plants),"worst":worst,"best":best,"production":total_prod,"revenue":total_rev,"ebitda":total_ebitda},"plants":rows,"evolution":evolution}


def pcp_screen(book, plant):
    df=plant_filter(book.get("PCP",pd.DataFrame()),plant)
    metrics=_pcp_metrics(df)
    if df.empty: return {"metrics":metrics,"monthly":[],"family_week":[],"family_month":[],"plant_month":[],"offenders":[]}
    d=df.copy(); d["Month"]=d["Data"].dt.to_period("M").dt.to_timestamp()
    monthly=[]
    for m,g in d.groupby("Month"):
        mm=_pcp_metrics(g); monthly.append({"period":month_label(m),**mm})
    family_week=[]
    for (fam,w),g in d.groupby(["Familia","Semana_ISO"]):
        family_week.append({"family":fam,"week":w,"wape":_pcp_metrics(g)["wape"]})
    family_month=[]
    for (fam,m),g in d.groupby(["Familia","Month"]): family_month.append({"family":fam,"period":month_label(m),**_pcp_metrics(g)})
    allpcp=book.get("PCP",pd.DataFrame()).copy(); allpcp["Month"]=allpcp["Data"].dt.to_period("M").dt.to_timestamp()
    plant_month=[]
    for (p,m),g in allpcp.groupby(["Fabrica","Month"]): plant_month.append({"plant":p,"period":month_label(m),**_pcp_metrics(g)})
    # sku offenders by contribution to absolute error
    denom=float(np.abs(d["Produzido"]).sum()) or 1
    offs=[]
    for (sku,fam),g in d.groupby(["SKU","Familia"]):
        abs_err=float(np.abs(g["Produzido"]-g["Forecast"]).sum())
        met=_pcp_metrics(g)
        offs.append({"sku":sku,"family":fam,"wape_contribution":abs_err/denom,"bias":met["bias"],"volume":float(g["Produzido"].sum())})
    offs=sorted(offs,key=lambda x:x["wape_contribution"],reverse=True)
    return {"metrics":metrics,"monthly":monthly,"family_week":family_week,"family_month":family_month,"plant_month":plant_month,"offenders":offs[:10]}


def oee_screen(book, plant):
    comp=_oee_components(book,plant); trend=_oee_components(book,plant,True)
    p=plant_filter(book.get("Producao",pd.DataFrame()),plant); q=plant_filter(book.get("Qualidade",pd.DataFrame()),plant); m=plant_filter(book.get("Manutencao",pd.DataFrame()),plant); c=plant_filter(book.get("Custos",pd.DataFrame()),plant)
    production=float(p["Realizado"].sum()) if not p.empty else 0
    # equipment downtime top10
    eq=[]
    if not m.empty:
        for machine,g in m.groupby("Maquina"):
            eq.append({"equipment":machine,"hours":float(g["Duracao_Horas"].sum()),"cause":str(g["Causa"].mode().iloc[0]) if not g["Causa"].mode().empty else ""})
        eq=sorted(eq,key=lambda x:x["hours"],reverse=True)[:10]
    availability=[]
    if not m.empty:
        for cause,g in m.groupby("Causa"):
            hours=float(g["Duracao_Horas"].sum()); availability.append({"cause":cause,"hours":hours,"share":hours/float(m["Duracao_Horas"].sum())})
        availability=sorted(availability,key=lambda x:x["hours"],reverse=True)
    performance=[]
    if not p.empty:
        for line,g in p.groupby("Linha"):
            loss=float(((g["Velocidade_Nominal"]-g["Velocidade_Real"]).clip(lower=0)*g["Realizado"]).sum())
            performance.append({"cause":f"Baixa velocidade — {line}","units":loss})
        performance=sorted(performance,key=lambda x:x["units"],reverse=True)
    quality=[]
    if not q.empty:
        for prod,g in q.groupby("Produto"):
            quality.append({"cause":f"Refugo / retrabalho — {prod}","units":float(g["Refugo"].sum()+g["Retrabalho"].sum()),"scrap":float(g["Refugo"].sum()),"rework":float(g["Retrabalho"].sum())})
        quality=sorted(quality,key=lambda x:x["units"],reverse=True)
    line_rows=[]
    if not p.empty:
        for line,g in p.groupby("Linha"):
            qg=q[q["Linha"]==line]; hrs=float(g["Horas_Disponiveis"].sum()); av=1-float(g["Horas_Paradas"].sum())/hrs if hrs else np.nan
            perf=float(np.average(g["Performance_Calc"],weights=g["Realizado"])) if g["Realizado"].sum() else float(g["Performance_Calc"].mean())
            qual=float(qg["Aprovado"].sum()/qg["Produzido"].sum()) if not qg.empty and qg["Produzido"].sum() else np.nan
            line_rows.append({"line":line,"oee":av*perf*qual,"availability":av,"performance":perf,"quality":qual})
    impact=float(c["Custo_Manutencao"].sum()) if not c.empty else 0
    if not c.empty and not q.empty and q["Produzido"].sum(): impact += float(c["Custo_MP"].sum()*(q["Refugo"].sum()/q["Produzido"].sum()))
    return {"kpis":{"oee":comp["oee"],"availability":comp["availability"],"performance":comp["performance"],"quality":comp["quality"],"production":production,"impact":impact},"trend":trend,"equipment":eq,"availability_offenders":availability[:8],"performance_offenders":performance[:8],"quality_offenders":quality[:8],"lines":line_rows}


def capacity_screen(book, plant):
    d=plant_filter(book.get("Capacidade",pd.DataFrame()),plant)
    if d.empty: return {}
    cap=float(d["Capacidade_Nominal_Un"].sum()); prod=float(d["Producao_Real_Un"].sum()); idle=float(d["Capacidade_Ociosa_Un"].sum()); rec=float(d["Capacidade_Tecnicamente_Recuperavel_Un"].sum()); dem=float(d["Demanda_Confirmada_Un"].sum()); mon=float(d["Volume_Monetizavel_Un"].sum())
    monthly=[]
    for m,g in d.groupby("Competencia"):
        c=float(g["Capacidade_Nominal_Un"].sum()); p=float(g["Producao_Real_Un"].sum()); monthly.append({"period":month_label(m),"capacity":c,"production":p,"utilization":p/c if c else np.nan})
    resource=[]
    for line,g in d.groupby("Linha"):
        c=float(g["Capacidade_Nominal_Un"].sum()); p=float(g["Producao_Real_Un"].sum()); resource.append({"line":line,"utilization":p/c if c else np.nan,"capacity":c,"status":"Gargalo" if p/c>=.9 else "Atenção" if p/c>=.8 else "Normal"})
    base_util=prod/cap if cap else 0
    scenarios=[]
    for util in [base_util,.75,.80,.85,.90]:
        out=cap*util; scenarios.append({"utilization":util,"production":out,"gain":max(out-prod,0)})
    fin=_finance_summary(book,plant); margin_unit=fin.get("Margem_Industrial",0)/(fin.get("Volume_Vendido",1) or 1)
    return {"kpis":{"capacity":cap,"production":prod,"utilization":base_util,"idle":idle,"potential":max(cap*.80-prod,0)},"monthly":monthly,"resources":sorted(resource,key=lambda x:x["utilization"],reverse=True),"scenarios":scenarios,"money":{"idle":idle,"recoverable":rec,"demand":dem,"monetizable":mon,"margin_unit":margin_unit,"impact":mon*margin_unit}}


def materials_screen(book, plant):
    d=plant_filter(book.get("Supply",pd.DataFrame()),plant)
    if d.empty:return {}
    std=float(d["Consumo_Padrao_kg"].sum()); real=float(d["Consumo_Real_kg"].sum()); dev=((d["Consumo_Real_kg"]-d["Consumo_Padrao_kg"]).clip(lower=0)*d["Preco_MP_R$_kg"])
    coverage=float(d["Cobertura_Dias"].mean()); critical=int((d["Risco"]=="Alto").sum()); adherence=float(d["Aderencia_Fornecedor"].mean())
    monthly=[]
    for m,g in d.groupby("Competencia"): monthly.append({"period":month_label(m),"standard":float(g["Consumo_Padrao_kg"].sum()),"actual":float(g["Consumo_Real_kg"].sum())})
    mat=[]
    for material,g in d.groupby("Material"):
        impact=float(((g["Consumo_Real_kg"]-g["Consumo_Padrao_kg"]).clip(lower=0)*g["Preco_MP_R$_kg"]).sum())
        mat.append({"material":material,"impact":impact,"deviation":float((g["Consumo_Real_kg"].sum()/g["Consumo_Padrao_kg"].sum()-1) if g["Consumo_Padrao_kg"].sum() else 0),"family":str(g["Familia_Material"].mode().iloc[0]),"evidence":str(g["Evidencia"].mode().iloc[0])})
    mat=sorted(mat,key=lambda x:x["impact"],reverse=True)
    supply=[]
    for material,g in d.groupby("Material"):
        supply.append({"material":material,"supplier":str(g["Fornecedor"].mode().iloc[0]),"coverage":float(g["Cobertura_Dias"].mean()),"lead_time":float(g["Lead_Time_Dias"].mean()),"adherence":float(g["Aderencia_Fornecedor"].mean()),"risk":str(g["Risco"].mode().iloc[0]),"impact_production":float(g["Impacto_Producao_Un"].sum())})
    return {"kpis":{"standard_unit":std/float(plant_filter(book.get("Producao",pd.DataFrame()),plant)["Realizado"].sum()),"actual_unit":real/float(plant_filter(book.get("Producao",pd.DataFrame()),plant)["Realizado"].sum()),"deviation_value":float(dev.sum()),"coverage":coverage,"critical":critical,"supplier_adherence":adherence},"monthly":monthly,"materials":mat,"supply":supply,"money":{"emergency":float(d["Compra_Emergencial_R$"].sum()),"excess":float(d["Estoque_Excesso_R$"].sum()),"production_risk_units":float(d["Impacto_Producao_Un"].sum())}}


def logistics_screen(book, plant):
    d=plant_filter(book.get("Logistica",pd.DataFrame()),plant); orders=plant_filter(book.get("Pedidos_Logistica",pd.DataFrame()),plant)
    if d.empty:return {}
    total=float(d["Pedidos_Total"].sum()); otif=float(d["Pedidos_OTIF"].sum()/total) if total else np.nan; on=float(d["Pedidos_On_Time"].sum()/total) if total else np.nan; full=float(d["Pedidos_In_Full"].sum()/total) if total else np.nan
    freight=float(d["Frete_Total"].sum()); units=float(d["Unidades_Entregues"].sum())
    monthly=[]
    for m,g in d.groupby("Competencia"):
        t=float(g["Pedidos_Total"].sum()); monthly.append({"period":month_label(m),"otif":float(g["Pedidos_OTIF"].sum()/t) if t else np.nan,"on_time":float(g["Pedidos_On_Time"].sum()/t) if t else np.nan,"in_full":float(g["Pedidos_In_Full"].sum()/t) if t else np.nan})
    causes=[]
    if not orders.empty:
        bad=orders[orders["Status_OTIF"]!="OTIF"]
        counts=bad.groupby("Causa_Nao_OTIF").size().sort_values(ascending=False)
        for cause,n in counts.items(): causes.append({"cause":cause,"count":int(n),"share":float(n/counts.sum()) if counts.sum() else 0})
    routes=[]
    for route,g in d.groupby("Rota"):
        routes.append({"route":route,"region":str(g["Regiao"].mode().iloc[0]),"freight_unit":float(g["Frete_Total"].sum()/g["Unidades_Entregues"].sum()) if g["Unidades_Entregues"].sum() else np.nan})
    critical=[]
    if not orders.empty:
        critical=records(orders[orders["Status_OTIF"]!="OTIF"].sort_values("Receita_em_Risco_R$",ascending=False)[["Pedido","Cliente","Regiao","Transportadora","Status_OTIF","Receita_em_Risco_R$"]],8)
    return {"kpis":{"otif":otif,"freight_unit":freight/units if units else np.nan,"on_time":on,"logistics_cost":freight,"critical_orders":len(critical),"revenue_risk":float(orders["Receita_em_Risco_R$"].sum()) if not orders.empty else 0},"monthly":monthly,"causes":causes,"routes":sorted(routes,key=lambda x:x["freight_unit"],reverse=True),"critical":critical}


def finance_screen(book, plant):
    d=_dre_plant(book,plant)
    if d.empty:return {}
    f=_finance_summary(book,plant)
    cost_var=f.get("Insumos_MP",0)+f.get("MOD",0)+f.get("GGF_Energia",0)
    ggf=f.get("GGF_Frete",0)+f.get("GGF_Energia",0)+f.get("GGF_Manutencao",0)+f.get("GGF_Contratos_Servicos",0)+f.get("GGF_Outros",0)
    opex=f.get("Desp_Administrativas",0)+f.get("Desp_Comerciais",0)+f.get("Desp_Logisticas_sem_Frete",0)+f.get("Outros_OPEX",0)
    lines=[
        ("Receita Bruta",f.get("Receita_Bruta",0)),("(-) Impostos e deduções",-f.get("Impostos_Deducoes",0)),("Receita Líquida",f.get("Receita_Liquida",0)),
        ("(-) Insumos / MP",-f.get("Insumos_MP",0)),("(-) MOD",-f.get("MOD",0)),("(-) GGF — Frete",-f.get("GGF_Frete",0)),("(-) GGF — Energia",-f.get("GGF_Energia",0)),("(-) GGF — Manutenção",-f.get("GGF_Manutencao",0)),("(-) GGF — Contratos e Serviços",-f.get("GGF_Contratos_Servicos",0)),("(-) GGF — Outros",-f.get("GGF_Outros",0)),
        ("Margem Industrial",f.get("Margem_Industrial",0)),("(-) Custos Fixos Industriais",-f.get("Custos_Fixos_Industriais",0)),("Resultado Industrial",f.get("Resultado_Industrial",0)),("(-) Despesas Administrativas",-f.get("Desp_Administrativas",0)),("(-) Despesas Comerciais",-f.get("Desp_Comerciais",0)),("(-) Despesas Logísticas (sem frete)",-f.get("Desp_Logisticas_sem_Frete",0)),("(-) Outros OPEX",-f.get("Outros_OPEX",0)),("EBITDA Gerencial",f.get("EBITDA_Gerencial",0))]
    trend=[]
    for m,g in d.groupby("Competencia"):
        trend.append({"period":month_label(m),"revenue":float(g["Receita_Liquida"].sum()),"industrial_margin":float(g["Margem_Industrial"].sum()),"ebitda":float(g["EBITDA_Gerencial"].sum())})
    costs=[{"name":"MP","value":f.get("Insumos_MP",0)},{"name":"MOD","value":f.get("MOD",0)},{"name":"GGF","value":ggf},{"name":"Fixos","value":f.get("Custos_Fixos_Industriais",0)},{"name":"OPEX","value":opex}]
    return {"kpis":{"revenue":f.get("Receita_Liquida",0),"industrial_margin":f.get("Margem_Industrial",0),"ebitda":f.get("EBITDA_Gerencial",0),"ebitda_margin":f.get("EBITDA_Margem_calc"),"variable_cost":cost_var,"ggf_freight":ggf,"opex":opex},"dre":[{"line":a,"value":b} for a,b in lines],"trend":trend,"costs":costs}


def diagnosis_screen(book, plant):
    oee = oee_screen(book, plant)
    log = logistics_screen(book, plant)
    mat = materials_screen(book, plant)
    cap = capacity_screen(book, plant)
    pcp = pcp_screen(book, plant)
    fin = _finance_summary(book, plant)
    q = plant_filter(book.get("Qualidade", pd.DataFrame()), plant)

    problems=[]
    total_q_produced = float(q["Produzido"].sum()) if not q.empty else 0
    mp_total = float(fin.get("Insumos_MP", 0) or 0)

    # Qualidade: custo direto de MP associado ao refugo. Retrabalho aparece como evidência, sem custo inventado.
    for x in oee.get("quality_offenders", [])[:4]:
        direct = (float(x.get("scrap",0)) / total_q_produced * mp_total) if total_q_produced else 0
        problems.append({
            "problem": x["cause"], "front":"Produção & OEE", "component":"Qualidade",
            "impact": direct, "monetized": direct > 0, "risk_value": 0,
            "evidence": f"{int(x.get('scrap',0))} un refugo · {int(x.get('rework',0))} un retrabalho",
            "action":"Eliminar a causa dominante de refugo e estabilizar o processo do SKU ofensor.",
            "effort":2, "horizon":"Até 90 dias", "priority":"Alta"
        })
    # Disponibilidade: causa comprovada, mas sem monetização adicional aqui para não duplicar Capacidade.
    for x in oee.get("availability_offenders", [])[:3]:
        problems.append({
            "problem": x["cause"], "front":"Produção & OEE", "component":"Disponibilidade",
            "impact": 0.0, "monetized": False, "risk_value": 0,
            "evidence": f"{float(x.get('hours',0)):.1f} h de parada registradas",
            "action":"Atacar a causa de parada com plano de contenção, causa raiz e rotina de confiabilidade.",
            "effort":3, "horizon":"3–6 meses", "priority":"Alta"
        })
    # Logística: receita em risco fica separada de EBITDA, conforme regra do produto.
    orders = plant_filter(book.get("Pedidos_Logistica", pd.DataFrame()), plant)
    if not orders.empty:
        bad=orders[orders["Status_OTIF"]!="OTIF"]
        for cause,g in bad.groupby("Causa_Nao_OTIF"):
            risk=float(g["Receita_em_Risco_R$"].sum())
            problems.append({
                "problem": str(cause), "front":"Logística", "component":"OTIF",
                "impact":0.0, "monetized":False, "risk_value":risk,
                "evidence":f"{len(g)} pedidos fora de OTIF · R$ {risk:,.0f} de receita em risco",
                "action":"Priorizar pedidos por valor em risco e eliminar a causa recorrente de não-OTIF.",
                "effort":2, "horizon":"Até 90 dias", "priority":"Alta"
            })
    # Materiais: desvio de consumo valorizado diretamente pelo preço da MP.
    for x in mat.get("materials", [])[:4]:
        impact=float(x.get("impact",0) or 0)
        problems.append({
            "problem":f"Desvio de consumo — {x['material']}", "front":"Materiais & Supply", "component":"Consumo MP",
            "impact":impact, "monetized":impact>0, "risk_value":0,
            "evidence":x.get("evidence") or "Desvio medido na base",
            "action":"Revisar padrão, rendimento e perdas físicas do material ofensor; confirmar causa antes de capturar valor.",
            "effort":2, "horizon":"Até 90 dias", "priority":"Alta" if impact>0 else "Média"
        })
    # Capacidade: monetização apenas sobre volume explicitamente monetizável/demand-backed.
    if cap:
        impact=float(cap.get("money",{}).get("impact",0) or 0)
        problems.append({
            "problem":"Capacidade monetizável não capturada", "front":"Capacidade", "component":"Utilização",
            "impact":impact, "monetized":impact>0, "risk_value":0,
            "evidence":f"{cap['money'].get('monetizable',0):.0f} un monetizáveis com demanda",
            "action":"Remover a restrição do recurso gargalo e capturar apenas o volume suportado por demanda confirmada.",
            "effort":4, "horizon":"3–6 meses", "priority":"Alta" if impact>0 else "Média"
        })
    # PCP: gap operacional fica causal; não soma R$ para evitar sobreposição com capacidade/volume.
    if pcp.get("metrics"):
        short=max(float(pcp["metrics"].get("plan",0) or 0)-float(pcp["metrics"].get("produced",0) or 0),0)
        if short>0:
            problems.append({
                "problem":"Gap Plano × Produzido", "front":"PCP & Aderência", "component":"Execução do plano",
                "impact":0.0, "monetized":False, "risk_value":0,
                "evidence":f"{short:.0f} un abaixo do plano no período",
                "action":"Separar restrição de planejamento da restrição de execução e atacar os SKUs de maior contribuição ao gap.",
                "effort":2, "horizon":"Até 90 dias", "priority":"Alta"
            })

    problems=sorted(problems,key=lambda x:(x.get("impact",0),x.get("risk_value",0)),reverse=True)
    fronts=["Produção & OEE","PCP & Aderência","Capacidade","Materiais & Supply","Logística","Finanças & DRE"]
    byfront=[]
    for front in fronts:
        ps=[p for p in problems if p["front"]==front]
        impact=sum(float(p.get("impact",0) or 0) for p in ps)
        risk=sum(float(p.get("risk_value",0) or 0) for p in ps)
        byfront.append({"front":front,"problems":len(ps),"impact":impact,"risk":risk,"potential":impact*.70 if impact else 0,"capture":.70 if impact else None,"status":"evidence" if ps else "no_material_issue"})

    total=sum(x["impact"] for x in byfront)
    revenue_risk=sum(x["risk"] for x in byfront)
    potential=sum(x["potential"] for x in byfront)
    quick=[p for p in problems if p.get("effort",5)<=2 and p.get("horizon")=="Até 90 dias"]
    horizons=[]
    for h in ["Até 90 dias","3–6 meses","6–12 meses"]:
        hp=[p for p in problems if p.get("horizon")==h]
        horizons.append({"horizon":h,"impact":sum(float(p.get("impact",0) or 0) for p in hp),"risk":sum(float(p.get("risk_value",0) or 0) for p in hp),"problems":len(hp)})

    monetized=[p for p in problems if float(p.get("impact",0) or 0)>0]
    top=monetized[0] if monetized else (problems[0] if problems else None)
    front_rank=sorted(byfront,key=lambda x:x["impact"],reverse=True)
    insights=[]
    if top:
        share=float(top.get("impact",0) or 0)/total if total else None
        insights.append({"title":"Maior impacto monetizado","text":f"{top['problem']} lidera o Pareto" + (f" e representa {share*100:.1f}% do impacto monetizado." if share is not None else ".")})
    if front_rank and front_rank[0]["impact"]>0:
        insights.append({"title":"Concentração por frente","text":f"{front_rank[0]['front']} concentra R$ {front_rank[0]['impact']:,.0f} de impacto direto identificado."})
    if revenue_risk>0:
        insights.append({"title":"Receita em risco separada do EBITDA","text":f"Logística possui R$ {revenue_risk:,.0f} de receita em risco; esse valor não é tratado como EBITDA garantido."})
    nonmon=sum(1 for p in problems if not p.get("monetized"))
    if nonmon:
        insights.append({"title":"Causas sem dupla contagem","text":f"{nonmon} causas/evidências permanecem no diagnóstico sem monetização adicional para evitar sobreposição entre causa e efeito."})

    recs=[]
    for i,p in enumerate(problems[:6],1):
        recs.append({"rank":i,"problem":p["problem"],"front":p["front"],"action":p["action"],"impact":p.get("impact",0),"risk_value":p.get("risk_value",0),"horizon":p.get("horizon"),"priority":p.get("priority")})

    return {
        "cards":{"problems":len(problems),"impact":total,"potential":potential,"quick_value":sum(float(p.get("impact",0) or 0)*.70 for p in quick),"actions":len(recs),"payback_months":None,"revenue_risk":revenue_risk},
        "fronts":byfront,"problems":problems[:16],"priced_problems":monetized[:12],"quickwins":quick[:8],"horizons":horizons,
        "insights":insights,"recommendations":recs,
        "risk":{"direct_impact":total,"revenue_risk":revenue_risk,"top_problem":top["problem"] if top else None},
        "assumptions":["Potencial de captura usado no MVP = 70% apenas sobre impactos monetizados; parametrização por tipo de ação continua A VALIDAR.","Receita em risco de OTIF é exibida separadamente e não é somada ao EBITDA.","Causas sem monetização confiável permanecem visíveis como evidência, sem R$ inventado."]
    }

def levers_screen(book, plant):
    f = _finance_summary(book, plant)
    fin = finance_screen(book, plant)
    comp = _oee_components(book, plant)
    cap = plant_filter(book.get("Capacidade", pd.DataFrame()), plant)
    prod = plant_filter(book.get("Producao", pd.DataFrame()), plant)
    std = book.get("Padroes_Produto", pd.DataFrame()).copy()
    if not std.empty and "Fabrica_Padrao" in std.columns:
        stdp = std[std["Fabrica_Padrao"].astype(str) == str(plant)].copy()
        if not stdp.empty:
            std = stdp

    volume = f.get("Volume_Vendido", 0) or 0
    price = f.get("Receita_Liquida", 0) / (volume or 1)
    mp_price = f.get("Preco_Medio_MP_kg", 0) or 0
    mp_consumption = f.get("Consumo_MP_kg", 0) / (volume or 1)
    freight_unit = f.get("GGF_Frete", 0) / (volume or 1)
    contracts = f.get("GGF_Contratos_Servicos", 0) or 0
    fixed = f.get("Custos_Fixos_Industriais", 0) or 0

    # Mix = participação dos produtos de maior margem de contribuição no volume produzido.
    mix = 0.5
    std_mp = None
    high_margin_products: list[str] = []
    if not std.empty and {"Produto", "Margem_Contrib_Padrao_R$_un"}.issubset(std.columns):
        margins = pd.to_numeric(std["Margem_Contrib_Padrao_R$_un"], errors="coerce")
        median_margin = float(margins.median()) if margins.notna().any() else np.nan
        if pd.notna(median_margin):
            high_margin_products = std.loc[margins >= median_margin, "Produto"].astype(str).tolist()
    if not prod.empty and "Produto" in prod.columns and "Realizado" in prod.columns:
        pv = prod.groupby("Produto")["Realizado"].sum()
        if pv.sum() > 0 and high_margin_products:
            mix = float(pv[pv.index.astype(str).isin(high_margin_products)].sum() / pv.sum())
        if not std.empty and "MP_Padrao_kg_un" in std.columns:
            mp_map = dict(zip(std["Produto"].astype(str), pd.to_numeric(std["MP_Padrao_kg_un"], errors="coerce")))
            weighted = []
            weights = []
            for product, qty in pv.items():
                v = mp_map.get(str(product))
                if v is not None and pd.notna(v):
                    weighted.append(float(v)); weights.append(float(qty))
            if weights and sum(weights) > 0:
                std_mp = float(np.average(weighted, weights=weights))

    scrap = 1 - comp["quality"] if comp.get("quality") is not None else 0
    material_loss = max(mp_consumption / std_mp - 1, 0) if std_mp not in (None, 0) else 0
    current = {
        "volume": float(volume), "price": float(price), "mix": float(mix),
        "mp_price": float(mp_price), "mp_consumption": float(mp_consumption),
        "material_loss": float(material_loss), "freight_unit": float(freight_unit),
        "contracts": float(contracts), "fixed": float(fixed),
        "availability": comp.get("availability"), "performance": comp.get("performance"), "scrap": float(scrap),
    }
    suggestions = {
        "volume": float(volume * 1.05), "price": float(price * 1.02), "mix": float(min(.95, mix + .03)),
        "mp_price": float(mp_price * .98),
        "mp_consumption": float(max(std_mp, mp_consumption * .97) if std_mp not in (None, 0) else mp_consumption * .97),
        "freight_unit": float(freight_unit * .95), "contracts": float(contracts * .95), "fixed": float(fixed * .98),
        "availability": float(max(comp.get("availability") or 0, min(.90, (comp.get("availability") or 0) + .025))),
        "performance": float(max(comp.get("performance") or 0, min(.95, (comp.get("performance") or 0) + .025))),
        "scrap": float(min(scrap, .025)),
    }
    return {
        "current": current,
        "suggestions": suggestions,
        "kpis": {"revenue": f.get("Receita_Liquida", 0), "ebitda": f.get("EBITDA_Gerencial", 0), "margin": f.get("EBITDA_Margem_calc")},
        "dre": fin.get("dre", []),
        "capacity": {
            "monetizable": float(cap["Volume_Monetizavel_Un"].sum()) if not cap.empty else 0,
            "demand": float(plant_filter(book.get("PCP", pd.DataFrame()), plant)["Demanda_Confirmada"].sum()) if not plant_filter(book.get("PCP", pd.DataFrame()), plant).empty else 0,
        },
        "assumptions": {
            "std_mp_kg_un": std_mp,
            "high_margin_products": high_margin_products,
            "mix_definition": "participação do volume produzido em SKUs com margem de contribuição padrão >= mediana",
        }
    }


def simulate(book, plant, targets: dict[str, float]):
    base = levers_screen(book, plant)
    cur = base["current"]
    f = _finance_summary(book, plant)
    prod = plant_filter(book.get("Producao", pd.DataFrame()), plant)
    std = book.get("Padroes_Produto", pd.DataFrame()).copy()
    if not std.empty and "Fabrica_Padrao" in std.columns:
        stdp = std[std["Fabrica_Padrao"].astype(str) == str(plant)].copy()
        if not stdp.empty:
            std = stdp

    revenue0 = float(f.get("Receita_Liquida", 0) or 0)
    ebitda0 = float(f.get("EBITDA_Gerencial", 0) or 0)
    volume0 = float(cur.get("volume", 0) or 0)
    opex_parts = ["Desp_Administrativas", "Desp_Comerciais", "Desp_Logisticas_sem_Frete", "Outros_OPEX"]
    opex0 = sum(float(f.get(k, 0) or 0) for k in opex_parts)

    def t(key):
        val = targets.get(key, cur.get(key))
        return float(cur.get(key) if val is None else val)

    volume_t = max(t("volume"), 0)
    price_t = max(t("price"), 0)
    mix_t = min(max(t("mix"), 0), 1)
    mp_price_t = max(t("mp_price"), 0)
    cons_t = max(t("mp_consumption"), 0)
    freight_t = max(t("freight_unit"), 0)
    contracts_t = max(t("contracts"), 0)
    fixed_t = max(t("fixed"), 0)
    A_t = min(max(t("availability"), 0), 1)
    P_t = min(max(t("performance"), 0), 1)
    scrap_t = min(max(t("scrap"), 0), 1)
    Q_t = 1 - scrap_t
    oee_current = float((cur.get("availability") or 0) * (cur.get("performance") or 0) * (1 - (cur.get("scrap") or 0)))
    oee_target = float(A_t * P_t * Q_t)

    # Mix: diferenciais de preço/custo padrão entre SKUs de maior e menor margem.
    dp_mix = 0.0; dvc_mix = 0.0
    high = set(base.get("assumptions", {}).get("high_margin_products") or [])
    if not std.empty and "Produto" in std.columns:
        price_map = dict(zip(std["Produto"].astype(str), pd.to_numeric(std.get("Preco_Liquido_Padrao_R$_un"), errors="coerce")))
        vc_map = dict(zip(std["Produto"].astype(str), pd.to_numeric(std.get("Custo_Variavel_Padrao_R$_un"), errors="coerce")))
        hp = [float(v) for k, v in price_map.items() if k in high and pd.notna(v)]
        lp = [float(v) for k, v in price_map.items() if k not in high and pd.notna(v)]
        hv = [float(v) for k, v in vc_map.items() if k in high and pd.notna(v)]
        lv = [float(v) for k, v in vc_map.items() if k not in high and pd.notna(v)]
        if hp and lp: dp_mix = float(np.mean(hp) - np.mean(lp))
        if hv and lv: dvc_mix = float(np.mean(hv) - np.mean(lv))
    mix_shift = max(-float(cur.get("mix", 0)), min(1 - float(cur.get("mix", 0)), mix_t - float(cur.get("mix", 0))))
    mix_units = volume_t * mix_shift

    desired_inc = max(0.0, volume_t - volume0)
    oee_enabled = max(0.0, volume0 * (oee_target / oee_current - 1)) if oee_current > 0 else 0.0
    demand_backed = float(base.get("capacity", {}).get("monetizable", 0) or 0)
    captured_oee_units = min(desired_inc, oee_enabled, demand_backed if demand_backed > 0 else desired_inc)
    commercial_units = max(0.0, desired_inc - captured_oee_units)

    deductions_rate = float(f.get("Impostos_Deducoes", 0) or 0) / float(f.get("Receita_Bruta", 1) or 1)
    revenue_proj = volume_t * price_t + mix_units * dp_mix
    gross_proj = revenue_proj / (1 - deductions_rate) if deductions_rate < 1 else revenue_proj
    ded_proj = gross_proj - revenue_proj

    std_mp = base.get("assumptions", {}).get("std_mp_kg_un")
    std_mp = float(std_mp) if std_mp not in (None, 0) else float(cur.get("mp_consumption", 0) or 0)
    gross_needed = volume_t / max(1e-9, Q_t)
    scrap_units_proj = max(0.0, gross_needed - volume_t)
    projected_mp_kg = volume_t * cons_t + scrap_units_proj * std_mp
    mp_proj_raw = projected_mp_kg * mp_price_t
    # Calibração ao realizado: a DRE já contém todo o consumo real de MP.
    # O modelo incremental usa a diferença contra o mesmo cálculo no cenário atual,
    # garantindo Atual -> Atual = zero e evitando criar uma perda artificial na base.
    current_scrap = float(cur.get("scrap", 0) or 0)
    current_scrap_units = volume0 / max(1e-9, 1-current_scrap) - volume0
    base_raw_mp_kg = volume0 * float(cur.get("mp_consumption",0) or 0) + current_scrap_units * std_mp
    base_raw_mp_cost = base_raw_mp_kg * float(cur.get("mp_price",0) or 0)
    mp_proj = float(f.get("Insumos_MP",0) or 0) + (mp_proj_raw - base_raw_mp_cost)

    vol_ratio = volume_t / volume0 if volume0 else 1.0
    mod_proj = float(f.get("MOD", 0) or 0) * vol_ratio
    freight_proj = freight_t * volume_t
    energy_proj = float(f.get("GGF_Energia", 0) or 0) * vol_ratio
    availability0 = float(cur.get("availability") or 0)
    maint_proj = float(f.get("GGF_Manutencao", 0) or 0) * max(.82, 1 - (A_t - availability0) * .6) if availability0 else float(f.get("GGF_Manutencao", 0) or 0)
    other_ggf_proj = float(f.get("GGF_Outros", 0) or 0) * vol_ratio

    margin_ind_proj = revenue_proj - mp_proj - mod_proj - freight_proj - energy_proj - maint_proj - contracts_t - other_ggf_proj
    result_ind_proj = margin_ind_proj - fixed_t
    opex_scale = 1 + max(0.0, vol_ratio - 1) * .20
    opex_proj_parts = {k: float(f.get(k, 0) or 0) * opex_scale for k in opex_parts}
    opex_proj = sum(opex_proj_parts.values())
    ebitda_proj = result_ind_proj - opex_proj
    delta_ebitda = ebitda_proj - ebitda0

    # Bridge exclusiva: drivers causais de OEE não recebem R$ separados; capacidade capturada é monetizada uma única vez.
    contribution_margin_unit = (ebitda0 + float(f.get("Custos_Fixos_Industriais", 0) or 0) + opex0) / (volume0 or 1)
    quality_saving = (current_scrap_units - scrap_units_proj) * std_mp * mp_price_t
    bridge = [
        {"key":"oee_capacity","label":"OEE / Capacidade capturada","impact":captured_oee_units * max(0.0, contribution_margin_unit)},
        {"key":"volume","label":"Volume comercial","impact":commercial_units * max(0.0, contribution_margin_unit)},
        {"key":"price","label":"Preço médio","impact":(price_t - float(cur.get("price",0))) * volume_t},
        {"key":"mix","label":"Mix","impact":mix_units * (dp_mix - dvc_mix)},
        {"key":"scrap","label":"Qualidade / Refugo","impact":quality_saving},
        {"key":"mp_price","label":"Preço MP","impact":(volume_t * float(cur.get("mp_consumption",0)) + scrap_units_proj * std_mp) * (float(cur.get("mp_price",0)) - mp_price_t)},
        {"key":"mp_consumption","label":"Consumo MP","impact":volume_t * (float(cur.get("mp_consumption",0)) - cons_t) * mp_price_t},
        {"key":"freight","label":"Frete","impact":(float(cur.get("freight_unit",0)) - freight_t) * volume_t},
        {"key":"contracts","label":"Contratos / serviços","impact":float(cur.get("contracts",0)) - contracts_t},
        {"key":"fixed","label":"Custo fixo","impact":float(cur.get("fixed",0)) - fixed_t},
    ]
    bridge = [{**x, "impact": float(x["impact"])} for x in bridge if abs(float(x["impact"])) > 1e-6]
    residual = float(delta_ebitda - sum(x["impact"] for x in bridge))
    if abs(residual) > 1.0:
        bridge.append({"key":"scale_other","label":"Escala / outros custos","impact":residual})
    reconciliation = float(delta_ebitda - sum(x["impact"] for x in bridge))

    current_lines = {
        "Receita Bruta": float(f.get("Receita_Bruta",0) or 0),
        "(-) Impostos e deduções": -float(f.get("Impostos_Deducoes",0) or 0),
        "Receita Líquida": revenue0,
        "(-) Insumos / MP": -float(f.get("Insumos_MP",0) or 0),
        "(-) MOD": -float(f.get("MOD",0) or 0),
        "(-) GGF — Frete": -float(f.get("GGF_Frete",0) or 0),
        "(-) GGF — Energia": -float(f.get("GGF_Energia",0) or 0),
        "(-) GGF — Manutenção": -float(f.get("GGF_Manutencao",0) or 0),
        "(-) GGF — Contratos e Serviços": -float(f.get("GGF_Contratos_Servicos",0) or 0),
        "(-) GGF — Outros": -float(f.get("GGF_Outros",0) or 0),
        "Margem Industrial": float(f.get("Margem_Industrial",0) or 0),
        "(-) Custos Fixos Industriais": -float(f.get("Custos_Fixos_Industriais",0) or 0),
        "Resultado Industrial": float(f.get("Resultado_Industrial",0) or 0),
        "(-) Despesas Administrativas": -float(f.get("Desp_Administrativas",0) or 0),
        "(-) Despesas Comerciais": -float(f.get("Desp_Comerciais",0) or 0),
        "(-) Despesas Logísticas (sem frete)": -float(f.get("Desp_Logisticas_sem_Frete",0) or 0),
        "(-) Outros OPEX": -float(f.get("Outros_OPEX",0) or 0),
        "EBITDA Gerencial": ebitda0,
    }
    projected_lines = {
        "Receita Bruta": gross_proj, "(-) Impostos e deduções": -ded_proj, "Receita Líquida": revenue_proj,
        "(-) Insumos / MP": -mp_proj, "(-) MOD": -mod_proj, "(-) GGF — Frete": -freight_proj,
        "(-) GGF — Energia": -energy_proj, "(-) GGF — Manutenção": -maint_proj,
        "(-) GGF — Contratos e Serviços": -contracts_t, "(-) GGF — Outros": -other_ggf_proj,
        "Margem Industrial": margin_ind_proj, "(-) Custos Fixos Industriais": -fixed_t,
        "Resultado Industrial": result_ind_proj,
        "(-) Despesas Administrativas": -opex_proj_parts["Desp_Administrativas"],
        "(-) Despesas Comerciais": -opex_proj_parts["Desp_Comerciais"],
        "(-) Despesas Logísticas (sem frete)": -opex_proj_parts["Desp_Logisticas_sem_Frete"],
        "(-) Outros OPEX": -opex_proj_parts["Outros_OPEX"], "EBITDA Gerencial": ebitda_proj,
    }
    order = list(current_lines.keys())
    dre_compare=[]
    for line in order:
        a=current_lines[line]; b=projected_lines[line]; delta=b-a
        dre_compare.append({"line":line,"current":a,"projected":b,"delta":delta,"delta_pct":delta/abs(a) if a else None})

    return {
        "base": base, "targets": targets,
        "oee": {"current": oee_current, "projected": oee_target, "quality": Q_t, "captured_units": captured_oee_units, "commercial_units": commercial_units},
        "impacts": bridge,
        "bridge": {"items": bridge, "reconciliation_diff": reconciliation},
        "dre_compare": dre_compare,
        "ebitda": {
            "current": ebitda0, "projected": ebitda_proj, "delta": delta_ebitda,
            "margin_current": ebitda0/revenue0 if revenue0 else None,
            "margin_projected": ebitda_proj/revenue_proj if revenue_proj else None,
        },
        "revenue_projected": revenue_proj,
    }

def data_quality(book):
    out=[]
    for s,df in book.items():
        if s=="LEIA-ME": continue
        missing=int(df.isna().sum().sum()) if not df.empty else 0
        dup=int(df.duplicated().sum()) if not df.empty else 0
        out.append({"sheet":s,"rows":int(len(df)),"columns":int(len(df.columns)),"missing_cells":missing,"duplicates":dup,"status":"ok" if missing==0 and dup==0 else "attention"})
    return out


def central_data(book):
    p=active_path(); quality=data_quality(book); total_rows=sum(x["rows"] for x in quality)
    return {"active_file":p.name,"path":str(p),"sheets":len(book),"rows":total_rows,"quality":quality,"pipeline":["RAW","Classificação","DE/PARA inteligente","Standard Industrial Model","Data Quality","Semantic/Gold","Motores analíticos"]}


def dashboard_from_book(screen: str, plant: str, book: dict[str, pd.DataFrame]):
    mapping={
        "cockpit":lambda:cockpit(book,plant),"multiplantas":lambda:multiplant(book),"pcp":lambda:pcp_screen(book,plant),"oee":lambda:oee_screen(book,plant),"capacidade":lambda:capacity_screen(book,plant),"materiais":lambda:materials_screen(book,plant),"logistica":lambda:logistics_screen(book,plant),"financas":lambda:finance_screen(book,plant),"diagnostico":lambda:diagnosis_screen(book,plant),"alavancas":lambda:levers_screen(book,plant),"central-dados":lambda:central_data(book)
    }
    if screen not in mapping: return {"status":"planned","screen":screen}
    return mapping[screen]()


def dashboard(screen: str, plant: str):
    return dashboard_from_book(screen, plant, load_book())

# ============================================================================
# v1.0.4 — Full Analytics Parity
# Overrides below intentionally supersede the initial v1.0 migration functions.
# The execution specification is the source of truth: no silent defaults, no
# invented money, no OEE consolidation, and drill-downs must be traceable.
# ============================================================================

def _ratio(a, b):
    try:
        a=float(a); b=float(b)
        return a/b if b else np.nan
    except Exception:
        return np.nan


def _pct_change(cur, prev):
    try:
        cur=float(cur); prev=float(prev)
        return (cur-prev)/abs(prev) if prev else None
    except Exception:
        return None


def _last_two_groups(df: pd.DataFrame, date_col: str):
    if df is None or df.empty or date_col not in df.columns:
        return None, None, None, None
    d=df.dropna(subset=[date_col]).copy()
    if d.empty: return None, None, None, None
    d['_m']=pd.to_datetime(d[date_col]).dt.to_period('M').dt.to_timestamp()
    months=sorted(d['_m'].unique())
    cur_m=months[-1]
    prev_m=months[-2] if len(months)>1 else None
    return d[d['_m']==cur_m].copy(), (d[d['_m']==prev_m].copy() if prev_m is not None else pd.DataFrame()), cur_m, prev_m


def _margin_unit(book, plant):
    f=_finance_summary(book,plant)
    vol=float(f.get('Volume_Vendido',0) or 0)
    return float(f.get('Margem_Industrial',0) or 0)/(vol or 1)


def _variable_cost_unit(book, plant):
    f=_finance_summary(book,plant)
    vol=float(f.get('Volume_Vendido',0) or 0)
    var=float(f.get('Insumos_MP',0) or 0)+float(f.get('MOD',0) or 0)+float(f.get('GGF_Energia',0) or 0)
    return var/(vol or 1)


def _monthly_finance_rows(book, plant):
    d=_dre_plant(book,plant)
    out=[]
    if d.empty: return out
    for m,g in d.groupby('Competencia'):
        rev=float(g['Receita_Liquida'].sum()); mi=float(g['Margem_Industrial'].sum()); eb=float(g['EBITDA_Gerencial'].sum())
        total_cost=rev-eb
        out.append({'period':month_label(m),'revenue':rev,'industrial_margin':mi,'ebitda':eb,'total_cost':total_cost,'ebitda_margin':_ratio(eb,rev)})
    return out


def _direct_financial_problems(book, plant):
    """Unique monetized pressures used consistently by Cockpit/Finance/Diagnosis.
    Revenue risk is kept separate and never added to EBITDA/direct impact.
    """
    oee=oee_screen(book,plant)
    mat=materials_screen(book,plant)
    cap=capacity_screen(book,plant)
    log=logistics_screen(book,plant)
    pcp=pcp_screen(book,plant)
    problems=[]
    for x in oee.get('money',{}).get('items',[]):
        v=float(x.get('value',0) or 0)
        if v>0:
            problems.append({'problem':x['name'],'front':'Produção & OEE','impact':v,'evidence':x.get('evidence'),'path':'/oee'})
    material_direct=float(mat.get('money',{}).get('material_excess',0) or 0)
    emergency=float(mat.get('money',{}).get('emergency',0) or 0)
    if material_direct>0:
        problems.append({'problem':'Consumo de materiais acima do padrão','front':'Materiais & Supply','impact':material_direct,'evidence':'Padrão × real valorizado por preço de MP','path':'/materiais'})
    if emergency>0:
        problems.append({'problem':'Compras emergenciais','front':'Materiais & Supply','impact':emergency,'evidence':'Valor registrado em Supply','path':'/materiais'})
    cap_impact=float(cap.get('money',{}).get('impact',0) or 0)
    if cap_impact>0:
        problems.append({'problem':'Capacidade monetizável não capturada','front':'Capacidade','impact':cap_impact,'evidence':'Volume monetizável × margem industrial/un','path':'/capacidade'})
    # PCP remains risk/causal when the same units are already monetized via capacity/OEE.
    # Logistics has revenue risk, not guaranteed EBITDA, so it is not added here.
    return sorted(problems,key=lambda x:x['impact'],reverse=True)


def multiplant(book):
    pcp_all=book.get('PCP',pd.DataFrame())
    plants=sorted(pcp_all['Fabrica'].dropna().astype(str).unique().tolist()) if not pcp_all.empty else []
    rows=[]; total_prod=0; total_rev=0; total_ebitda=0
    for plant in plants:
        comp=_oee_components(book,plant); fin=_finance_summary(book,plant)
        pcp=plant_filter(pcp_all,plant); pm=_pcp_metrics(pcp)
        log=logistics_screen(book,plant)
        prod=float(pcp['Produzido'].sum()) if not pcp.empty else 0
        total_prod+=prod; total_rev+=float(fin.get('Receita_Liquida',0) or 0); total_ebitda+=float(fin.get('EBITDA_Gerencial',0) or 0)
        cur,prev,cur_m,prev_m=_last_two_groups(pcp,'Data')
        cur_prod=float(cur['Produzido'].sum()) if cur is not None and not cur.empty else 0
        prev_prod=float(prev['Produzido'].sum()) if prev is not None and not prev.empty else 0
        rows.append({
            'plant':plant,'production':prod,'oee':comp.get('oee'),'availability':comp.get('availability'),'performance':comp.get('performance'),'quality':comp.get('quality'),
            'conversion_cost':fin.get('Custo_Conversao_un'),'adherence':pm.get('adherence'),'otif':log.get('kpis',{}).get('otif'),'ebitda_margin':fin.get('EBITDA_Margem_calc'),
            'production_change':_pct_change(cur_prod,prev_prod),'drilldown':f'/cockpit?plant={plant.replace(" ","%20")}'
        })
    valid_oee=[r for r in rows if r.get('oee') is not None and not pd.isna(r.get('oee'))]
    best=max(valid_oee,key=lambda x:x['oee']) if valid_oee else None
    worst=min(valid_oee,key=lambda x:x['oee']) if valid_oee else None
    evolution=[]
    for plant in plants:
        for r in _oee_components(book,plant,True): evolution.append({'plant':plant,**r})
    insights=[]; recs=[]
    if worst:
        gap=max(_target(book,'OEE',.85)-float(worst['oee']),0)
        insights.append({'title':'Prioridade de performance','text':f"{worst['plant']} possui o menor OEE ({worst['oee']*100:.1f}%), gap de {gap*100:.1f} p.p. para a meta de 85%."})
        recs.append({'priority':1,'action':f"Abrir Cockpit e Diagnóstico de {worst['plant']} para decompor o gap de OEE.",'path':worst['drilldown']})
    if rows:
        hi=max([r for r in rows if r.get('conversion_cost') is not None],key=lambda x:x['conversion_cost'],default=None)
        lo=min([r for r in rows if r.get('conversion_cost') is not None],key=lambda x:x['conversion_cost'],default=None)
        if hi and lo:
            spread=_ratio(hi['conversion_cost'],lo['conversion_cost'])-1
            insights.append({'title':'Dispersão de custo','text':f"O custo de conversão varia de R$ {lo['conversion_cost']:.2f}/un ({lo['plant']}) a R$ {hi['conversion_cost']:.2f}/un ({hi['plant']}), diferença de {spread*100:.1f}%."})
            recs.append({'priority':2,'action':f"Comparar drivers de conversão de {hi['plant']} com {lo['plant']} antes de definir meta de redução.",'path':f"/financas?plant={hi['plant'].replace(' ','%20')}"})
        declining=[r for r in rows if r.get('production_change') is not None and r['production_change']<0]
        if declining:
            d=min(declining,key=lambda x:x['production_change'])
            insights.append({'title':'Deterioração de volume','text':f"{d['plant']} apresenta a maior queda de produção no último mês vs. anterior ({d['production_change']*100:.1f}%)."})
    insights.append({'title':'Regra de consolidação','text':'Receita, EBITDA e produção são somados no grupo. OEE permanece exclusivamente planta a planta; não existe OEE médio/consolidado.'})
    return {'cards':{'plants':len(plants),'worst':worst,'best':best,'production':total_prod,'revenue':total_rev,'ebitda':total_ebitda},'plants':rows,'evolution':evolution,'insights':insights,'recommendations':recs,'geo_available':False}


def pcp_screen(book, plant):
    df=plant_filter(book.get('PCP',pd.DataFrame()),plant)
    metrics=_pcp_metrics(df)
    empty={'metrics':metrics,'monthly':[],'family_week':[],'family_month':[],'plant_month':[],'offenders':[],'money':{},'insights':[],'recommendations':[]}
    if df.empty:return empty
    d=df.copy(); d['Month']=d['Data'].dt.to_period('M').dt.to_timestamp()
    monthly=[]
    for m,g in d.groupby('Month'):
        mm=_pcp_metrics(g); monthly.append({'period':month_label(m),**mm,'planning_gap':float(g['MRP_Plano'].sum()-g['Forecast'].sum()),'execution_gap':float(g['Produzido'].sum()-g['MRP_Plano'].sum())})
    family_week=[]
    for (fam,w),g in d.groupby(['Familia','Semana_ISO']):
        family_week.append({'family':fam,'week':w,'wape':_pcp_metrics(g)['wape']})
    family_month=[]
    for fam,g in d.groupby('Familia'):
        family_month.append({'family':fam,**_pcp_metrics(g)})
    allpcp=book.get('PCP',pd.DataFrame()).copy(); allpcp['Month']=allpcp['Data'].dt.to_period('M').dt.to_timestamp()
    plant_month=[]
    for p,g in allpcp.groupby('Fabrica'):
        plant_month.append({'plant':p,**_pcp_metrics(g)})
    denom=float(np.abs(d['Produzido']).sum()) or 1
    offenders=[]
    for (sku,fam),g in d.groupby(['SKU','Familia']):
        abs_err=float(np.abs(g['Produzido']-g['Forecast']).sum()); met=_pcp_metrics(g)
        unexpected=float(g.loc[(g['Forecast']==0)&(g['Produzido']>0),'Produzido'].sum())
        over=float((g['Forecast']-g['Produzido']).clip(lower=0).sum())
        exec_gap=float((g['MRP_Plano']-g['Produzido']).clip(lower=0).sum())
        offenders.append({'sku':sku,'family':fam,'wape_contribution':abs_err/denom,'bias':met['bias'],'volume':float(g['Produzido'].sum()),'abs_error':abs_err,'unexpected_units':unexpected,'overforecast_units':over,'execution_gap_units':exec_gap})
    offenders=sorted(offenders,key=lambda x:x['wape_contribution'],reverse=True)[:10]
    margin_unit=_margin_unit(book,plant)
    demand_short=float((d['Demanda_Confirmada']-d['Produzido']).clip(lower=0).sum())
    demand_risk=demand_short*max(margin_unit,0)
    over_units=float((d['Forecast']-d['Demanda_Confirmada']).clip(lower=0).sum())
    unexpected_units=float(d.loc[(d['Forecast']==0)&(d['Produzido']>0),'Produzido'].sum())
    plan_gap=float((d['MRP_Plano']-d['Produzido']).clip(lower=0).sum())
    fam_rank=sorted(family_month,key=lambda x:(x.get('wape') or 0),reverse=True)
    top_sku=offenders[0] if offenders else None; top_fam=fam_rank[0] if fam_rank else None
    insights=[]
    insights.append({'title':'Qualidade do forecast','text':f"WAPE de {(metrics.get('wape') or 0)*100:.1f}% e Bias de {(metrics.get('bias') or 0)*100:.1f}%. " + ('Há tendência de sobreprevisão.' if (metrics.get('bias') or 0)>0 else 'Há tendência de subprevisão.' if (metrics.get('bias') or 0)<0 else 'Forecast sem viés agregado material.')})
    if top_fam: insights.append({'title':'Família prioritária','text':f"{top_fam['family']} possui o maior WAPE ({(top_fam.get('wape') or 0)*100:.1f}%) no período selecionado."})
    if top_sku: insights.append({'title':'SKU ofensor','text':f"{top_sku['sku']} responde por {(top_sku['wape_contribution'] or 0)*100:.1f} p.p. do erro ponderado absoluto."})
    if demand_risk>0: insights.append({'title':'Demanda confirmada não atendida','text':f"{demand_short:,.0f} un de demanda confirmada ficaram acima do produzido, exposição de margem de {demand_risk:,.0f} R$; risco, não EBITDA realizado."})
    recommendations=[]
    if top_sku: recommendations.append({'priority':1,'action':f"Revisar parâmetros, eventos e forecast do {top_sku['sku']} ({top_sku['family']}).",'drilldown':top_sku['sku']})
    if top_fam: recommendations.append({'priority':2,'action':f"Executar revisão semanal da família {top_fam['family']} até WAPE convergir para a meta."})
    if abs(metrics.get('bias') or 0)>.03: recommendations.append({'priority':3,'action':'Recalibrar viés sistemático antes do próximo ciclo de S&OP/PCP.'})
    recommendations.append({'priority':4,'action':'Separar Forecast→Plano (planejamento) de Plano→Produzido (execução) na rotina de causa.'})
    return {'metrics':metrics,'monthly':monthly,'family_week':family_week,'family_month':family_month,'plant_month':plant_month,'offenders':offenders,
            'money':{'confirmed_demand_short_units':demand_short,'confirmed_demand_margin_risk':demand_risk,'overforecast_units':over_units,'unexpected_units':unexpected_units,'plan_execution_gap_units':plan_gap,'note':'Somente a demanda confirmada não atendida é valorizada como margem em risco. Sobreprevisão e demanda não prevista permanecem em unidades quando não há custo específico na base.'},
            'insights':insights,'recommendations':recommendations,
            'rules':{'mape':'média |Real-Forecast|/|Real| para Real>0; Forecast=0 e Real>0 = 100%; Real=0 e Forecast>0 = N/A','wape':'Σ|Real-Forecast| / Σ|Real|; N/A se ΣReal=0','bias':'Σ(Forecast-Real)/ΣReal; positivo=sobreprevisão, negativo=subprevisão'}}


def oee_screen(book, plant):
    comp=_oee_components(book,plant); trend=_oee_components(book,plant,True)
    p=plant_filter(book.get('Producao',pd.DataFrame()),plant); q=plant_filter(book.get('Qualidade',pd.DataFrame()),plant); m=plant_filter(book.get('Manutencao',pd.DataFrame()),plant); c=plant_filter(book.get('Custos',pd.DataFrame()),plant); pcp=plant_filter(book.get('PCP',pd.DataFrame()),plant)
    production=float(p['Realizado'].sum()) if not p.empty else 0
    good=float(q['Aprovado'].sum()) if not q.empty else production
    A=float(comp.get('availability') or 0); P=float(comp.get('performance') or 0); Q=float(comp.get('quality') or 0); O=A*P*Q
    ideal=good/O if O>0 else good
    loss_av=max(ideal*(1-A),0); loss_perf=max(ideal*A*(1-P),0); loss_qual=max(ideal*A*P*(1-Q),0)
    demand_confirmed=float(pcp['Demanda_Confirmada'].sum()) if not pcp.empty else 0
    demand_gap=max(demand_confirmed-good,0)
    throughput_loss=loss_av+loss_perf
    demand_backed=min(demand_gap,throughput_loss) if throughput_loss>0 else 0
    av_db=demand_backed*(loss_av/throughput_loss) if throughput_loss else 0
    perf_db=demand_backed*(loss_perf/throughput_loss) if throughput_loss else 0
    margin_unit=max(_margin_unit(book,plant),0)
    av_impact=av_db*margin_unit; perf_impact=perf_db*margin_unit
    mp_total=float(c['Custo_MP'].sum()) if not c.empty else 0; qprod=float(q['Produzido'].sum()) if not q.empty else 0
    scrap_total=float(q['Refugo'].sum()) if not q.empty else 0
    quality_direct=(scrap_total/qprod*mp_total) if qprod else 0
    total_impact=av_impact+perf_impact+quality_direct
    # Availability offenders and equipment: allocate only the availability impact by downtime share.
    total_down=float(m['Duracao_Horas'].sum()) if not m.empty else 0
    availability=[]
    if not m.empty:
        for cause,g in m.groupby('Causa'):
            hrs=float(g['Duracao_Horas'].sum()); share=hrs/total_down if total_down else 0
            ev=float((g['Evidencia_Causal'].astype(str).str.casefold()=='sim').mean()) if 'Evidencia_Causal' in g.columns else 0
            availability.append({'cause':cause,'hours':hrs,'share':share,'impact':av_impact*share,'evidence':'Evidenciado' if ev>=.5 else 'Possível causa'})
        availability=sorted(availability,key=lambda x:x['hours'],reverse=True)
    equipment=[]
    if not m.empty:
        for machine,g in m.groupby('Maquina'):
            hrs=float(g['Duracao_Horas'].sum()); share=hrs/total_down if total_down else 0
            cause=str(g['Causa'].mode().iloc[0]) if not g['Causa'].mode().empty else 'N/A'
            ev='Evidenciado' if (g['Evidencia_Causal'].astype(str).str.casefold()=='sim').mean()>=.5 else 'Possível causa'
            equipment.append({'equipment':machine,'hours':hrs,'share':share,'impact':av_impact*share,'cause':cause,'evidence':ev})
        equipment=sorted(equipment,key=lambda x:x['hours'],reverse=True)[:10]
    # Performance offenders by line using unit-equivalent loss derived from measured performance.
    performance=[]
    if not p.empty:
        tmp=[]
        for line,g in p.groupby('Linha'):
            realized=float(g['Realizado'].sum()); weights=g['Realizado'].clip(lower=0)
            perf=float(np.average(g['Performance_Calc'],weights=weights)) if weights.sum() else float(g['Performance_Calc'].mean())
            units=max(realized/perf-realized,0) if perf>0 else 0; tmp.append((line,units))
        denom=sum(x[1] for x in tmp) or 1
        for line,units in tmp: performance.append({'cause':f'Baixa velocidade — {line}','units':units,'share':units/denom,'impact':perf_impact*(units/denom),'evidence':'Velocidade real × nominal'})
        performance=sorted(performance,key=lambda x:x['units'],reverse=True)
    quality=[]
    if not q.empty:
        cprod=c.groupby('Produto').agg({'Custo_MP':'sum'}).reset_index() if not c.empty else pd.DataFrame()
        cmap=dict(zip(cprod['Produto'].astype(str),cprod['Custo_MP'])) if not cprod.empty else {}
        for prod,g in q.groupby('Produto'):
            qp=float(g['Produzido'].sum()); scrap=float(g['Refugo'].sum()); rework=float(g['Retrabalho'].sum())
            cost_mp=float(cmap.get(str(prod),0) or 0); direct=(scrap/qp*cost_mp) if qp else 0
            quality.append({'cause':f'Refugo / retrabalho — {prod}','units':scrap+rework,'scrap':scrap,'rework':rework,'impact':direct,'evidence':'Refugo valorizado por MP; retrabalho sem custo específico'})
        quality=sorted(quality,key=lambda x:x['impact'],reverse=True)
    lines=[]
    if not p.empty:
        for line,g in p.groupby('Linha'):
            qg=q[q['Linha']==line]; hrs=float(g['Horas_Disponiveis'].sum()); av=1-float(g['Horas_Paradas'].sum())/hrs if hrs else np.nan
            perf=float(np.average(g['Performance_Calc'],weights=g['Realizado'].clip(lower=0))) if g['Realizado'].sum() else float(g['Performance_Calc'].mean())
            qual=float(qg['Aprovado'].sum()/qg['Produzido'].sum()) if not qg.empty and qg['Produzido'].sum() else np.nan
            lines.append({'line':line,'oee':av*perf*qual,'availability':av,'performance':perf,'quality':qual,'production':float(g['Realizado'].sum())})
    targets={'oee':_target(book,'OEE',.85),'availability':_target(book,'Disponibilidade',.90),'performance':_target(book,'Performance',.95),'quality':_target(book,'Qualidade',.98)}
    gaps={k:targets[k]-(O if k=='oee' else {'availability':A,'performance':P,'quality':Q}[k]) for k in targets}
    component=max(['availability','performance','quality'],key=lambda k:gaps[k])
    labels={'availability':'Disponibilidade','performance':'Performance','quality':'Qualidade'}
    top_cause=(availability[0] if component=='availability' and availability else performance[0] if component=='performance' and performance else quality[0] if quality else None)
    insights=[{'title':'Gap principal do OEE','text':f"OEE de {O*100:.1f}% está {(targets['oee']-O)*100:.1f} p.p. abaixo da meta. {labels[component]} é o maior gap entre os componentes ({gaps[component]*100:.1f} p.p.)."}]
    if top_cause: insights.append({'title':'Principal ofensor','text':f"{top_cause['cause']} é o maior ofensor do componente prioritário; evidência: {top_cause.get('evidence','N/A')}."})
    insights.append({'title':'Regra financeira','text':f"Disponibilidade e Performance monetizam apenas {demand_backed:,.0f} un suportadas por demanda confirmada. Refugo usa custo direto de MP; não há dupla contagem com OEE."})
    actions=[]
    if availability: actions.append({'priority':1,'action':f"Atacar {availability[0]['cause']} ({availability[0]['hours']:.1f} h) e validar causa raiz no equipamento líder.",'path':'/diagnostico'})
    if performance: actions.append({'priority':2,'action':f"Restaurar velocidade na linha líder de perda: {performance[0]['cause'].replace('Baixa velocidade — ','')}."})
    if quality: actions.append({'priority':3,'action':f"Reduzir refugo do ofensor {quality[0]['cause'].replace('Refugo / retrabalho — ','')} e confirmar parâmetros de processo."})
    return {'kpis':{'oee':O,'availability':A,'performance':P,'quality':Q,'production':production,'impact':total_impact},'targets':targets,'trend':trend,'equipment':equipment,'availability_offenders':availability[:8],'performance_offenders':performance[:8],'quality_offenders':quality[:8],'lines':sorted(lines,key=lambda x:x['oee']),
            'money':{'items':[{'name':'Disponibilidade — margem em risco demand-backed','value':av_impact,'units':av_db,'evidence':'Demanda confirmada + perda de disponibilidade'},{'name':'Performance — margem em risco demand-backed','value':perf_impact,'units':perf_db,'evidence':'Demanda confirmada + perda de performance'},{'name':'Qualidade — custo direto de refugo','value':quality_direct,'units':scrap_total,'evidence':'Refugo × custo de MP'}],'total':total_impact,'ideal_units':ideal,'lost_units':ideal-good,'demand_backed_units':demand_backed},
            'insights':insights,'recommendations':actions}


def capacity_screen(book, plant):
    d=plant_filter(book.get('Capacidade',pd.DataFrame()),plant)
    if d.empty:return {}
    cap=float(d['Capacidade_Nominal_Un'].sum()); prod=float(d['Producao_Real_Un'].sum()); idle=float(d['Capacidade_Ociosa_Un'].sum()); rec=float(d['Capacidade_Tecnicamente_Recuperavel_Un'].sum()); dem=float(d['Demanda_Confirmada_Un'].sum()); mon=float(d['Volume_Monetizavel_Un'].sum())
    monthly=[]
    for m,g in d.groupby('Competencia'):
        c=float(g['Capacidade_Nominal_Un'].sum()); p=float(g['Producao_Real_Un'].sum()); monthly.append({'period':month_label(m),'capacity':c,'production':p,'utilization':_ratio(p,c)})
    resources=[]
    for (line,res),g in d.groupby(['Linha','Recurso']):
        c=float(g['Capacidade_Nominal_Un'].sum()); p=float(g['Producao_Real_Un'].sum()); u=_ratio(p,c)
        declared=str(g['Status_Recurso'].mode().iloc[0]) if not g['Status_Recurso'].mode().empty else ''
        resources.append({'line':line,'resource':res,'utilization':u,'capacity':c,'production':p,'status':declared or ('Gargalo' if u>=.9 else 'Atenção' if u>=.8 else 'Normal')})
    resources=sorted(resources,key=lambda x:x['utilization'] if x['utilization'] is not None else -1,reverse=True)
    base_util=_ratio(prod,cap)
    scenarios=[]
    for util in [base_util,.75,.80,.85,.90]:
        out=cap*util; scenarios.append({'utilization':util,'production':out,'gain':max(out-prod,0)})
    margin_unit=max(_margin_unit(book,plant),0)
    structural=max(idle-rec,0); recoverable_no_demand=max(rec-mon,0); monetizable=max(mon,0)
    losses=[{'cause':'Ociosidade não recuperável tecnicamente','units':structural,'share':_ratio(structural,idle),'type':'structural'},{'cause':'Capacidade recuperável sem demanda monetizável','units':recoverable_no_demand,'share':_ratio(recoverable_no_demand,idle),'type':'demand'},{'cause':'Capacidade recuperável com demanda','units':monetizable,'share':_ratio(monetizable,idle),'type':'monetizable'}]
    bottleneck=resources[0] if resources else None
    insights=[]
    insights.append({'title':'Utilização da capacidade','text':f"A planta utiliza {(base_util or 0)*100:.1f}% da capacidade nominal e mantém {idle:,.0f} un ociosas no período."})
    if bottleneck: insights.append({'title':'Recurso prioritário','text':f"{bottleneck['resource']} ({bottleneck['line']}) apresenta a maior utilização, {(bottleneck['utilization'] or 0)*100:.1f}%, status {bottleneck['status']}."})
    insights.append({'title':'Monetização condicionada à demanda','text':f"Das {rec:,.0f} un tecnicamente recuperáveis, apenas {mon:,.0f} un estão classificadas como monetizáveis; impacto potencial de R$ {mon*margin_unit:,.0f}."})
    recs=[]
    if bottleneck: recs.append({'priority':1,'action':f"Tratar restrição do recurso {bottleneck['resource']} e validar causa operacional no OEE.",'path':'/oee'})
    if recoverable_no_demand>0: recs.append({'priority':2,'action':'Não converter capacidade sem demanda em EBITDA; sincronizar cenário com PCP/comercial.' ,'path':'/pcp'})
    if monetizable>0: recs.append({'priority':3,'action':f"Planejar captura das {monetizable:,.0f} un monetizáveis com margem industrial unitária de R$ {margin_unit:.2f}."})
    return {'kpis':{'capacity':cap,'production':prod,'utilization':base_util,'idle':idle,'potential':max(cap*.80-prod,0)},'monthly':monthly,'resources':resources,'scenarios':scenarios,'bottleneck':bottleneck,'losses':losses,
            'shift_available':False,'shift_message':'Granularidade de turno não disponível na base ativa.',
            'money':{'idle':idle,'recoverable':rec,'demand':dem,'monetizable':mon,'margin_unit':margin_unit,'impact':mon*margin_unit},'insights':insights,'recommendations':recs}


def materials_screen(book, plant):
    d=plant_filter(book.get('Supply',pd.DataFrame()),plant); prod=plant_filter(book.get('Producao',pd.DataFrame()),plant)
    if d.empty:return {}
    std=float(d['Consumo_Padrao_kg'].sum()); real=float(d['Consumo_Real_kg'].sum()); units=float(prod['Realizado'].sum()) if not prod.empty else 0
    dev=((d['Consumo_Real_kg']-d['Consumo_Padrao_kg']).clip(lower=0)*d['Preco_MP_R$_kg'])
    coverage=float(d['Cobertura_Dias'].mean()); critical=int((d['Risco'].astype(str).str.casefold()=='alto').sum()); adherence=float(d['Aderencia_Fornecedor'].mean())
    monthly=[]
    for m,g in d.groupby('Competencia'): monthly.append({'period':month_label(m),'standard':_ratio(float(g['Consumo_Padrao_kg'].sum()), float(plant_filter(prod,plant)['Realizado'].sum()) if False else 1),'standard_total':float(g['Consumo_Padrao_kg'].sum()),'actual_total':float(g['Consumo_Real_kg'].sum())})
    # convert monthly totals to kg/un using production in same month
    if not prod.empty:
        pp=prod.copy(); pp['_m']=pp['Data'].dt.to_period('M').dt.to_timestamp(); pmap=pp.groupby('_m')['Realizado'].sum().to_dict()
        for row,m in zip(monthly,sorted(d['Competencia'].unique())):
            pu=float(pmap.get(pd.Timestamp(m),0) or 0); row['standard']=row.pop('standard_total')/(pu or 1); row['actual']=row.pop('actual_total')/(pu or 1)
    materials=[]
    for material,g in d.groupby('Material'):
        s=float(g['Consumo_Padrao_kg'].sum()); a=float(g['Consumo_Real_kg'].sum()); impact=float(((g['Consumo_Real_kg']-g['Consumo_Padrao_kg']).clip(lower=0)*g['Preco_MP_R$_kg']).sum())
        materials.append({'material':material,'family':str(g['Familia_Material'].mode().iloc[0]),'deviation':_ratio(a,s)-1 if s else None,'impact':impact,'excess_kg':max(a-s,0),'possible_cause':'Dado causal de processo não disponível na fonte Supply','evidence':'Desvio padrão × real medido'})
    materials=sorted(materials,key=lambda x:x['impact'],reverse=True)
    supplier=[]
    for (supplier_name,material),g in d.groupby(['Fornecedor','Material']):
        supplier.append({'supplier':supplier_name,'material':material,'coverage':float(g['Cobertura_Dias'].mean()),'lead_time':float(g['Lead_Time_Dias'].mean()),'adherence':float(g['Aderencia_Fornecedor'].mean()),'risk':str(g['Risco'].mode().iloc[0]),'emergency':float(g['Compra_Emergencial_R$'].sum()),'excess_inventory':float(g['Estoque_Excesso_R$'].sum()),'production_risk_units':float(g['Impacto_Producao_Un'].sum()),'evidence':str(g['Evidencia'].mode().iloc[0])})
    supplier=sorted(supplier,key=lambda x:({'Alto':3,'Médio':2,'Medio':2,'Baixo':1}.get(x['risk'],0),x['production_risk_units']),reverse=True)
    emergency=float(d['Compra_Emergencial_R$'].sum()); excess=float(d['Estoque_Excesso_R$'].sum()); risk_units=float(d['Impacto_Producao_Un'].sum()); material_excess=float(dev.sum())
    margin_unit=max(_margin_unit(book,plant),0); production_risk=risk_units*margin_unit
    top=materials[0] if materials else None; top_supply=supplier[0] if supplier else None
    insights=[]
    if top: insights.append({'title':'Principal desvio de materiais','text':f"{top['material']} concentra R$ {top['impact']:,.0f} de consumo acima do padrão ({(top['deviation'] or 0)*100:.1f}%). A causa de processo precisa ser confirmada; a fonte Supply não a informa."})
    if top_supply: insights.append({'title':'Risco de abastecimento','text':f"{top_supply['material']} / {top_supply['supplier']} está classificado como risco {top_supply['risk']}, cobertura {top_supply['coverage']:.0f} dias vs. lead time {top_supply['lead_time']:.0f} dias."})
    insights.append({'title':'Capital separado de EBITDA','text':f"Estoque em excesso de R$ {excess:,.0f} é exposição de capital de giro e não é somado ao EBITDA potencial."})
    recs=[]
    if top: recs.append({'priority':1,'action':f"Abrir investigação de rendimento/padrão para {top['material']} e confirmar causa de processo antes da captura."})
    if top_supply and top_supply['risk'] in {'Alto','Médio','Medio'}: recs.append({'priority':2,'action':f"Mitigar risco de {top_supply['material']} com {top_supply['supplier']}: cobertura, alternativa e aderência."})
    if emergency>0: recs.append({'priority':3,'action':f"Eliminar recorrência de compras emergenciais (R$ {emergency:,.0f}) atacando itens de cobertura crítica."})
    return {'kpis':{'standard_unit':_ratio(std,units),'actual_unit':_ratio(real,units),'deviation_value':material_excess,'coverage':coverage,'critical':critical,'supplier_adherence':adherence},'monthly':monthly,'materials':materials,'supply':supplier,
            'money':{'material_excess':material_excess,'emergency':emergency,'excess_inventory':excess,'production_risk_units':risk_units,'production_margin_risk':production_risk,'direct_total':material_excess+emergency},'insights':insights,'recommendations':recs}


def logistics_screen(book, plant):
    d=plant_filter(book.get('Logistica',pd.DataFrame()),plant); orders=plant_filter(book.get('Pedidos_Logistica',pd.DataFrame()),plant)
    if d.empty:return {}
    total=float(d['Pedidos_Total'].sum()); otif=_ratio(float(d['Pedidos_OTIF'].sum()),total); on=_ratio(float(d['Pedidos_On_Time'].sum()),total); full=_ratio(float(d['Pedidos_In_Full'].sum()),total)
    freight=float(d['Frete_Total'].sum()); units=float(d['Unidades_Entregues'].sum()); avg_occ=float(d['Ocupacao_Pct'].mean()); urg=int(d['Urgencias'].sum())
    monthly=[]
    for m,g in d.groupby('Competencia'):
        t=float(g['Pedidos_Total'].sum()); monthly.append({'period':month_label(m),'otif':_ratio(float(g['Pedidos_OTIF'].sum()),t),'on_time':_ratio(float(g['Pedidos_On_Time'].sum()),t),'in_full':_ratio(float(g['Pedidos_In_Full'].sum()),t),'freight_unit':_ratio(float(g['Frete_Total'].sum()),float(g['Unidades_Entregues'].sum()))})
    bad=orders[orders['Status_OTIF'].astype(str)!='OTIF'].copy() if not orders.empty else pd.DataFrame()
    causes=[]
    if not bad.empty:
        for cause,g in bad.groupby('Causa_Nao_OTIF'):
            n=len(g); causes.append({'cause':cause,'count':int(n),'share':n/len(bad),'revenue_risk':float(g['Receita_em_Risco_R$'].sum())})
        causes=sorted(causes,key=lambda x:x['count'],reverse=True)
    routes=[]
    for (route,region),g in d.groupby(['Rota','Regiao']):
        f=float(g['Frete_Total'].sum()); u=float(g['Unidades_Entregues'].sum())
        routes.append({'route':route,'region':region,'freight_unit':_ratio(f,u),'freight_total':f,'occupancy':float(g['Ocupacao_Pct'].mean()),'urgencies':int(g['Urgencias'].sum()),'lead_time':float(g['Lead_Time_Dias'].mean())})
    routes=sorted(routes,key=lambda x:x['freight_unit'] if x['freight_unit'] is not None else 0,reverse=True)
    critical=[]
    if not bad.empty:
        for _,r in bad.sort_values('Receita_em_Risco_R$',ascending=False).head(10).iterrows():
            critical.append({'order':r['Pedido'],'client':r['Cliente'],'region':r['Regiao'],'carrier':r['Transportadora'],'route':r['Rota'],'status':r['Status_OTIF'],'cause':r['Causa_Nao_OTIF'],'risk':float(r['Receita_em_Risco_R$']),'promised':_clean(r['Data_Prometida']),'delivered':_clean(r['Data_Entrega'])})
    revenue_risk=float(bad['Receita_em_Risco_R$'].sum()) if not bad.empty else 0
    top_cause=causes[0] if causes else None; top_route=routes[0] if routes else None
    insights=[]
    insights.append({'title':'Nível de serviço','text':f"OTIF de {(otif or 0)*100:.1f}% vs. meta {_target(book,'OTIF',.95)*100:.0f}%; On Time {(on or 0)*100:.1f}% e In Full {(full or 0)*100:.1f}%."})
    if top_cause: insights.append({'title':'Principal causa de não OTIF','text':f"{top_cause['cause']} responde por {top_cause['share']*100:.1f}% das ocorrências e R$ {top_cause['revenue_risk']:,.0f} de receita em risco."})
    if top_route: insights.append({'title':'Pressão de frete','text':f"{top_route['route']} tem o maior frete unitário (R$ {top_route['freight_unit']:.2f}/un), ocupação média {top_route['occupancy']*100:.1f}%."})
    insights.append({'title':'Regra financeira','text':f"Receita em risco de R$ {revenue_risk:,.0f} é exposição comercial, não EBITDA garantido. Custos de devolução/reentrega não são monetizados porque a base não traz esses valores separados."})
    recs=[]
    if top_cause: recs.append({'priority':1,'action':f"Atacar {top_cause['cause']} nos pedidos/rotas de maior receita em risco."})
    if top_route: recs.append({'priority':2,'action':f"Revisar tarifa, ocupação e frequência da rota {top_route['route']} antes de renegociar frete."})
    if critical: recs.append({'priority':3,'action':f"Criar rotina diária para os {len(critical)} pedidos críticos exibidos, com dono e data de recuperação."})
    return {'kpis':{'otif':otif,'freight_unit':_ratio(freight,units),'on_time':on,'logistics_cost':freight,'critical_orders':len(bad),'revenue_risk':revenue_risk,'occupancy':avg_occ,'urgencies':urg},'monthly':monthly,'causes':causes,'routes':routes,'critical':critical,
            'money':{'freight_total':freight,'revenue_risk':revenue_risk,'urgencies':urg,'unsupported':['Custo de devoluções','Custo de reentrega','Custo incremental de frete emergencial']},'insights':insights[:4],'recommendations':recs}


def finance_screen(book, plant):
    d=_dre_plant(book,plant)
    if d.empty:return {}
    f=_finance_summary(book,plant)
    variable=float(f.get('Insumos_MP',0) or 0)+float(f.get('MOD',0) or 0)+float(f.get('GGF_Energia',0) or 0)
    ggf=sum(float(f.get(k,0) or 0) for k in ['GGF_Frete','GGF_Energia','GGF_Manutencao','GGF_Contratos_Servicos','GGF_Outros'])
    opex=sum(float(f.get(k,0) or 0) for k in ['Desp_Administrativas','Desp_Comerciais','Desp_Logisticas_sem_Frete','Outros_OPEX'])
    lines=[('Receita Bruta',f.get('Receita_Bruta',0)),('(-) Impostos e deduções',-f.get('Impostos_Deducoes',0)),('Receita Líquida',f.get('Receita_Liquida',0)),('(-) Insumos / MP',-f.get('Insumos_MP',0)),('(-) MOD',-f.get('MOD',0)),('(-) GGF — Frete',-f.get('GGF_Frete',0)),('(-) GGF — Energia',-f.get('GGF_Energia',0)),('(-) GGF — Manutenção',-f.get('GGF_Manutencao',0)),('(-) GGF — Contratos e Serviços',-f.get('GGF_Contratos_Servicos',0)),('(-) GGF — Outros',-f.get('GGF_Outros',0)),('Margem Industrial',f.get('Margem_Industrial',0)),('(-) Custos Fixos Industriais',-f.get('Custos_Fixos_Industriais',0)),('Resultado Industrial',f.get('Resultado_Industrial',0)),('(-) Despesas Administrativas',-f.get('Desp_Administrativas',0)),('(-) Despesas Comerciais',-f.get('Desp_Comerciais',0)),('(-) Despesas Logísticas (sem frete)',-f.get('Desp_Logisticas_sem_Frete',0)),('(-) Outros OPEX',-f.get('Outros_OPEX',0)),('EBITDA Gerencial',f.get('EBITDA_Gerencial',0))]
    trend=_monthly_finance_rows(book,plant)
    costs=[{'name':'MP','value':f.get('Insumos_MP',0)},{'name':'MOD','value':f.get('MOD',0)},{'name':'GGF','value':ggf},{'name':'Fixos','value':f.get('Custos_Fixos_Industriais',0)},{'name':'OPEX','value':opex}]
    # Historical EBITDA bridge: latest competence vs previous competence, exact DRE reconciliation.
    cur,prev,cur_m,prev_m=_last_two_groups(d,'Competencia')
    bridge=[]; bridge_current=0; bridge_projected=0
    if cur is not None and not cur.empty and prev is not None and not prev.empty:
        def s(g,c): return float(g[c].sum())
        bridge_current=s(prev,'EBITDA_Gerencial'); bridge_projected=s(cur,'EBITDA_Gerencial')
        drivers=[('Receita Líquida','Receita_Liquida',1),('Insumos / MP','Insumos_MP',-1),('MOD','MOD',-1),('GGF — Frete','GGF_Frete',-1),('GGF — Energia','GGF_Energia',-1),('GGF — Manutenção','GGF_Manutencao',-1),('GGF — Contratos/Serviços','GGF_Contratos_Servicos',-1),('GGF — Outros','GGF_Outros',-1),('Custos Fixos Industriais','Custos_Fixos_Industriais',-1),('Despesas Administrativas','Desp_Administrativas',-1),('Despesas Comerciais','Desp_Comerciais',-1),('Despesas Logísticas s/ frete','Desp_Logisticas_sem_Frete',-1),('Outros OPEX','Outros_OPEX',-1)]
        for label,col,sign in drivers:
            impact=sign*(s(cur,col)-s(prev,col))
            if abs(impact)>.01: bridge.append({'label':label,'impact':impact})
    bridge_diff=bridge_projected-bridge_current-sum(x['impact'] for x in bridge)
    # DRE closing tests for full selected period.
    calc_margin=float(f.get('Receita_Liquida',0) or 0)-sum(float(f.get(k,0) or 0) for k in ['Insumos_MP','MOD','GGF_Frete','GGF_Energia','GGF_Manutencao','GGF_Contratos_Servicos','GGF_Outros'])
    calc_result=calc_margin-float(f.get('Custos_Fixos_Industriais',0) or 0)
    calc_ebitda=calc_result-opex
    closing={'margin_diff':calc_margin-float(f.get('Margem_Industrial',0) or 0),'result_diff':calc_result-float(f.get('Resultado_Industrial',0) or 0),'ebitda_diff':calc_ebitda-float(f.get('EBITDA_Gerencial',0) or 0),'bridge_diff':bridge_diff}
    direct=_direct_financial_problems(book,plant)
    log=logistics_screen(book,plant); mat=materials_screen(book,plant)
    top_cost=max(costs,key=lambda x:x['value']) if costs else None
    top_pressure=direct[0] if direct else None
    insights=[{'title':'Resultado gerencial','text':f"EBITDA Gerencial de R$ {float(f.get('EBITDA_Gerencial',0))/1e6:.2f} mi, margem {(f.get('EBITDA_Margem_calc') or 0)*100:.1f}% sobre Receita Líquida."}]
    if bridge:
        top_bridge=max(bridge,key=lambda x:abs(x['impact']))
        insights.append({'title':'Maior variação no último mês','text':f"{top_bridge['label']} foi o maior driver da variação mensal do EBITDA, efeito de R$ {top_bridge['impact']:,.0f}. Bridge reconciliada com diferença de R$ {bridge_diff:,.2f}."})
    if top_cost: insights.append({'title':'Estrutura de custos','text':f"{top_cost['name']} é o maior bloco de custo do período, R$ {float(top_cost['value']):,.0f}."})
    if top_pressure: insights.append({'title':'Pressão originada na operação','text':f"{top_pressure['problem']} é a maior oportunidade/pressão monetizada fora da DRE, R$ {top_pressure['impact']:,.0f}; origem: {top_pressure['front']}."})
    recommendations=[]
    if top_pressure: recommendations.append({'priority':1,'action':f"Atacar {top_pressure['problem']} na origem operacional antes de tratar o efeito financeiro.",'path':top_pressure['path']})
    if bridge: recommendations.append({'priority':2,'action':'Revisar mensalmente os drivers da Bridge e exigir explicação operacional para variações materiais.'})
    recommendations.append({'priority':3,'action':'Manter estoque/DPO/DSO fora do EBITDA e tratá-los como capital de giro.'})
    return {'kpis':{'revenue':f.get('Receita_Liquida',0),'industrial_margin':f.get('Margem_Industrial',0),'ebitda':f.get('EBITDA_Gerencial',0),'ebitda_margin':f.get('EBITDA_Margem_calc'),'variable_cost':variable,'ggf_freight':ggf,'opex':opex},
            'dre':[{'line':a,'value':b,'key':a in {'Receita Líquida','Margem Industrial','Resultado Industrial','EBITDA Gerencial'}} for a,b in lines],'trend':trend,'costs':costs,
            'bridge':{'current':bridge_current,'projected':bridge_projected,'items':bridge,'reconciliation_diff':bridge_diff,'current_period':month_label(prev_m) if prev_m is not None else None,'projected_period':month_label(cur_m) if cur_m is not None else None},
            'closing':closing,'operational_pressures':direct,'risk':{'logistics_revenue_risk':log.get('kpis',{}).get('revenue_risk',0),'working_capital_excess':mat.get('money',{}).get('excess_inventory',0)},'insights':insights,'recommendations':recommendations}


def diagnosis_screen(book, plant):
    oee=oee_screen(book,plant); log=logistics_screen(book,plant); mat=materials_screen(book,plant); cap=capacity_screen(book,plant); pcp=pcp_screen(book,plant)
    problems=[]
    # Unique direct monetized OEE components.
    for x in oee.get('money',{}).get('items',[]):
        impact=float(x.get('value',0) or 0)
        if impact<=0: continue
        component='Qualidade' if 'Qualidade' in x['name'] else 'Disponibilidade' if 'Disponibilidade' in x['name'] else 'Performance'
        offs=oee.get('quality_offenders',[]) if component=='Qualidade' else oee.get('availability_offenders',[]) if component=='Disponibilidade' else oee.get('performance_offenders',[])
        top=offs[0] if offs else None
        problems.append({'problem':x['name'],'front':'Produção & OEE','component':component,'impact':impact,'monetized':True,'risk_value':0,'evidence':top.get('evidence') if top else x.get('evidence'),'cause':top.get('cause') if top else None,'action':f"Atacar o principal ofensor de {component.lower()} e medir captura no OEE.",'effort':2 if component!='Disponibilidade' else 3,'horizon':'Até 90 dias','priority':'Alta','path':'/oee'})
    # Material direct impacts.
    for x in mat.get('materials',[])[:4]:
        impact=float(x.get('impact',0) or 0)
        if impact>0: problems.append({'problem':f"Desvio de consumo — {x['material']}",'front':'Materiais & Supply','component':'Consumo MP','impact':impact,'monetized':True,'risk_value':0,'evidence':x.get('evidence'),'cause':None,'action':'Revisar padrão, rendimento e perdas físicas; confirmar causa de processo antes da captura.','effort':2,'horizon':'Até 90 dias','priority':'Alta','path':'/materiais'})
    emergency=float(mat.get('money',{}).get('emergency',0) or 0)
    if emergency>0: problems.append({'problem':'Compras emergenciais','front':'Materiais & Supply','component':'Supply','impact':emergency,'monetized':True,'risk_value':0,'evidence':'Compra_Emergencial_R$ registrada','cause':mat.get('supply',[{}])[0].get('evidence') if mat.get('supply') else None,'action':'Corrigir cobertura/fornecedor dos materiais que geram urgência.','effort':2,'horizon':'Até 90 dias','priority':'Alta','path':'/materiais'})
    cap_impact=float(cap.get('money',{}).get('impact',0) or 0)
    if cap_impact>0: problems.append({'problem':'Capacidade monetizável não capturada','front':'Capacidade','component':'Utilização','impact':cap_impact,'monetized':True,'risk_value':0,'evidence':f"{cap.get('money',{}).get('monetizable',0):.0f} un monetizáveis com demanda",'cause':cap.get('bottleneck',{}).get('resource') if cap.get('bottleneck') else None,'action':'Remover a restrição do recurso gargalo e capturar somente o volume suportado por demanda.','effort':4,'horizon':'3–6 meses','priority':'Alta','path':'/capacidade'})
    # Logistics risk (not EBITDA).
    for x in log.get('causes',[])[:3]:
        rv=float(x.get('revenue_risk',0) or 0)
        if rv>0: problems.append({'problem':x['cause'],'front':'Logística','component':'OTIF','impact':0,'monetized':False,'risk_value':rv,'evidence':f"{x['count']} pedidos não OTIF",'cause':x['cause'],'action':'Atacar pedidos, rotas e transportadoras que concentram a ocorrência.','effort':2,'horizon':'Até 90 dias','priority':'Alta','path':'/logistica'})
    # PCP causal/risk without double count.
    pcp_risk=float(pcp.get('money',{}).get('confirmed_demand_margin_risk',0) or 0)
    if pcp_risk>0: problems.append({'problem':'Demanda confirmada acima do produzido','front':'PCP & Aderência','component':'Execução do plano','impact':0,'monetized':False,'risk_value':pcp_risk,'evidence':f"{pcp.get('money',{}).get('confirmed_demand_short_units',0):.0f} un",'cause':pcp.get('offenders',[{}])[0].get('sku') if pcp.get('offenders') else None,'action':'Separar planejamento de execução e atacar os SKUs que concentram o gap.','effort':2,'horizon':'Até 90 dias','priority':'Alta','path':'/pcp'})
    problems=sorted(problems,key=lambda x:(x.get('impact',0),x.get('risk_value',0)),reverse=True)
    fronts=['Produção & OEE','PCP & Aderência','Capacidade','Materiais & Supply','Logística','Finanças & DRE']
    byfront=[]
    for front in fronts:
        ps=[p for p in problems if p['front']==front]; impact=sum(float(p.get('impact',0) or 0) for p in ps); risk=sum(float(p.get('risk_value',0) or 0) for p in ps)
        byfront.append({'front':front,'problems':len(ps),'impact':impact,'risk':risk,'potential':impact*.70 if impact else 0,'capture':.70 if impact else None,'status':'evidence' if ps else 'no_material_issue'})
    total=sum(x['impact'] for x in byfront); revenue_risk=sum(x['risk'] for x in byfront); potential=sum(x['potential'] for x in byfront)
    quick=[p for p in problems if p.get('effort',5)<=2 and p.get('horizon')=='Até 90 dias']
    horizons=[]
    for h in ['Até 90 dias','3–6 meses','6–12 meses']:
        hp=[p for p in problems if p.get('horizon')==h]; horizons.append({'horizon':h,'impact':sum(float(p.get('impact',0) or 0) for p in hp),'risk':sum(float(p.get('risk_value',0) or 0) for p in hp),'problems':len(hp)})
    monetized=[p for p in problems if float(p.get('impact',0) or 0)>0]; top=monetized[0] if monetized else (problems[0] if problems else None)
    insights=[]
    if top:
        share=float(top.get('impact',0) or 0)/total if total and top.get('impact') else None
        insights.append({'title':'Maior impacto monetizado','text':f"{top['problem']} lidera o Pareto"+(f" e representa {share*100:.1f}% do impacto direto." if share is not None else '.')})
    front_rank=sorted(byfront,key=lambda x:x['impact'],reverse=True)
    if front_rank and front_rank[0]['impact']>0: insights.append({'title':'Concentração por frente','text':f"{front_rank[0]['front']} concentra R$ {front_rank[0]['impact']:,.0f} de impacto direto identificado."})
    if revenue_risk>0: insights.append({'title':'Risco separado de captura','text':f"Há R$ {revenue_risk:,.0f} de margem/receita em risco em PCP/Logística; não é somado ao EBITDA potencial."})
    insights.append({'title':'Causalidade','text':'Causa é afirmada apenas quando existe registro/evidência. Ausência de causa permanece explícita como lacuna de dado, sem preenchimento artificial.'})
    recs=[]
    for i,p in enumerate(problems[:7],1): recs.append({'rank':i,'problem':p['problem'],'front':p['front'],'action':p['action'],'impact':p.get('impact',0),'risk_value':p.get('risk_value',0),'horizon':p.get('horizon'),'priority':p.get('priority'),'path':p.get('path')})
    return {'cards':{'problems':len(problems),'impact':total,'potential':potential,'quick_value':sum(float(p.get('impact',0) or 0)*.70 for p in quick),'actions':len(recs),'payback_months':None,'revenue_risk':revenue_risk},'fronts':byfront,'problems':problems[:18],'priced_problems':monetized[:12],'quickwins':quick[:8],'horizons':horizons,'insights':insights,'recommendations':recs,'risk':{'direct_impact':total,'revenue_risk':revenue_risk,'top_problem':top['problem'] if top else None},'causal_tree':problems[:6],
            'assumptions':['Potencial de captura MVP = 70% somente sobre impactos monetizados; parametrização por tipo de ação continua A VALIDAR.','Receita/margem em risco é exibida separadamente e não é somada ao EBITDA.','Causas sem monetização confiável permanecem visíveis como evidência, sem R$ inventado.']}


def cockpit(book, plant):
    comp=_oee_components(book,plant); pcp=plant_filter(book.get('PCP',pd.DataFrame()),plant); pcp_m=_pcp_metrics(pcp); cap=capacity_screen(book,plant); mat=materials_screen(book,plant); log=logistics_screen(book,plant); fin=finance_screen(book,plant)
    produced=float(pcp['Produzido'].sum()) if not pcp.empty else 0
    kfin=fin.get('kpis',{}); otif=log.get('kpis',{}).get('otif'); cap_util=cap.get('kpis',{}).get('utilization'); supply_adh=mat.get('kpis',{}).get('supplier_adherence')
    targets={'OEE':_target(book,'OEE',.85),'PCP':_target(book,'Aderência PCP',.98),'Capacidade':_target(book,'Utilização Capacidade',.80),'Materiais':.95,'OTIF':_target(book,'OTIF',.95)}
    values={'OEE':comp.get('oee'),'PCP':pcp_m.get('adherence'),'Capacidade':cap_util,'Materiais':supply_adh,'OTIF':otif}; weights={'OEE':.35,'PCP':.20,'Capacidade':.15,'Materiais':.15,'OTIF':.15}
    status=[]; health=0
    for name in weights:
        val=values[name]; tgt=targets[name]; ratio=min((float(val)/tgt if val is not None and not pd.isna(val) and tgt else 0),1.15); health+=ratio*weights[name]*100
        state='good' if val is not None and val>=tgt else 'warn' if val is not None and val>=tgt*.9 else 'bad'
        status.append({'name':name,'value':val,'target':tgt,'weight':weights[name],'state':state})
    # real monthly series
    oee_month=_oee_components(book,plant,True); p2=pcp.copy(); l2=plant_filter(book.get('Logistica',pd.DataFrame()),plant); dre=_dre_plant(book,plant)
    if not p2.empty:p2['_m']=p2['Data'].dt.to_period('M').dt.to_timestamp()
    if not l2.empty:l2['_m']=l2['Competencia'].dt.to_period('M').dt.to_timestamp()
    if not dre.empty:dre=dre.copy();dre['_m']=dre['Competencia'].dt.to_period('M').dt.to_timestamp()
    series=[]
    for row in oee_month:
        m=pd.to_datetime(row['period'],format='%b/%y'); pg=p2[p2['_m']==m] if not p2.empty else pd.DataFrame(); lg=l2[l2['_m']==m] if not l2.empty else pd.DataFrame(); dg=dre[dre['_m']==m] if not dre.empty else pd.DataFrame()
        series.append({'period':row['period'],'oee':row['oee'],'adherence':_ratio(pg['Produzido'].sum(),pg['MRP_Plano'].sum()) if not pg.empty else None,'otif':_ratio(lg['Pedidos_OTIF'].sum(),lg['Pedidos_Total'].sum()) if not lg.empty else None,'margin':_ratio(dg['EBITDA_Gerencial'].sum(),dg['Receita_Liquida'].sum()) if not dg.empty else None})
    diag=diagnosis_screen(book,plant); opps=[{'name':x['problem'],'pillar':x['front'],'impact':x.get('impact',0),'evidence':x.get('evidence'),'path':x.get('path')} for x in diag.get('priced_problems',[])[:5]]
    alerts=[]
    screen_map={'OEE':'/oee','PCP':'/pcp','Capacidade':'/capacidade','Materiais':'/materiais','OTIF':'/logistica'}
    for x in sorted(status,key=lambda z:((z['value'] or 0)/(z['target'] or 1)) if z['value'] is not None else -1)[:5]:
        if x['state']!='good': alerts.append({'kpi':x['name'],'value':x['value'],'target':x['target'],'gap':(x['target']-(x['value'] or 0)),'state':x['state'],'path':screen_map[x['name']]})
    prod=plant_filter(book.get('Producao',pd.DataFrame()),plant); q=plant_filter(book.get('Qualidade',pd.DataFrame()),plant)
    production_detail=[]
    if not prod.empty:
        for line,g in prod.groupby('Linha'):
            qg=q[q['Linha']==line]; hrs=float(g['Horas_Disponiveis'].sum()); av=1-float(g['Horas_Paradas'].sum())/hrs if hrs else None; perf=float(np.average(g['Performance_Calc'],weights=g['Realizado'].clip(lower=0))) if g['Realizado'].sum() else None; qual=_ratio(qg['Aprovado'].sum(),qg['Produzido'].sum()) if not qg.empty else None
            production_detail.append({'line':line,'production':float(g['Realizado'].sum()),'oee':(av*perf*qual if None not in (av,perf,qual) else None),'availability':av,'performance':perf,'quality':qual})
    top=opps[0] if opps else None
    summary=f"{plant}: OEE {(comp.get('oee') or 0)*100:.1f}%, aderência PCP {(pcp_m.get('adherence') or 0)*100:.1f}% e OTIF {(otif or 0)*100:.1f}%. EBITDA Gerencial {float(kfin.get('ebitda',0))/1e6:.2f} mi ({(kfin.get('ebitda_margin') or 0)*100:.1f}% da receita)."
    if top: summary+=f" Maior oportunidade direta: {top['name']} ({top['impact']:,.0f} R$)."
    return {'plant':plant,'kpis':{'production':produced,'oee':comp.get('oee'),'adherence':pcp_m.get('adherence'),'conversion_cost':_finance_summary(book,plant).get('Custo_Conversao_un'),'ebitda':kfin.get('ebitda'),'ebitda_margin':kfin.get('ebitda_margin'),'otif':otif},'series':series,'health':{'score':health,'status':status},'opportunities':opps,'money_total':float(diag.get('cards',{}).get('impact',0) or 0),'alerts':alerts,
            'pillar':[{'name':'PCP & Aderência','value':pcp_m.get('adherence'),'target':targets['PCP'],'path':'/pcp'},{'name':'Produção & OEE','value':comp.get('oee'),'target':targets['OEE'],'path':'/oee'},{'name':'Capacidade','value':cap_util,'target':targets['Capacidade'],'path':'/capacidade'},{'name':'Materiais & Supply','value':supply_adh,'target':targets['Materiais'],'path':'/materiais'},{'name':'Logística','value':otif,'target':targets['OTIF'],'path':'/logistica'},{'name':'Finanças & DRE','value':kfin.get('ebitda_margin'),'target':None,'path':'/financas'}],
            'production_detail':sorted(production_detail,key=lambda x:x['production'],reverse=True),'finance_trend':fin.get('trend',[]),'executive':{'summary':summary,'top':top,'coverage_days':mat.get('kpis',{}).get('coverage')},'actions':diag.get('recommendations',[])[:5]}

# ============================================================================
# v1.0.5 — Executive Intelligence Closure
# Adds the validated analytical layer to every principal screen without
# changing the frozen v0.9.1.1 business formulas.  All conclusions are derived
# from already-calculated fields; drill-through preserves plant/context.
# ============================================================================
from urllib.parse import quote as _urlquote

_v104_multiplant = multiplant
_v104_cockpit = cockpit
_v104_pcp_screen = pcp_screen
_v104_oee_screen = oee_screen
_v104_capacity_screen = capacity_screen
_v104_materials_screen = materials_screen
_v104_logistics_screen = logistics_screen
_v104_finance_screen = finance_screen
_v104_diagnosis_screen = diagnosis_screen
_v104_levers_screen = levers_screen
_v104_simulate = simulate


def _diag_path(plant: str, front: str | None = None, focus: str | None = None):
    q=[f"plant={_urlquote(str(plant))}"]
    if front: q.append(f"front={_urlquote(str(front))}")
    if focus: q.append(f"focus={_urlquote(str(focus))}")
    return "/diagnostico?" + "&".join(q)


def _money_text(v):
    try:
        v=float(v or 0)
    except Exception:
        return "R$ 0"
    if abs(v)>=1_000_000: return f"R$ {v/1_000_000:.2f} mi"
    if abs(v)>=1_000: return f"R$ {v/1_000:.0f} mil"
    return f"R$ {v:.0f}"


def _pct_text(v):
    if v is None or (isinstance(v,float) and np.isnan(v)): return "N/D"
    return f"{float(v)*100:.1f}%"


def multiplant(book):
    d=_v104_multiplant(book)
    rows=d.get('plants',[]); insights=d.get('insights',[])
    worst=d.get('cards',{}).get('worst'); best=d.get('cards',{}).get('best')
    declining=[r for r in rows if r.get('production_change') is not None and r.get('production_change')<0]
    hi_cost=max(rows,key=lambda r: r.get('conversion_cost') or -1,default=None)
    priority=worst or hi_cost
    if priority:
        conclusion=(
            f"A prioridade do grupo é {priority.get('plant')}: OEE {_pct_text(priority.get('oee'))}. "
            f"A comparação deve continuar planta a planta; receita e EBITDA podem ser somados, OEE não."
        )
    else:
        conclusion="A base não contém informação suficiente para priorizar uma planta com segurança."
    d['executive_conclusion']={
        'headline':'Qual planta exige atenção primeiro?',
        'text':conclusion,
        'decision':f"Abrir o Cockpit de {priority.get('plant')} e decompor o principal gap." if priority else 'Completar os dados necessários antes de priorizar.',
        'confidence':'Alta' if priority else 'Baixa'
    }
    drill=[]
    for r in sorted(rows,key=lambda x:(x.get('oee') if x.get('oee') is not None else 9e9)):
        drill.append({'level':'Planta','offender':r.get('plant'),'evidence':f"OEE {_pct_text(r.get('oee'))} · custo conv. {_money_text(r.get('conversion_cost'))}/un",'impact':r.get('ebitda_margin'),'impact_label':'Margem EBITDA','path':r.get('drilldown')})
    d['drilldowns']=drill[:8]
    if declining:
        x=min(declining,key=lambda r:r['production_change'])
        d.setdefault('recommendations',[]).append({'priority':3,'action':f"Investigar a queda de volume de {x['plant']} ({_pct_text(x['production_change'])} vs. mês anterior).",'path':x['drilldown']})
    return d


def pcp_screen(book, plant):
    d=_v104_pcp_screen(book,plant); m=d.get('metrics',{}); offs=d.get('offenders',[]); money=d.get('money',{})
    top=offs[0] if offs else None
    bias=m.get('bias'); direction='sobreprevisão' if bias is not None and bias>0.02 else 'subprevisão' if bias is not None and bias<-0.02 else 'viés controlado'
    conclusion=(f"O forecast apresenta WAPE {_pct_text(m.get('wape'))}, MAPE {_pct_text(m.get('mape'))} e {direction} ({_pct_text(bias)}). "
                f"A aderência Produzido/Plano é {_pct_text(m.get('adherence'))}.")
    if top: conclusion+=f" O SKU prioritário é {top.get('sku')} ({top.get('family')}), responsável por {_pct_text(top.get('wape_contribution'))} do erro ponderado."
    if money.get('confirmed_demand_margin_risk',0): conclusion+=f" Há {_money_text(money.get('confirmed_demand_margin_risk'))} de margem em risco por demanda confirmada não atendida."
    d['executive_conclusion']={'headline':'Conclusão executiva de PCP','text':conclusion,'decision':'Separar erro de previsão do gap de execução e atacar os SKUs que concentram o WAPE.','confidence':'Alta' if top else 'Média'}
    d['drilldowns']=[{'level':'SKU','offender':x.get('sku'),'evidence':f"Família {x.get('family')} · contribuição WAPE {_pct_text(x.get('wape_contribution'))} · Bias {_pct_text(x.get('bias'))}", 'impact':x.get('execution_gap_units'),'impact_label':'Gap plano (un)','path':_diag_path(plant,'PCP & Aderência',str(x.get('sku')))} for x in offs[:10]]
    d['management_practices']=[
        'Revisar previsões com sinal de mercado e pedidos confirmados.',
        'Tratar separadamente erro de forecast, desvio de plano e falha de execução.',
        'Monitorar Bias para evitar sobre/subprevisão sistemática.',
        'Priorizar exceções nos SKUs que concentram o WAPE e o volume.'
    ]
    return d


def oee_screen(book, plant):
    d=_v104_oee_screen(book,plant); k=d.get('kpis',{}); t=d.get('targets',{}); money=d.get('money',{}); eq=d.get('equipment',[])
    gaps={'Disponibilidade':max(float(t.get('availability') or 0)-float(k.get('availability') or 0),0),'Performance':max(float(t.get('performance') or 0)-float(k.get('performance') or 0),0),'Qualidade':max(float(t.get('quality') or 0)-float(k.get('quality') or 0),0)}
    worst=max(gaps,key=gaps.get) if gaps else None; top_eq=eq[0] if eq else None
    text=f"O OEE está em {_pct_text(k.get('oee'))}, contra meta {_pct_text(t.get('oee'))}. O maior gap está em {worst} ({gaps.get(worst,0)*100:.1f} p.p.)."
    if top_eq: text+=f" O equipamento mais crítico é {top_eq.get('equipment')}, com {float(top_eq.get('hours') or 0):.1f} h perdidas e evidência {top_eq.get('evidence') or 'N/D'}."
    text+=f" O impacto direto identificado é {_money_text(money.get('total'))}, sem somar OEE aos próprios componentes."
    d['executive_conclusion']={'headline':'Conclusão executiva de Produção & OEE','text':text,'decision':f"Atacar primeiro {worst.lower() if worst else 'o principal gap'} e o equipamento/ofensor que mais o explica.",'confidence':'Alta' if top_eq else 'Média'}
    drill=[]
    for x in eq[:10]: drill.append({'level':'Equipamento','offender':x.get('equipment'),'evidence':f"{float(x.get('hours') or 0):.1f} h · {x.get('cause') or 'causa N/D'} · {x.get('evidence') or 'evidência N/D'}",'impact':x.get('impact'),'impact_label':'Impacto R$','path':_diag_path(plant,'Produção & OEE',str(x.get('cause') or x.get('equipment')))})
    for comp,key in [('Disponibilidade','availability_offenders'),('Performance','performance_offenders'),('Qualidade','quality_offenders')]:
        for x in d.get(key,[])[:3]: drill.append({'level':comp,'offender':x.get('cause'),'evidence':x.get('evidence') or comp,'impact':x.get('impact'),'impact_label':'Impacto R$','path':_diag_path(plant,'Produção & OEE',comp)})
    d['drilldowns']=drill[:12]
    return d


def capacity_screen(book, plant):
    d=_v104_capacity_screen(book,plant); k=d.get('kpis',{}); m=d.get('money',{}); b=d.get('bottleneck') or {}; resources=d.get('resources',[])
    text=(f"A utilização está em {_pct_text(k.get('utilization'))}; há {float(k.get('idle') or 0):,.0f} un de capacidade ociosa. "
          f"O gargalo prioritário é {b.get('resource') or 'N/D'} ({_pct_text(b.get('utilization'))}). "
          f"Dos {float(m.get('recoverable') or 0):,.0f} un tecnicamente recuperáveis, {float(m.get('monetizable') or 0):,.0f} un são monetizáveis com demanda, equivalentes a {_money_text(m.get('impact'))}.")
    d['executive_conclusion']={'headline':'Conclusão executiva de Capacidade','text':text,'decision':'Remover a restrição antes de adicionar CAPEX e monetizar somente o volume coberto por demanda.','confidence':'Alta' if b else 'Média'}
    d['drilldowns']=[{'level':'Recurso','offender':x.get('resource'),'evidence':f"Linha {x.get('line')} · utilização {_pct_text(x.get('utilization'))} · status {x.get('status')}", 'impact':x.get('capacity'),'impact_label':'Capacidade (un)','path':_diag_path(plant,'Capacidade',str(x.get('resource')))} for x in resources[:10]]
    return d


def materials_screen(book, plant):
    d=_v104_materials_screen(book,plant); k=d.get('kpis',{}); mats=d.get('materials',[]); sup=d.get('supply',[]); money=d.get('money',{})
    top=mats[0] if mats else None; risky=[x for x in sup if str(x.get('risk','')).lower()=='alto']
    text=(f"O consumo real é {float(k.get('actual_unit') or 0):.2f} kg/un contra padrão {float(k.get('standard_unit') or 0):.2f} kg/un. "
          f"O impacto direto de consumo/urgências é {_money_text(float(money.get('material_excess') or 0)+float(money.get('emergency') or 0))}; estoque em excesso ({_money_text(money.get('excess_inventory'))}) permanece capital de giro, fora do EBITDA.")
    if top: text+=f" O material prioritário é {top.get('material')}, com desvio {_pct_text(top.get('deviation'))} e impacto {_money_text(top.get('impact'))}."
    if risky: text+=f" Há {len(risky)} material(is) em risco alto de Supply."
    d['executive_conclusion']={'headline':'Conclusão executiva de Materiais & Supply','text':text,'decision':'Atacar o maior desvio de consumo e, em paralelo, os materiais de risco alto com cobertura insuficiente.','confidence':'Alta' if top else 'Média'}
    drill=[]
    for x in mats[:8]: drill.append({'level':'Material','offender':x.get('material'),'evidence':f"Família {x.get('family')} · desvio {_pct_text(x.get('deviation'))} · {x.get('possible_cause') or 'causa a confirmar'}",'impact':x.get('impact'),'impact_label':'Impacto R$','path':_diag_path(plant,'Materiais & Supply',str(x.get('material')))})
    for x in sorted(sup,key=lambda y:(0 if str(y.get('risk','')).lower()=='alto' else 1, y.get('coverage') or 999))[:6]: drill.append({'level':'Fornecedor / material','offender':f"{x.get('supplier')} · {x.get('material')}", 'evidence':f"Risco {x.get('risk')} · cobertura {x.get('coverage')}d · lead time {x.get('lead_time')}d", 'impact':x.get('production_risk_units'),'impact_label':'Produção em risco (un)','path':_diag_path(plant,'Materiais & Supply',str(x.get('material')))})
    d['drilldowns']=drill[:12]
    return d


def logistics_screen(book, plant):
    d=_v104_logistics_screen(book,plant); k=d.get('kpis',{}); causes=d.get('causes',[]); routes=d.get('routes',[]); critical=d.get('critical',[])
    top_cause=causes[0] if causes else None; expensive=max(routes,key=lambda x:x.get('freight_unit') or -1,default=None)
    text=f"O OTIF está em {_pct_text(k.get('otif'))}, gap de {max(.95-float(k.get('otif') or 0),0)*100:.1f} p.p. para a meta."
    if top_cause: text+=f" A principal causa é {top_cause.get('cause')} ({_pct_text(top_cause.get('share'))} das ocorrências)."
    if expensive: text+=f" A rota com maior frete/un é {expensive.get('route')} ({_money_text(expensive.get('freight_unit'))}/un)."
    text+=f" Receita em risco: {_money_text(k.get('revenue_risk'))}, tratada como exposição e não EBITDA garantido."
    d['executive_conclusion']={'headline':'Conclusão executiva de Logística','text':text,'decision':'Priorizar a causa dominante do OTIF, os pedidos críticos e as rotas com maior pressão de frete/ocupação.','confidence':'Alta' if top_cause else 'Média'}
    drill=[]
    for x in causes[:6]: drill.append({'level':'Causa OTIF','offender':x.get('cause'),'evidence':f"{x.get('count')} ocorrências · {_pct_text(x.get('share'))} do total",'impact':x.get('revenue_risk'),'impact_label':'Receita em risco','path':_diag_path(plant,'Logística',str(x.get('cause')))})
    for x in critical[:8]: drill.append({'level':'Pedido','offender':str(x.get('order')),'evidence':f"{x.get('client')} · {x.get('carrier')} · {x.get('cause')} · {x.get('status')}", 'impact':x.get('risk'),'impact_label':'Valor em risco','path':_diag_path(plant,'Logística',str(x.get('cause')))})
    d['drilldowns']=drill[:12]
    return d


def finance_screen(book, plant):
    d=_v104_finance_screen(book,plant); k=d.get('kpis',{}); pressures=d.get('operational_pressures',[]); bridge=d.get('bridge',{}); insights=d.get('insights',[])
    top=pressures[0] if pressures else None; delta=float((bridge.get('projected') or 0)-(bridge.get('current') or 0))
    text=(f"A Receita Líquida é {_money_text(k.get('revenue'))} e o EBITDA Gerencial {_money_text(k.get('ebitda'))} ({_pct_text(k.get('ebitda_margin'))}). "
          f"A variação de EBITDA entre os períodos é {_money_text(delta)} e a bridge reconcilia por drivers reais.")
    if top: text+=f" A maior pressão operacional rastreada é {top.get('problem')} ({_money_text(top.get('impact'))}), originada em {top.get('front')}."
    d['executive_conclusion']={'headline':'Conclusão executiva financeira','text':text,'decision':'Atacar a origem operacional das pressões antes de tratar o efeito na DRE; manter receita em risco e capital de giro separados do EBITDA.','confidence':'Alta' if abs(float(d.get('closing',{}).get('bridge_diff') or 0))<1 else 'Média'}
    d['drilldowns']=[{'level':'Pressão operacional','offender':x.get('problem'),'evidence':f"{x.get('front')} · {x.get('evidence') or 'evidência operacional'}",'impact':x.get('impact'),'impact_label':'Impacto R$','path':x.get('path')} for x in pressures[:10]]
    return d


def diagnosis_screen(book, plant):
    d=_v104_diagnosis_screen(book,plant); probs=d.get('problems',[]); cards=d.get('cards',{}); risk=d.get('risk',{})
    top=probs[0] if probs else None
    text=f"Foram identificados {int(cards.get('problems') or 0)} problemas em 6 frentes, com {_money_text(cards.get('impact'))} de impacto direto único e {_money_text(cards.get('potential'))} de potencial de captura sob a premissa explícita do MVP."
    if top: text+=f" A prioridade é {top.get('problem')} ({top.get('front')})."
    if risk.get('revenue_risk',0): text+=f" Há ainda {_money_text(risk.get('revenue_risk'))} de receita/margem em risco, exibida separadamente."
    d['executive_conclusion']={'headline':'Conclusão executiva do Diagnóstico','text':text,'decision':'Executar os quick-wins de maior impacto/evidência e estruturar os projetos de maior valor com responsável, prazo e captura.','confidence':'Alta' if top else 'Média'}
    d['drilldowns']=[{'level':x.get('front'),'offender':x.get('problem'),'evidence':x.get('evidence') or 'evidência a confirmar','impact':x.get('impact') or x.get('risk_value'),'impact_label':'Impacto / risco','path':x.get('path')} for x in probs[:12]]
    return d


def cockpit(book, plant):
    d=_v104_cockpit(book,plant); opp=d.get('opportunities',[]); alerts=d.get('alerts',[]); k=d.get('kpis',{}); health=d.get('health',{})
    weakest=min(health.get('status',[]),key=lambda x:(float(x.get('value') or 0)/(float(x.get('target') or 1))),default=None)
    text=d.get('executive',{}).get('summary','')
    if weakest: text+=f" O pilar com maior distância relativa da meta é {weakest.get('name')} ({_pct_text(weakest.get('value'))} vs. {_pct_text(weakest.get('target'))})."
    d['executive_conclusion']={'headline':'Conclusão executiva da planta','text':text,'decision':'Concentrar os próximos 30/60/90 dias no maior gap operacional e nas oportunidades monetizadas do Diagnóstico.','confidence':'Alta'}
    cockpit_insights=[]
    if weakest: cockpit_insights.append({'title':'Pilar que mais exige atenção','text':f"{weakest.get('name')} está em {_pct_text(weakest.get('value'))} contra referência {_pct_text(weakest.get('target'))}."})
    if opp: cockpit_insights.append({'title':'Maior oportunidade monetizada','text':f"{opp[0].get('name')} concentra {_money_text(opp[0].get('impact'))} de impacto direto identificado."})
    cockpit_insights.append({'title':'Saúde ponderada','text':f"Score operacional ponderado: {float(health.get('score') or 0):.1f}/100, com pesos OEE 35%, PCP 20%, Capacidade 15%, Materiais 15% e OTIF 15%."})
    d['insights']=cockpit_insights
    drill=[]
    for x in opp[:5]: drill.append({'level':'Oportunidade','offender':x.get('name'),'evidence':x.get('evidence') or x.get('pillar'),'impact':x.get('impact'),'impact_label':'Impacto R$','path':x.get('path')})
    for x in alerts[:5]: drill.append({'level':'Alerta','offender':x.get('kpi'),'evidence':f"Atual {_pct_text(x.get('value'))} · meta {_pct_text(x.get('target'))}", 'impact':x.get('gap'),'impact_label':'Gap p.p.','path':x.get('path')})
    d['drilldowns']=drill[:10]
    return d


def levers_screen(book, plant):
    d=_v104_levers_screen(book,plant)
    d['executive_conclusion']={'headline':'Leitura do cenário base','text':'O cenário base preserva a DRE atual. O valor só aparece quando metas são alteradas; a bridge deve reconciliar exatamente o Δ EBITDA Gerencial.','decision':'Aplicar metas plausíveis, validar capacidade/demanda e converter o cenário aprovado em plano de execução.','confidence':'Alta'}
    return d


def simulate(book, plant, targets: dict[str,float]):
    d=_v104_simulate(book,plant,targets); e=d.get('ebitda',{}); bridge=d.get('bridge',{}); oee=d.get('oee',{})
    items=sorted(bridge.get('items',[]),key=lambda x:abs(float(x.get('impact') or 0)),reverse=True)
    delta=float(e.get('delta') or 0); diff=float(bridge.get('reconciliation_diff') or 0)
    insights=[]
    if items:
        top=items[0]; insights.append({'title':'Maior alavanca do cenário','text':f"{top.get('label')} responde pelo maior efeito individual: {_money_text(top.get('impact'))}."})
    insights.append({'title':'OEE e capacidade','text':f"OEE {_pct_text(oee.get('current'))} → {_pct_text(oee.get('projected'))}; capacidade capturada {float(oee.get('captured_units') or 0):,.0f} un e volume comercial adicional {float(oee.get('commercial_units') or 0):,.0f} un."})
    insights.append({'title':'Reconciliação','text':f"Δ EBITDA Gerencial {_money_text(delta)}; diferença de reconciliação {_money_text(diff)}."})
    if abs(delta)<1:
        text='Nenhuma meta foi alterada em relação ao cenário base; portanto não há incremento de EBITDA a capturar.'
        decision='Definir metas somente para alavancas com evidência operacional e viabilidade de execução.'
    else:
        text=f"O cenário projeta EBITDA Gerencial de {_money_text(e.get('projected'))}, variação de {_money_text(delta)} e margem de {_pct_text(e.get('margin_projected'))}."
        decision='Validar as premissas das três maiores alavancas, confirmar demanda/capacidade e então converter o cenário em Plano de Ação.'
    recs=[]
    for i,x in enumerate([z for z in items if float(z.get('impact') or 0)>0][:4],1):
        recs.append({'priority':i,'action':f"Validar e estruturar a captura da alavanca {x.get('label')} ({_money_text(x.get('impact'))}).",'path':_diag_path(plant,focus=str(x.get('label')))})
    d['insights']=insights
    d['executive_conclusion']={'headline':'Conclusão executiva do cenário','text':text,'decision':decision,'confidence':'Alta' if abs(diff)<1 else 'Média'}
    d['recommendations']=recs
    d['drilldowns']=[{'level':'Alavanca','offender':x.get('label'),'evidence':'Impacto reconciliado na bridge do cenário','impact':x.get('impact'),'impact_label':'Δ EBITDA','path':_diag_path(plant,focus=str(x.get('label')))} for x in items[:10]]
    return d

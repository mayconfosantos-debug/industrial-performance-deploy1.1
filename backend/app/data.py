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
    production=plant_filter(book.get("Producao",pd.DataFrame()),plant)
    production_units=float(production["Realizado"].sum()) if not production.empty else 0
    vals["Custo_Conversao_un"]=conv/production_units if production_units else np.nan
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
            # Unidade correta: unidades realizadas × (velocidade nominal / real − 1).
            # Este é potencial técnico estimado, não volume vendido e não é monetizado.
            real=pd.to_numeric(g["Velocidade_Real"],errors="coerce"); nominal=pd.to_numeric(g["Velocidade_Nominal"],errors="coerce")
            valid=real>0
            loss=float((g.loc[valid,"Realizado"]*((nominal[valid]/real[valid]-1).clip(lower=0))).sum())
            performance.append({"cause":f"Baixa velocidade — {line}","line":line,"units":loss,"unit":"unidades técnicas potenciais; validar regime/ciclo"})
        performance=sorted(performance,key=lambda x:x["units"],reverse=True)
    quality=[]
    if not q.empty:
        for prod,g in q.groupby("Produto"):
            quality.append({"cause":f"Refugo / retrabalho — {prod}","product":prod,"units":float(g["Refugo"].sum()+g["Retrabalho"].sum()),"scrap":float(g["Refugo"].sum()),"rework":float(g["Retrabalho"].sum())})
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
        c=float(g["Capacidade_Nominal_Un"].sum()); p=float(g["Producao_Real_Un"].sum()); resource.append({"line":line,"utilization":p/c if c else np.nan,"capacity":c,"status":str(g["Status_Recurso"].mode().iloc[0]) if "Status_Recurso" in g.columns and not g["Status_Recurso"].mode().empty else "N/A"})
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
    # MP total da DRE inclui a perda de refugo. Separar parcela atribuível à qualidade
    # antes de permitir a alavanca independente de consumo, evitando dupla contagem.
    if std_mp not in (None,0) and volume > 0 and comp.get("quality") not in (None,0):
        scrap_units_baseline=volume/comp["quality"]-volume
        mp_consumption=max((f.get("Consumo_MP_kg",0)-scrap_units_baseline*std_mp)/volume,0)
    material_loss = max(mp_consumption / std_mp - 1, 0) if std_mp not in (None, 0) else 0
    current = {
        "volume": float(volume), "price": float(price), "mix": float(mix),
        "mp_price": float(mp_price), "mp_consumption": float(mp_consumption),
        "material_loss": float(material_loss), "freight_unit": float(freight_unit),
        "contracts": float(contracts), "fixed": float(fixed),
        "availability": comp.get("availability"), "performance": comp.get("performance"), "scrap": float(scrap),
    }
    # No unapproved default percentage improvement. Manual scenario only.
    suggestions = current.copy()

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
    captured_oee_units = min(desired_inc, oee_enabled, demand_backed)
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
    maint_proj = float(f.get("GGF_Manutencao", 0) or 0)  # Sem hipótese validada de custo evitável
    other_ggf_proj = float(f.get("GGF_Outros", 0) or 0) * vol_ratio

    margin_ind_proj = revenue_proj - mp_proj - mod_proj - freight_proj - energy_proj - maint_proj - contracts_t - other_ggf_proj
    result_ind_proj = margin_ind_proj - fixed_t
    # Despesas sem alavanca explícita permanecem constantes: não presumir 20% de escala.
    opex_proj_parts = {k: float(f.get(k, 0) or 0) for k in opex_parts}
    opex_proj = sum(opex_proj_parts.values())
    ebitda_proj = result_ind_proj - opex_proj
    delta_ebitda = ebitda_proj - ebitda0

    # Bridge incremental EXATA, por variação algébrica dos termos efetivamente usados
    # na DRE. OEE é habilitador causal, não impacto aditivo independente de volume.
    price0=float(cur.get("price",0) or 0);cons0=float(cur.get("mp_consumption",0) or 0)
    mp0_price=float(cur.get("mp_price",0) or 0);freight0=float(cur.get("freight_unit",0) or 0)
    delta_units=volume_t-volume0
    # Receitas: volume + preço + mix (decomposição exata, sem custo de mix inferido).
    revenue_volume=delta_units*price0
    revenue_price=volume_t*(price_t-price0)
    revenue_mix=mix_units*dp_mix
    # MP: preço sobre massa BASE, volume sobre consumo sem refugo,
    # consumo específico e refugo separados, nesta ordem de atribuição.
    mp_price_effect=base_raw_mp_kg*(mp0_price-mp_price_t)
    mp_volume_effect=-delta_units*cons0*mp_price_t
    mp_consumption_effect=volume_t*(cons0-cons_t)*mp_price_t
    mp_scrap_effect=(current_scrap_units-scrap_units_proj)*std_mp*mp_price_t
    # Volume incorpora seus custos variáveis sem criar barra extra de OEE.
    volume_effect=revenue_volume+mp_volume_effect-delta_units*freight0
    volume_effect+=float(f.get("MOD",0) or 0)-mod_proj
    volume_effect+=float(f.get("GGF_Energia",0) or 0)-energy_proj
    volume_effect+=float(f.get("GGF_Outros",0) or 0)-other_ggf_proj
    split=captured_oee_units/delta_units if delta_units>0 else 0.0
    bridge=[
      {"key":"oee_capacity","label":"Volume habilitado por OEE*","impact":volume_effect*split},
      {"key":"volume","label":"Volume comercial*","impact":volume_effect*(1-split)},
      {"key":"price","label":"Preço médio","impact":revenue_price},
      {"key":"mix","label":"Mix (receita; custo A VALIDAR)","impact":revenue_mix},
      {"key":"mp_price","label":"Preço de MP","impact":mp_price_effect},
      {"key":"mp_consumption","label":"Consumo MP sem refugo","impact":mp_consumption_effect},
      {"key":"scrap","label":"Qualidade / Refugo","impact":mp_scrap_effect},
      {"key":"freight","label":"Frete/unidade","impact":volume_t*(freight0-freight_t)},
      {"key":"contracts","label":"Contratos / Serviços","impact":float(f.get("GGF_Contratos_Servicos",0) or 0)-contracts_t},
      {"key":"fixed","label":"Custos fixos","impact":float(f.get("Custos_Fixos_Industriais",0) or 0)-fixed_t},
      {"key":"maintenance","label":"Manutenção","impact":float(f.get("GGF_Manutencao",0) or 0)-maint_proj},
    ]
    bridge=[{**item,"impact":float(item["impact"])} for item in bridge if abs(item['impact'])>1e-7]
    reconciliation=delta_ebitda-sum(item['impact'] for item in bridge)
    if abs(reconciliation)>.01:
        raise ValueError(f'Bridge não reconcilia; diferença R$ {reconciliation:.2f}. Revisar fórmula antes de exibir resultado.')

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
        "bridge": {"items": bridge, "reconciliation_diff": reconciliation,"assumptions":["*Volume adicional depende de demanda vendável confirmada; OEE não gera EBITDA sozinho.","Preço/volume/mix usam decomposição algébrica da receita; custo incremental de mix por SKU A VALIDAR.","MP: consumo sem refugo e qualidade/refugo são componentes distintos da equação; sem dupla contagem.","Manutenção, SG&A e custo fixo total ficam constantes sem driver explícito aprovado."]},
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
    return {"active_file":p.name,"sheets":len(book),"rows":total_rows,"quality":quality,"pipeline":["RAW","Classificação","DE/PARA inteligente","Standard Industrial Model","Data Quality","Semantic/Gold","Motores analíticos"]}


def dashboard_from_book(screen: str, plant: str, book: dict[str, pd.DataFrame]):
    mapping={
        "cockpit":lambda:cockpit(book,plant),"multiplantas":lambda:multiplant(book),"pcp":lambda:pcp_screen(book,plant),"oee":lambda:oee_screen(book,plant),"capacidade":lambda:capacity_screen(book,plant),"materiais":lambda:materials_screen(book,plant),"logistica":lambda:logistics_screen(book,plant),"financas":lambda:finance_screen(book,plant),"diagnostico":lambda:diagnosis_screen(book,plant),"alavancas":lambda:levers_screen(book,plant),"central-dados":lambda:central_data(book)
    }
    if screen not in mapping: return {"status":"planned","screen":screen}
    return mapping[screen]()


def dashboard(screen: str, plant: str):
    return dashboard_from_book(screen, plant, load_book())

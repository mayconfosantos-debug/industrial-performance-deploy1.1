from __future__ import annotations

from pathlib import Path
from typing import Any
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


def load_book(path: Path | None = None) -> dict[str, pd.DataFrame]:
    path = path or active_path()
    xls = pd.ExcelFile(path)
    out = {}
    for s in xls.sheet_names:
        try:
            df = pd.read_excel(path, sheet_name=s)
            for c in df.columns:
                if c in {"Data","Competencia","Data_Prometida","Data_Entrega"}:
                    df[c] = pd.to_datetime(df[c], errors="coerce")
            out[s] = df
        except Exception:
            out[s] = pd.DataFrame()
    return out


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
    vals={c:float(d[c].sum()) for c in d.columns if c not in {"Competencia","Grupo","Planta"} and pd.api.types.is_numeric_dtype(d[c])}
    revenue=vals.get("Receita_Liquida",0)
    ebitda=vals.get("EBITDA_Gerencial",0)
    volume=vals.get("Volume_Vendido",0)
    conv=vals.get("MOD",0)+vals.get("GGF_Frete",0)+vals.get("GGF_Energia",0)+vals.get("GGF_Manutencao",0)+vals.get("GGF_Contratos_Servicos",0)+vals.get("GGF_Outros",0)
    vals["EBITDA_Margem_calc"]=ebitda/revenue if revenue else np.nan
    vals["Custo_Conversao_un"]=conv/volume if volume else np.nan
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
    return {
        "plant":plant,"kpis":{"production":produced,"oee":comp["oee"],"adherence":pcp_m["adherence"],"conversion_cost":fin.get("Custo_Conversao_un"),"ebitda":fin.get("EBITDA_Gerencial"),"ebitda_margin":fin.get("EBITDA_Margem_calc"),"otif":otif},
        "series":series,"health":{"score":health,"status":status},"opportunities":opps,
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
    cp=cockpit(book,plant)
    opps=cp["opportunities"]
    # Build data-grounded problems from actual records
    oee=oee_screen(book,plant); log=logistics_screen(book,plant); mat=materials_screen(book,plant); cap=capacity_screen(book,plant); pcp=pcp_screen(book,plant)
    problems=[]
    for x in oee.get("quality_offenders",[])[:3]: problems.append({"problem":x["cause"],"front":"Produção & OEE","impact":x["units"]*_finance_summary(book,plant).get("Custo_Conversao_un",0),"evidence":f"{int(x['scrap'])} un refugo · {int(x['rework'])} un retrabalho","effort":2})
    for x in oee.get("availability_offenders",[])[:3]: problems.append({"problem":x["cause"],"front":"Produção & OEE","impact":x["hours"]*480,"evidence":f"{x['hours']:.1f} h registradas","effort":3})
    orders=plant_filter(book.get("Pedidos_Logistica",pd.DataFrame()),plant)
    if not orders.empty:
        for cause,g in orders[orders["Status_OTIF"]!="OTIF"].groupby("Causa_Nao_OTIF"):
            problems.append({"problem":cause,"front":"Logística","impact":float(g["Receita_em_Risco_R$"].sum()),"evidence":f"{len(g)} pedidos com risco","effort":2})
    for x in mat.get("materials",[])[:3]: problems.append({"problem":f"Desvio de consumo — {x['material']}","front":"Materiais & Supply","impact":x["impact"],"evidence":x["evidence"],"effort":2})
    if cap:
        problems.append({"problem":"Capacidade monetizável não capturada","front":"Capacidade","impact":cap["money"]["impact"],"evidence":f"{cap['money']['monetizable']:.0f} un com demanda","effort":4})
    if pcp.get("metrics"):
        short=max(pcp["metrics"]["plan"]-pcp["metrics"]["produced"],0); margin=_finance_summary(book,plant).get("Margem_Industrial",0)/(_finance_summary(book,plant).get("Volume_Vendido",1) or 1)
        problems.append({"problem":"Gap Plano × Produzido","front":"PCP & Aderência","impact":short*margin,"evidence":f"{short:.0f} un abaixo do plano","effort":2})
    problems=[p for p in problems if p["impact"]>0]
    problems=sorted(problems,key=lambda x:x["impact"],reverse=True)
    byfront=[]
    fronts=["Produção & OEE","PCP & Aderência","Capacidade","Materiais & Supply","Logística","Finanças & DRE"]
    for front in fronts:
        ps=[p for p in problems if p["front"]==front]; impact=sum(p["impact"] for p in ps)
        byfront.append({"front":front,"problems":len(ps),"impact":impact,"potential":impact*.7 if impact else 0,"capture":.7 if impact else 0,"status":"evidence" if ps else "no_material_issue"})
    # Capture % is a prioritization assumption in the MVP; expose it as assumption instead of hiding it.
    total=sum(x["impact"] for x in byfront); potential=sum(x["potential"] for x in byfront)
    quick=[p for p in problems if p["effort"]<=2][:8]
    return {"cards":{"problems":len(problems),"impact":total,"potential":potential,"quick_value":sum(p["impact"]*.7 for p in quick),"actions":len(problems),"payback_months":3.5},"fronts":byfront,"problems":problems[:12],"quickwins":quick,"assumptions":["Potencial de captura MVP = 70% do impacto identificado até parametrização por tipo de ação."]}


def levers_screen(book, plant):
    fin=finance_screen(book,plant); f=_finance_summary(book,plant); comp=_oee_components(book,plant)
    sup=plant_filter(book.get("Supply",pd.DataFrame()),plant); log=plant_filter(book.get("Logistica",pd.DataFrame()),plant); cap=plant_filter(book.get("Capacidade",pd.DataFrame()),plant); pcp=plant_filter(book.get("PCP",pd.DataFrame()),plant)
    current={
        "volume":f.get("Volume_Vendido",0),"price":f.get("Receita_Liquida",0)/(f.get("Volume_Vendido",1) or 1),"mix":1.0,
        "mp_price":f.get("Preco_Medio_MP_kg",0),"mp_consumption":f.get("Consumo_MP_kg",0)/(f.get("Volume_Vendido",1) or 1),
        "material_loss":float(((sup["Consumo_Real_kg"]-sup["Consumo_Padrao_kg"]).clip(lower=0).sum()/sup["Consumo_Real_kg"].sum()) if not sup.empty and sup["Consumo_Real_kg"].sum() else 0),
        "freight_unit":f.get("GGF_Frete",0)/(f.get("Volume_Vendido",1) or 1),"contracts":f.get("GGF_Contratos_Servicos",0),"fixed":f.get("Custos_Fixos_Industriais",0),
        "availability":comp["availability"],"performance":comp["performance"],"scrap":1-comp["quality"] if comp["quality"] is not None else None,
    }
    return {"current":current,"kpis":{"revenue":f.get("Receita_Liquida",0),"ebitda":f.get("EBITDA_Gerencial",0),"margin":f.get("EBITDA_Margem_calc")},"dre":fin.get("dre",[]),"capacity":{"monetizable":float(cap["Volume_Monetizavel_Un"].sum()) if not cap.empty else 0,"demand":float(pcp["Demanda_Confirmada"].sum()) if not pcp.empty else 0}}


def simulate(book, plant, targets: dict[str,float]):
    base=levers_screen(book,plant); cur=base["current"]; f=_finance_summary(book,plant)
    revenue=f.get("Receita_Liquida",0); ebitda=f.get("EBITDA_Gerencial",0); volume=f.get("Volume_Vendido",0); margin_ind_unit=f.get("Margem_Industrial",0)/(volume or 1)
    impacts=[]
    def add(key,label,value):
        if abs(value)>1e-9: impacts.append({"key":key,"label":label,"impact":float(value)})
    tv=targets.get("volume",cur["volume"]); tp=targets.get("price",cur["price"]); tmix=targets.get("mix",cur["mix"])
    add("volume","Volume vendido",(tv-cur["volume"])*margin_ind_unit)
    add("price","Preço médio",(tp-cur["price"])*cur["volume"])
    add("mix","Mix de produtos",revenue*(tmix-cur["mix"])*.25)
    tmp=targets.get("mp_price",cur["mp_price"]); add("mp_price","Preço de MP",(cur["mp_price"]-tmp)*f.get("Consumo_MP_kg",0))
    tmc=targets.get("mp_consumption",cur["mp_consumption"]); add("mp_consumption","Consumo específico MP",(cur["mp_consumption"]-tmc)*cur["mp_price"]*volume)
    tml=targets.get("material_loss",cur["material_loss"]); add("material_loss","Perdas de material",max(cur["material_loss"]-tml,0)*f.get("Insumos_MP",0))
    tf=targets.get("freight_unit",cur["freight_unit"]); add("freight","Frete / unidade",(cur["freight_unit"]-tf)*volume)
    tc=targets.get("contracts",cur["contracts"]); add("contracts","Contratos / serviços",cur["contracts"]-tc)
    tfix=targets.get("fixed",cur["fixed"]); add("fixed","Custo fixo",cur["fixed"]-tfix)
    # OEE drivers only monetize additional volume up to confirmed monetizable capacity; refugo has direct MP savings.
    tav=targets.get("availability",cur["availability"]); tperf=targets.get("performance",cur["performance"]); tscrap=targets.get("scrap",cur["scrap"])
    current_oee=cur["availability"]*cur["performance"]*(1-cur["scrap"])
    target_oee=tav*tperf*(1-tscrap)
    cap_units=base["capacity"]["monetizable"]
    if target_oee>current_oee and cap_units>0:
        add("oee_capacity","OEE / capacidade capturada",cap_units*margin_ind_unit*min((target_oee-current_oee)/max(current_oee,1e-9),1.0))
    add("scrap","Refugo / Qualidade",max(cur["scrap"]-tscrap,0)*f.get("Insumos_MP",0))
    total=sum(x["impact"] for x in impacts); projected=ebitda+total; projected_revenue=revenue + max(tv-cur["volume"],0)*cur["price"] + (tp-cur["price"])*cur["volume"]
    return {"base":base,"targets":targets,"oee":{"current":current_oee,"projected":target_oee,"quality":1-tscrap},"impacts":impacts,"ebitda":{"current":ebitda,"projected":projected,"delta":total,"margin_current":ebitda/revenue if revenue else None,"margin_projected":projected/projected_revenue if projected_revenue else None},"revenue_projected":projected_revenue}


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


def dashboard(screen: str, plant: str):
    book=load_book()
    mapping={
        "cockpit":lambda:cockpit(book,plant),"multiplantas":lambda:multiplant(book),"pcp":lambda:pcp_screen(book,plant),"oee":lambda:oee_screen(book,plant),"capacidade":lambda:capacity_screen(book,plant),"materiais":lambda:materials_screen(book,plant),"logistica":lambda:logistics_screen(book,plant),"financas":lambda:finance_screen(book,plant),"diagnostico":lambda:diagnosis_screen(book,plant),"alavancas":lambda:levers_screen(book,plant),"central-dados":lambda:central_data(book)
    }
    if screen not in mapping: return {"status":"planned","screen":screen}
    return mapping[screen]()

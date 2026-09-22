"""Industrial Performance v1.0.4: observability, period-scoped analytics and evidence.
No synthetic values. Underlying analytical engine in data.py remains the frozen reference;
this module only expands/guards its public contract and exposes traceable records.
"""
from __future__ import annotations
import math
import pandas as pd
import numpy as np
from . import data as core

DATES=('Competencia','Data')
ADDITIVE_DRE=[('Receita Líquida','Receita_Liquida',1),('Insumos / MP','Insumos_MP',-1),('MOD','MOD',-1),('GGF — Frete','GGF_Frete',-1),('GGF — Energia','GGF_Energia',-1),('GGF — Manutenção','GGF_Manutencao',-1),('GGF — Contratos e Serviços','GGF_Contratos_Servicos',-1),('GGF — Outros','GGF_Outros',-1),('Custos Fixos Industriais','Custos_Fixos_Industriais',-1),('Despesas Administrativas','Desp_Administrativas',-1),('Despesas Comerciais','Desp_Comerciais',-1),('Despesas Logísticas (sem frete)','Desp_Logisticas_sem_Frete',-1),('Outros OPEX','Outros_OPEX',-1)]
DRILL_SOURCES={
'cockpit':('PCP','Fabrica'), 'multiplantas':('PCP','Fabrica'), 'pcp':('PCP','Fabrica'),
'oee':('Producao','Fabrica'),'capacidade':('Capacidade','Fabrica'),
'materiais':('Supply','Fabrica'),'logistica':('Pedidos_Logistica','Fabrica'),
'financas':('DRE_Gerencial','Planta'),'diagnostico':('Producao','Fabrica'),
'alavancas':('DRE_Gerencial','Planta'), 'central-dados':('PCP','Fabrica')}


def safe_num(v):
    try:
        a=float(v)
        return a if math.isfinite(a) else None
    except (ValueError,TypeError): return None


def subset(book,start=None,end=None):
    """Apply the *same* month range to every dated fact table. Masters untouched."""
    s=pd.to_datetime(start,errors='coerce') if start else None
    e=pd.to_datetime(end,errors='coerce') if end else None
    if start and pd.isna(s): raise ValueError('Período inicial inválido')
    if end and pd.isna(e): raise ValueError('Período final inválido')
    if s is not None and e is not None and s>e: raise ValueError('Período final anterior ao inicial')
    if s is None and e is None: return book
    out={}
    for name,df in book.items():
        col=next((x for x in DATES if x in df.columns),None)
        if col is None or df.empty: out[name]=df;continue
        period=pd.to_datetime(df[col],errors='coerce')
        mask=pd.Series(True,index=df.index)
        if s is not None:mask &= (period>=s)
        if e is not None:mask &= (period<e+pd.offsets.MonthBegin(1))
        out[name]=df.loc[mask].copy()
    return out


def coverage(book,plant):
    facts=['Producao','Qualidade','Custos','PCP','Capacidade','Supply','Logistica','Pedidos_Logistica','DRE_Gerencial']
    out=[]
    for s in facts:
        df=book.get(s,pd.DataFrame()); df=core.plant_filter(df,plant,'Planta' if s=='DRE_Gerencial' else 'Fabrica')
        out.append({'sheet':s,'rows':len(df) if df is not None else 0,'status':'available' if df is not None and not df.empty else 'missing'})
    return out


def observations(items):
    """No inferred causes: only numerical observations with named source and qualified action."""
    return [x for x in items if x and x.get('text')]


def financial(book,plant):
    frame=core.plant_filter(book.get('DRE_Gerencial',pd.DataFrame()),plant,'Planta')
    if frame.empty: return {'status':'no_data','message':'DRE indisponível para planta/período selecionado.'}
    result=core.finance_screen(book,plant)
    frame=frame.copy();frame['month']=pd.to_datetime(frame['Competencia']).dt.to_period('M').dt.to_timestamp()
    f=core._finance_summary(book,plant)
    rows=[]
    for month,g in sorted(frame.groupby('month'),key=lambda a:a[0]):
        rows.append({'period':core.month_label(month),'month':month.strftime('%Y-%m'),'revenue':float(g.Receita_Liquida.sum()),'margin':float(g.Margem_Industrial.sum()),'industrial_result':float(g.Resultado_Industrial.sum()),'ebitda':float(g.EBITDA_Gerencial.sum()),'mp':float(g.Insumos_MP.sum()),'mod':float(g.MOD.sum()),'ggf':float(g[['GGF_Frete','GGF_Energia','GGF_Manutencao','GGF_Contratos_Servicos','GGF_Outros']].sum().sum()),'fixed':float(g.Custos_Fixos_Industriais.sum()),'opex':float(g[['Desp_Administrativas','Desp_Comerciais','Desp_Logisticas_sem_Frete','Outros_OPEX']].sum().sum())})
    last=frame[frame['month']==frame['month'].max()];previous=frame[frame['month']==sorted(frame['month'].unique())[-2]] if len(rows)>1 else pd.DataFrame()
    bridge=None
    if not previous.empty:
        cur=float(last.EBITDA_Gerencial.sum());prev=float(previous.EBITDA_Gerencial.sum())
        items=[]
        for label,key,sign in ADDITIVE_DRE:
            change=(float(last[key].sum())-float(previous[key].sum()))*sign
            items.append({'label':label,'key':key,'impact':change,'source':'DRE_Gerencial','evidence':'Variação das linhas reais entre as duas competências'})
        diff=cur-prev-sum(i['impact'] for i in items)
        bridge={'current':prev,'projected':cur,'period_current':core.month_label(previous['month'].iloc[0]),'period_projected':core.month_label(last['month'].iloc[0]),'items':items,'reconciliation_diff':diff,'basis':'Ponte contábil entre competências, não atribuição causal'}
    def residual(g):
        if g.empty:return None
        v=g.sum(numeric_only=True)
        margin=float(v.Receita_Liquida-sum(float(v[k]) for k in ['Insumos_MP','MOD','GGF_Frete','GGF_Energia','GGF_Manutencao','GGF_Contratos_Servicos','GGF_Outros'])-v.Margem_Industrial)
        ri=float(v.Margem_Industrial-v.Custos_Fixos_Industriais-v.Resultado_Industrial)
        eb=float(v.Resultado_Industrial-sum(float(v[k]) for k in ['Desp_Administrativas','Desp_Comerciais','Desp_Logisticas_sem_Frete','Outros_OPEX'])-v.EBITDA_Gerencial)
        return {'margin':margin,'industrial_result':ri,'ebitda':eb,'max_abs':max(abs(margin),abs(ri),abs(eb))}
    result['reconciliation']=residual(frame)
    result['bridge']=bridge
    result['monthly']=rows
    result['cost_drivers']=[{'name':label,'value':float(f.get(key,0) or 0),'source':key} for label,key,sign in ADDITIVE_DRE if sign==-1]
    result['cost_drivers'].sort(key=lambda a:a['value'],reverse=True)
    result['insights']=observations([
        {'title':'EBITDA Gerencial','text':f"Margem EBITDA do período: {float(f.get('EBITDA_Margem_calc',0) or 0)*100:.1f}%. EBITDA e Receita Líquida vêm de DRE_Gerencial.",'source':'DRE_Gerencial','kind':'evidência'},
        {'title':'Maior conta de custo','text':f"{result['cost_drivers'][0]['name']} representa R$ {result['cost_drivers'][0]['value']:,.0f} no filtro selecionado." if result['cost_drivers'] else None,'source':'DRE_Gerencial','kind':'evidência'},
        {'title':'Evolução entre competências','text':f"EBITDA variou R$ {bridge['projected']-bridge['current']:,.0f} de {bridge['period_current']} a {bridge['period_projected']}; a ponte reconcilia linhas contábeis, sem afirmar causas operacionais." if bridge else 'Uma única competência no filtro; ponte entre períodos indisponível.','source':'DRE_Gerencial','kind':'evidência'},
        {'title':'Rastreabilidade','text':f"Resíduo máximo de fechamento entre linhas da DRE: R$ {result['reconciliation']['max_abs']:.2f}." ,'source':'DRE_Gerencial','kind':'evidência'}
    ])
    result['recommendations']=[{'title':'Investigar maior pressão financeira','text':f"Abrir os lançamentos e os drivers operacionais associados a {result['cost_drivers'][0]['name']}; variação contábil isolada não comprova causa.",'source':'DRE_Gerencial','kind':'recomendação condicionada'}] if result['cost_drivers'] else []
    return result


def enrich(screen, book, plant, start=None, end=None):
    data=core.dashboard_from_book(screen,plant,book)
    if not isinstance(data,dict):return data
    data={**data,'source_base':core.active_path().name,'coverage':coverage(book,plant),'selected_period':{'start':start,'end':end},'validation':'EM VALIDAÇÃO'}
    if screen=='financas': data={**data,**financial(book,plant)}
    if screen=='multiplantas':
        data['insights']=observations([{'title':f"OEE por planta: {r['plant']}",'text':f"OEE apurado de {r['oee']*100:.1f}% (Disponibilidade × Performance × Qualidade); clique na planta para aprofundar.",'source':'Producao + Qualidade','kind':'evidência'} for r in data.get('plants',[]) if safe_num(r.get('oee')) is not None]);data['no_group_oee']=True
    if screen=='cockpit':
        f=financial(book,plant)
        data['finance']={'kpis':f.get('kpis'), 'monthly':f.get('monthly'),'reconciliation':f.get('reconciliation')}
        # Five approved weights are on the donut segments, not counts disguised as weights.
        w={'OEE':.35,'Aderência PCP':.20,'Capacidade':.15,'Aderência fornecedores':.15,'OTIF':.15}
        stats=data.get('health',{}).get('status',[])
        for item in stats:item['weight']=w.get(item['name'],0)
        if any(safe_num(it.get('value')) is None for it in stats) or len(stats)!=5:
            data['health']['score']=None
            data['health']['unavailable']='Índice N/A: pelo menos um indicador sem dado. Avaliar qualidade antes de pontuar.'
        else:
            data['health']['score']=max(0,min(100,data['health']['score']))
        diag=enrich('diagnostico',book,plant,start,end)
        data['opportunities']=[{'name':p['problem'],'pillar':p['front'],'impact':p['impact'],'evidence':p.get('evidence')} for p in diag.get('priced_problems',[])[:5]]
        data['money_total']=diag['cards']['impact']
        data['insights']=observations([{'title':'Indicador fora da meta','text':f"{s['name']}: atual {s['value']*100:.1f}%, referência {s['target']*100:.1f}%; verificar os ofensores antes de atribuir causa.",'kind':'evidência','source':'Metas + fato correspondente'} for s in data.get('health',{}).get('status',[]) if safe_num(s.get('value')) is not None and safe_num(s.get('target')) is not None and s['value']<s['target']]);data['recommendations']=[{'title':i['title'],'text':i['text'],'source':i['source']} for i in data['insights'][:3]]
    if screen=='pcp':
        m=data.get('metrics',{});off=data.get('offenders',[])
        data['insights']=observations([{'title':'Erro ponderado do forecast','text':f"WAPE {m['wape']*100:.1f}% e Bias {m['bias']*100:+.1f}%; sinal positivo indica sobreprevisão. Fonte: PCP.",'source':'PCP','kind':'evidência'} if safe_num(m.get('wape')) is not None and safe_num(m.get('bias')) is not None else None,{'title':'SKU ofensor','text':f"{off[0]['sku']} ({off[0]['family']}) contribui com {off[0]['wape_contribution']*100:.2f} p.p. ao WAPE do filtro; investigar planejamento e execução separadamente.",'source':'PCP','kind':'evidência'} if off else None]);data['recommendations']=[{'title':'Investigar maior erro absoluto','text':f"Conferir histórico e premissas de {off[0]['sku']} antes de atualizar o forecast; sem presunção de causa.",'source':'PCP'}] if off else []
    if screen=='oee':
        comp=data.get('kpis',{});eq=data.get('equipment',[])
        data['insights']=observations([{'title':'OEE e seus componentes','text':f"OEE {comp['oee']*100:.1f}% = Disponibilidade {comp['availability']*100:.1f}% × Performance {comp['performance']*100:.1f}% × Qualidade {comp['quality']*100:.1f}%." ,'source':'Producao + Qualidade','kind':'evidência'} if all(safe_num(comp.get(k)) is not None for k in ['oee','availability','performance','quality']) else None, {'title':'Equipamento com maior tempo parado','text':f"{eq[0]['equipment']} registrou {eq[0]['hours']:.1f} h; causa registrada: {eq[0]['cause'] or 'não identificada'}. Verificar eventos antes de atribuir impacto evitável.",'source':'Manutencao','kind':'evidência'} if eq else None]);data['recommendations']=[{'title':'Priorizar investigação da parada','text':f"Abrir os eventos e a evidência de {eq[0]['equipment']}; definir ação somente após confirmação.",'source':'Manutencao'}] if eq else []
    if screen=='capacidade' and data.get('money'):
        money=data.get('money',{});resources=data.get('resources',[])
        monet=min(float(money.get('recoverable',0) or 0),float(money.get('monetizable',0) or 0))
        data['money']['monetizable']=monet
        # Margem industrial média inclui componentes não necessariamente incrementais: não afirmá-la como contribuição.
        data['money']['impact']=None
        data['money']['impact_status']='A VALIDAR: margem incremental por SKU + demanda confirmada; nenhuma redução automática de fixos.'
        data['insights']=observations([{'title':'Capacidade versus demanda','text':f"{money.get('idle',0):,.0f} un ociosas; {money.get('recoverable',0):,.0f} un tecnicamente recuperáveis; até {monet:,.0f} un monetizáveis segundo a base. Impacto EBITDA não monetizado sem margem incremental.",'source':'Capacidade','kind':'evidência'}, {'title':'Utilização por recurso','text':f"Maior utilização observada: {resources[0]['line']} ({resources[0]['utilization']*100:.1f}%). Utilização alta não comprova gargalo sem fluxo e restrição evidenciados.",'source':'Capacidade','kind':'evidência'} if resources else None]);data['recommendations']=[{'title':'Validar monetização por produto','text':'Cruzar demanda adicional confirmada, capacidade recuperável e margem de contribuição por SKU; custo fixo total permanece inalterado sem plano de redução.','source':'Capacidade + PCP + Padroes_Produto'}]
    if screen=='materiais':
        mats=data.get('materials',[]);sup=data.get('supply',[])
        data['insights']=observations([{'title':'Material mais ofensor','text':f"{mats[0]['material']} apresenta R$ {mats[0]['impact']:,.0f} de desvio de consumo valorizado. Evidência da fonte: {mats[0].get('evidence') or 'não informada'}. Não somar novamente refugo incluído no consumo.",'source':'Supply','kind':'evidência'} if mats else None,{'title':'Cobertura versus lead time','text':f"{sum(s['coverage']<s['lead_time'] for s in sup)} de {len(sup)} materiais têm cobertura inferior ao lead time apurado; verificar risco e estoque de segurança.",'source':'Supply','kind':'evidência'} if sup else None]);data['recommendations']=[{'title':'Conferir consumo do material ofensor','text':f"Investigar {mats[0]['material']} por material, lote e padrão antes de aprovar economia.",'source':'Supply'}] if mats else []
    if screen=='logistica':
        k=data.get('kpis',{});cs=data.get('causes',[]);routes=data.get('routes',[])
        data['insights']=observations([{'title':'Nível de serviço','text':f"OTIF {k['otif']*100:.1f}% versus referência de 95%. Receita em risco R$ {k['revenue_risk']:,.0f}, separada do EBITDA.",'source':'Logistica + Pedidos_Logistica','kind':'evidência'} if safe_num(k.get('otif')) is not None else None,{'title':'Ofensor registrado','text':f"{cs[0]['cause']} responde por {cs[0]['share']*100:.1f}% das ocorrências de pedidos não OTIF registradas.",'source':'Pedidos_Logistica','kind':'evidência'} if cs else None]);data['recommendations']=[{'title':'Abrir pedidos do principal ofensor','text':f"Filtrar pedidos com '{cs[0]['cause']}', conferir transportadora e rota e validar plano com a equipe logística.",'source':'Pedidos_Logistica'}] if cs else []
        if k: k['critical_orders_total']=int(len(core.plant_filter(book.get('Pedidos_Logistica',pd.DataFrame()),plant).query("Status_OTIF != 'OTIF'"))) if not book.get('Pedidos_Logistica',pd.DataFrame()).empty else 0;k['critical_orders']=k['critical_orders_total']
    if screen=='diagnostico':
        # Disjoint attribution is not evidenced across material losses, scrap and capacity.
        # Material excess is the sole counted observed cost exposure in this demo;
        # other drivers remain explicitly visible, unpriced and non-additive.
        for p in data.get('problems',[]):
            p['source']='base ativa / evento original; confirmação causal pendente'
            p['kind']='desvio observado, não economia realizada'
            if p.get('front') in {'Capacidade','Produção & OEE'} and p.get('component') in {'Utilização','Qualidade'}:
                p['non_additive_impact']=p['impact']
                p['impact']=0.0;p['monetized']=False
                p['kind']='oportunidade explicativa: impacto sobreposto ou hipótese sem margem incremental'
        for f in data.get('fronts',[]):
            ps=[p for p in data.get('problems',[]) if p['front']==f['front']]
            f['impact']=sum(float(p.get('impact',0) or 0) for p in ps)
            f['potential']=None;f['capture']=None
        data['cards']['impact']=sum(f['impact'] for f in data.get('fronts',[]))
        data['cards']['potential']=None;data['cards']['quick_value']=None
        data['priced_problems']=[p for p in data.get('problems',[]) if float(p.get('impact',0) or 0)>0]
        data['horizons']=[{**h,'impact':sum(p['impact'] for p in data['problems'] if p.get('horizon')==h['horizon'])} for h in data.get('horizons',[])]
        data['risk']['direct_impact']=data['cards']['impact']
        data['problems']=sorted(data['problems'],key=lambda p:(p.get('impact',0),p.get('risk_value',0)),reverse=True)
        data['risk']['top_problem']=data['problems'][0]['problem'] if data['problems'] else None
        # Existing fixed effort, duration and capture were illustrative. Never advertise as validated quick wins.
        data['quickwins']=[]
        data['horizons']=[{'horizon':x['horizon'],'impact':None,'risk':x['risk'],'problems':x['problems'],'status':'A VALIDAR — prazos por ação'} for x in data.get('horizons',[])]
        for r in data.get('recommendations',[]):
            matched=next((p for p in data['problems'] if p['problem']==r['problem'] and p['front']==r['front']),None)
            if matched:r['impact']=matched.get('impact',0)
            r['horizon']='A VALIDAR';r['priority']='proposta de investigação'
        data['insights']=[{'title':'Exposição financeira identificada','text':f"Desvio de consumo valorizado e sem duplicar refugo ou capacidade: R$ {data['cards']['impact']:,.0f}. Economia efetivamente capturável ainda depende de validação.",'source':'Supply','kind':'evidência'}, {'title':'Causas sem soma indevida','text':'Refugo, OEE, capacidade e execução do PCP permanecem visíveis como explicações; seus impactos não são acumulados com consumo de MP até comprovar ausência de sobreposição.','source':'Producao + Qualidade + Capacidade + PCP','kind':'regra'}]
        data['assumptions']=['Impacto exibido = exposição observada de excesso de consumo MP, não incremento garantido no EBITDA. Refugo pode estar incluído no consumo: não somar ambos.','Captura, esforço, horizonte e payback requerem premissas por ação e aprovação; valores exemplificativos do motor anterior não são tratados como fatos.','Receita logística em risco fica separada do EBITDA.']
    if screen=='central-dados':
        data['insights']=[{'title':'Base ativa rastreada','text':f"{data.get('active_file','Base não disponível')}: {data.get('rows',0):,} registros em {data.get('sheets',0)} abas. Fonte: Excel versionado; não há persistência de uploads no ambiente atual.",'source':'Central de Dados','kind':'evidência'}]
        data['recommendations']=[{'title':'Habilitar publicação segura','text':'Contratar storage persistente, autenticação, isolamento por cliente e registros de auditoria antes de ativar upload e DE/PARA em produção.','source':'arquitetura v1.0'}]
    if screen=='alavancas':
        data['validation_note']='Cenários são hipóteses gerenciais. A bridge numérica fecha com a DRE projetada; drivers residuais e premissas precisam ser explicitamente aprovados antes de chamar impacto capturável.'
    return data


def drill(book,screen,plant,dimension='',value='',start=None,end=None,limit=75):
    if screen not in DRILL_SOURCES: raise ValueError('Tela não possui origem de drill-down cadastrada')
    source,col=DRILL_SOURCES[screen]
    if screen=='oee' and dimension in ('Maquina','Causa','Tipo_Parada'):source='Manutencao'
    elif screen=='oee' and dimension in ('Refugo','Produto'):source='Qualidade'
    elif screen=='materiais' and dimension=='Produto':source='Producao'
    elif screen=='logistica' and dimension in ('Rota','Transportadora') and value and dimension=='Rota':source='Logistica'
    elif screen=='diagnostico' and dimension=='Material':source='Supply'
    elif screen=='diagnostico' and dimension in ('Pedido','Causa_Nao_OTIF'):source='Pedidos_Logistica'
    elif screen=='diagnostico' and dimension=='SKU':source='PCP'
    if screen in ('pcp','multiplantas') and dimension=='Fabrica' and value:
        plant=value  # Drill-through de planta comparada deve abrir registros da planta clicada.
    df=core.plant_filter(book.get(source,pd.DataFrame()),plant,'Planta' if source=='DRE_Gerencial' else 'Fabrica')
    total_before=len(df)
    if dimension and value:
        if dimension not in df.columns: return {'source':source,'rows':[],'total_rows':0,'message':f'Dimensão {dimension} não disponível em {source}','evidence':'ausente'}
        df=df[df[dimension].astype(str)==value]
    total=len(df)
    selected=core.records(df.head(min(max(limit,1),100))) if not df.empty else []
    return {'source':source,'plant':plant,'dimension':dimension,'value':value,'total_rows':total,'plant_rows':total_before,'rows':selected,'truncated':total>len(selected),'evidence':'linhas originais da base ativa','aggregation':'nenhum valor sintetizado; abertura da tabela-fonte'}

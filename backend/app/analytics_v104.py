"""Auditable analytical enrichments. No synthetic time-series or unapproved capture factor."""
import math
import pandas as pd
from .data import plant_filter, _finance_summary, _dre_plant, _oee_components, _pcp_metrics, month_label

DRE_COSTS = [
 ('Insumos / MP','Insumos_MP'),('MOD','MOD'),('GGF — Frete','GGF_Frete'),
 ('GGF — Energia','GGF_Energia'),('GGF — Manutenção','GGF_Manutencao'),
 ('GGF — Contratos e Serviços','GGF_Contratos_Servicos'),('GGF — Outros','GGF_Outros'),
 ('Custos Fixos Industriais','Custos_Fixos_Industriais'),
 ('Despesas Administrativas','Desp_Administrativas'),('Despesas Comerciais','Desp_Comerciais'),
 ('Despesas Logísticas (sem frete)','Desp_Logisticas_sem_Frete'),('Outros OPEX','Outros_OPEX')]

def num(v):
    if v is None or pd.isna(v): return None
    return float(v)
def calc(v,den): return float(v/den) if den else None
def obs(title, text, source, status='observado', action=None, key=None):
    return {'title':title,'text':text,'source':source,'classification':status,'action':action,'drill':key}
def sumcol(df,col):
    return float(pd.to_numeric(df[col],errors='coerce').sum()) if df is not None and not df.empty and col in df else 0.0

def finance_extra(book,plant,result):
    d=_dre_plant(book,plant).copy()
    if d.empty: return result
    d['Competencia']=pd.to_datetime(d['Competencia'])
    d=d.sort_values('Competencia')
    actual=d.iloc[-1]
    prior=d.iloc[-2] if len(d)>=2 else None
    def totals(row):
        rev=float(row['Receita_Liquida']); costs=sum(float(row[c]) for _,c in DRE_COSTS)
        margin=rev-sum(float(row[c]) for _,c in DRE_COSTS[:7])
        result_ind=margin-float(row['Custos_Fixos_Industriais'])
        calc_ebitda=rev-costs
        return {'revenue':rev,'margin':margin,'industrial_result':result_ind,'ebitda_calc':calc_ebitda,'ebitda_recorded':float(row['EBITDA_Gerencial']),
                'revenue_diff':float(row['Receita_Bruta'])-float(row['Impostos_Deducoes'])-rev,
                'margin_diff':margin-float(row['Margem_Industrial']),
                'industrial_result_diff':result_ind-float(row['Resultado_Industrial']),
                'ebitda_diff':calc_ebitda-float(row['EBITDA_Gerencial'])}
    monthly_checks=[{'period':month_label(r['Competencia']),**totals(r)} for _,r in d.iterrows()]
    for key in ['revenue_diff','margin_diff','industrial_result_diff','ebitda_diff']:
        if any(abs(row[key])>0.05 for row in monthly_checks):
            result.setdefault('quality_flags',[]).append(f'DRE: divergência {key} em uma ou mais competências. Não classificar como reconciliado.')
    result['reconciliation']={'monthly':monthly_checks,'max_absolute_diff':max((abs(x[k]) for x in monthly_checks for k in ['revenue_diff','margin_diff','industrial_result_diff','ebitda_diff']),default=0)}
    if prior is not None:
        prior_ebitda=float(prior['EBITDA_Gerencial']); current_ebitda=float(actual['EBITDA_Gerencial'])
        bridge=[{'name':'Receita Líquida','impact':float(actual['Receita_Liquida'])-float(prior['Receita_Liquida']),'source':'DRE_Gerencial.Receita_Liquida'}]
        bridge += [{'name':name,'impact':float(prior[col])-float(actual[col]),'source':f'DRE_Gerencial.{col}'} for name,col in DRE_COSTS]
        bridge_sum=sum(x['impact'] for x in bridge)
        result['bridge']={'current':prior_ebitda,'projected':current_ebitda,'items':bridge,'delta':current_ebitda-prior_ebitda,
                          'reconciliation_diff':current_ebitda-prior_ebitda-bridge_sum,
                          'from':month_label(prior['Competencia']),'to':month_label(actual['Competencia']),
                          'status':'reconciled' if abs(current_ebitda-prior_ebitda-bridge_sum)<.05 and result['reconciliation']['max_absolute_diff']<.05 else 'check_source'}
        ranked=sorted((x for x in bridge if x['impact']<0),key=lambda x:x['impact'])
        result['pressures']=ranked[:6]
        result['analysis']=[obs('Variação de EBITDA Gerencial',f"{month_label(prior['Competencia'])} → {month_label(actual['Competencia'])}: Δ EBITDA de R$ {current_ebitda-prior_ebitda:,.2f}.",'DRE_Gerencial.EBITDA_Gerencial')]
        if ranked:
            x=ranked[0]
            result['analysis'].append(obs('Maior pressão contábil observada',f"{x['name']}: efeito de R$ {x['impact']:,.2f} na variação mensal. Causa operacional ainda requer rastreamento da origem.",x['source'],'observado', 'Abrir o detalhamento da rubrica e cruzar o registro operacional.'))
        if result['bridge']['status']!='reconciled':
            result['analysis'].append(obs('Reconciliação pendente','Existe diferença entre linhas e subtotais da DRE; a bridge não pode receber selo de reconciliada.','DRE_Gerencial','divergência'))
    else:
        result['bridge']=None;result['analysis']=[obs('Comparativo indisponível','É necessária uma segunda competência dentro do período selecionado para compor a bridge.','DRE_Gerencial','dado_insuficiente')]
    result['cost_drill']=[{'line':n,'column':col,'value':sumcol(d,col),'source':'DRE_Gerencial'} for n,col in DRE_COSTS]
    result['financial_scope']='Bridge entre as duas últimas competências do período; DRE principal soma o período selecionado. Capital de giro não entra no EBITDA.'
    return result

def pcp_extra(book,plant,r):
    df=plant_filter(book.get('PCP',pd.DataFrame()),plant)
    if df.empty:return r
    m=r.get('metrics',{}); f=sumcol(df,'Forecast'); plan=sumcol(df,'MRP_Plano'); produced=sumcol(df,'Produzido')
    r['planning_gap']=plan-f;r['execution_gap']=produced-plan
    z_unplanned=df[(df['Forecast']==0)&(df['Produzido']>0)]
    z_unrealized=df[(df['Produzido']==0)&(df['Forecast']>0)]
    r['zero_rules']={'unplanned_rows':int(len(z_unplanned)),'unrealized_rows':int(len(z_unrealized)),'both_zero':int(((df['Forecast']==0)&(df['Produzido']==0)).sum())}
    r['analysis']=[obs('Planejamento versus demanda',f'Plano − Forecast: {plan-f:,.0f} un. Este é um gap de planejamento, não uma perda de OEE.','PCP.Forecast + PCP.MRP_Plano',action='Verificar famílias com maior diferença entre demanda prevista e plano.') ,
                   obs('Execução versus plano',f'Produzido − Plano: {produced-plan:,.0f} un. A causalidade deve ser investigada nas linhas e equipamentos.','PCP.MRP_Plano + PCP.Produzido',action='Abrir ofensores SKU e Produção & OEE.')]
    if r.get('offenders'):
        x=r['offenders'][0]; r['analysis'].append(obs('SKU com maior contribuição ao WAPE',f"{x['sku']} ({x['family']}): contribuição de {x['wape_contribution']*100:.2f} p.p.", 'PCP.Forecast + PCP.Produzido','observado','Revisar previsão e abastecimento do SKU.'))
    r['analysis'].append(obs('Monetização em validação','Não atribuir R$ ao erro de forecast sem comprovar perda de margem, estoque ou frete incremental.','PCP + DRE_Gerencial','dado_insuficiente'))
    return r

def oee_extra(book,plant,r):
    p=plant_filter(book.get('Producao',pd.DataFrame()),plant); q=plant_filter(book.get('Qualidade',pd.DataFrame()),plant);m=plant_filter(book.get('Manutencao',pd.DataFrame()),plant)
    top=r.get('equipment',[])
    r['analysis']=[]
    c=r.get('kpis',{})
    if c.get('oee') is not None:
        r['analysis'].append(obs('Equação de OEE',f"D × P × Q = {c['availability']*c['performance']*c['quality']*100:.2f}%; OEE reportado = {c['oee']*100:.2f}%.",'Producao + Qualidade'))
    if top:
        x=top[0];r['analysis'].append(obs('Equipamento com mais horas paradas',f"{x['equipment']}: {x['hours']:.1f} h; causa mais frequente registrada: {x['cause']}.",'Manutencao.Maquina + Duracao_Horas + Causa','observado','Confirmar plano de contenção e confiabilidade.',{'sheet':'Manutencao','field':'Maquina','value':x['equipment']}))
    if not p.empty:
        r['line_monthly']=[]
        for (line,dt),g in p.groupby(['Linha',p['Data'].dt.to_period('M')]):
            qg=q[(q['Linha']==line)&(q['Data'].dt.to_period('M')==dt)] if not q.empty else pd.DataFrame()
            h=sumcol(g,'Horas_Disponiveis');a=1-sumcol(g,'Horas_Paradas')/h if h else None
            w=g['Realizado'].clip(lower=0); perf=float((g['Performance_Calc']*w).sum()/w.sum()) if w.sum() else None
            qual=calc(sumcol(qg,'Aprovado'),sumcol(qg,'Produzido'))
            r['line_monthly'].append({'line':line,'period':month_label(dt.to_timestamp()),'availability':a,'performance':perf,'quality':qual,'oee':a*perf*qual if None not in (a,perf,qual) else None})
    r['money_disclaimer']='Horas paradas e baixa velocidade são causas de capacidade; não somar seus R$ ao valor de volume recuperável. Custos diretos de refugo requerem verificação contra perdas de MP.'
    return r

def capacity_extra(book,plant,r):
    df=plant_filter(book.get('Capacidade',pd.DataFrame()),plant)
    if df.empty:return r
    k=r.get('kpis',{});mon=r.get('money',{}); nominal=k.get('capacity',0); prod=k.get('production',0)
    r['analysis']=[obs('Utilização observada',f"{prod:,.0f} un de {nominal:,.0f} un nominais = {100*prod/nominal:.2f}%" if nominal else 'Capacidade nominal não disponível.','Capacidade.Capacidade_Nominal_Un + Producao_Real_Un')]
    if r.get('resources'):
        x=r['resources'][0];r['analysis'].append(obs('Restrição a investigar',f"{x['line']} opera com {100*(x['utilization'] or 0):.1f}% de utilização; alta utilização isolada não comprova gargalo físico.",'Capacidade.Linha + Capacidade_Nominal_Un + Producao_Real_Un','hipotese','Validar fila, takt e restrição do fluxo.'))
    r['analysis'].append(obs('Volume monetizável',f"Ociosa {mon.get('idle',0):,.0f} → recuperável {mon.get('recoverable',0):,.0f} → demanda registrada {mon.get('demand',0):,.0f} → monetizável informado {mon.get('monetizable',0):,.0f} un.",'Capacidade.Volume_Monetizavel_Un + Demanda_Confirmada_Un','observado','Validar período de conversão e margem de contribuição antes de projetar EBITDA.'))
    r['money']['validation_warning']='Impacto usa margem industrial média como aproximação; validar margem de contribuição e se o volume já aparece em OEE/PCP. Não consolidar com outros impactos antes da deduplicação.'
    r['shifts'] = None
    r['shift_message']='Granularidade por turno não disponível na aba Capacidade; não criar série artificial.'
    return r

def materials_extra(book,plant,r):
    d=plant_filter(book.get('Supply',pd.DataFrame()),plant)
    if d.empty:return r
    sup=r.get('supply',[])
    r['analysis']=[]
    if r.get('materials'):
        x=r['materials'][0];r['analysis'].append(obs('Maior excesso de consumo',f"{x['material']}: desvio de {100*x['deviation']:.1f}% e excesso valorizado em R$ {x['impact']:,.2f}.",'Supply.Consumo_Real_kg + Consumo_Padrao_kg + Preco_MP_R$_kg','observado','Confirmar padrão por produto, unidade e efeito do refugo antes de classificar como economia capturável.',{'sheet':'Supply','field':'Material','value':x['material']}))
    risks=[x for x in sup if x['coverage']<x['lead_time']]
    r['analysis'].append(obs('Cobertura inferior ao lead time',f'{len(risks)} materiais com cobertura média inferior ao lead time registrado.','Supply.Cobertura_Dias + Lead_Time_Dias','observado','Confirmar estoque de segurança e pedidos em trânsito.'))
    r['critical_materials']=risks
    r['supply_money']={'emergency_cost':r['money'].get('emergency'),'excess_inventory':r['money'].get('excess'),'production_risk_units':r['money'].get('production_risk_units'),
                       'caution':'Estoque excedente = capital de giro, não economia automática de EBITDA. Unidades em risco não são receita ou margem sem pedido associado.'}
    return r

def logistics_extra(book,plant,r):
    orders=plant_filter(book.get('Pedidos_Logistica',pd.DataFrame()),plant)
    d=plant_filter(book.get('Logistica',pd.DataFrame()),plant)
    if d.empty:return r
    r['analysis']=[];k=r['kpis']
    r['analysis'].append(obs('Nível de serviço',f"OTIF = {100*k['otif']:.1f}% ({sumcol(d,'Pedidos_OTIF'):,.0f} de {sumcol(d,'Pedidos_Total'):,.0f} pedidos). On Time = {100*k['on_time']:.1f}%.",'Logistica.Pedidos_OTIF + Pedidos_Total + Pedidos_On_Time'))
    if r.get('causes'):
        c=r['causes'][0];r['analysis'].append(obs('Principal motivo registrado de não OTIF',f"{c['cause']}: {c['count']} ocorrências ({100*c['share']:.1f}% do Pareto dos registros de pedidos).",'Pedidos_Logistica.Causa_Nao_OTIF','observado','Abrir pedidos e confirmar responsável pela ocorrência.',{'sheet':'Pedidos_Logistica','field':'Causa_Nao_OTIF','value':c['cause']}))
    if r.get('routes'):
        x=r['routes'][0];r['analysis'].append(obs('Maior frete unitário observado',f"Rota {x['route']}: R$ {x['freight_unit']:.2f}/un. Sem benchmark de distância/carga, não classificar como ineficiência comprovada.",'Logistica.Frete_Total + Unidades_Entregues','observado','Investigar ocupação, distância e contrato da rota.'))
    r['money_lines']=[{'name':'Frete total realizado','value':sumcol(d,'Frete_Total'),'classification':'custo contabilizado','source':'Logistica.Frete_Total'},
                      {'name':'Receita em risco registrada','value':sumcol(orders,'Receita_em_Risco_R$'),'classification':'receita em risco, fora do EBITDA','source':'Pedidos_Logistica.Receita_em_Risco_R$'}]
    r['financial_note']='Atrasos, urgências e devoluções não têm custo extra mensurado nesta base; não criar estimativas arbitrárias. Frete em GGF é custo realizado, não necessariamente perda.'
    r['critical_count_all']=int((orders['Status_OTIF']!='OTIF').sum()) if not orders.empty else 0
    return r

def multiplant_extra(book,result):
    rows=result.get('plants',[]);result['analysis']=[]
    if rows:
        valid=[x for x in rows if x.get('oee') is not None]
        if valid:
            hi=max(valid,key=lambda x:x['oee']);lo=min(valid,key=lambda x:x['oee'])
            result['analysis'].append(obs('Dispersão entre plantas',f"{hi['plant']} {hi['oee']*100:.1f}% versus {lo['plant']} {lo['oee']*100:.1f}%: distância de {(hi['oee']-lo['oee'])*100:.1f} p.p. Comparação, sem OEE médio de grupo.",'Producao + Qualidade','observado','Abrir Cockpit individual das plantas.'))
        costs=[x for x in rows if x.get('conversion_cost') is not None]
        if costs:
            x=max(costs,key=lambda x:x['conversion_cost']);result['analysis'].append(obs('Custo de conversão por unidade',f"{x['plant']}: R$ {x['conversion_cost']:.2f}/un (maior valor observado). Comparabilidade requer mix e método de custeio homogêneos.",'DRE_Gerencial + Volume_Vendido','observado','Comparar mix e linhas de custo antes de concluir ineficiência.'))
    result['no_consolidated_oee']=True
    result['map_status']='Localização precisa não disponível no cadastro; mapa não é exibido para evitar coordenadas inventadas.'
    return result

def enrich(screen,book,plant,result):
    if screen=='financas':return finance_extra(book,plant,result)
    if screen=='pcp':return pcp_extra(book,plant,result)
    if screen=='oee':return oee_extra(book,plant,result)
    if screen=='capacidade':return capacity_extra(book,plant,result)
    if screen=='materiais':return materials_extra(book,plant,result)
    if screen=='logistica':return logistics_extra(book,plant,result)
    if screen=='multiplantas':return multiplant_extra(book,result)
    return result

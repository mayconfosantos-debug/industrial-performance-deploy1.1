'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from './Sidebar'
import { getJSON } from '../lib/api'
import { PageHeader,KpiCard,Panel,DataTable,StatusBadge,fmtMoney,fmtNumber,fmtPct,EmptyState } from './UI'
import { TrendChart,HorizontalBars,HealthDonut,MatrixChart,CostDonut,BridgeChart } from './Charts'
import {MultiScreen,PcpScreen,OeeScreen,CapacityScreen,MaterialsScreen,LogisticsScreen,FinanceScreen,DataCenterScreen} from './OperationalScreens'

const meta={
 cockpit:['Cockpit Executivo','Panorama integrado da performance industrial e oportunidades de valor'],
 multiplantas:['Visão Multiplantas','Panorama integrado da performance das suas plantas'],
 pcp:['PCP & Aderência','Forecast, planejamento e execução em uma única visão'],
 oee:['Produção & OEE','Desempenho da produção, perdas e oportunidades de melhoria'],
 capacidade:['Capacidade','Entenda o potencial produtivo e as restrições da sua operação'],
 materiais:['Materiais & Supply','Eficiência no uso de materiais e segurança no abastecimento'],
 logistica:['Logística','OTIF, frete, nível de serviço e onde está o dinheiro na execução logística'],
 financas:['Finanças & DRE','Leitura gerencial do resultado, conectando performance operacional a resultado financeiro'],
 diagnostico:['Diagnóstico','Da causa raiz ao plano de ação, com impacto financeiro'],
 alavancas:['Alavancas de Valor','Simule as principais alavancas, projete o DRE e reconcilie o EBITDA Gerencial'],
 'central-dados':['Central de Dados','Data Lake industrial, ingestão, mapeamento, qualidade e publicação da base ativa'],
 'plano-acao':['Plano de Ação','Transforme prioridades em execução, responsáveis, prazos e valor capturado'],
 agente:['Agente de Performance','Interprete a operação com contexto, evidência e impacto financeiro'],
 relatorios:['Relatórios','Relatórios executivos e operacionais do Industrial Performance'],
 mapeamentos:['Mapeamentos','Governança do DE/PARA inteligente por empresa e fonte'],
 'qualidade-dados':['Qualidade dos Dados','Completeza, consistência, linhagem e confiança da base industrial'],
 'meu-plano':['Meu Plano','Recursos disponíveis e evolução do produto'],
 ajuda:['Ajuda','Como ler e operar o Industrial Performance']
}
const ACTIVE_SCREENS=new Set(['cockpit','diagnostico','alavancas','multiplantas','pcp','oee','capacidade','materiais','logistica','financas','central-dados'])

const _endMonth = v => {const [y,m]=v.split('-').map(Number);return new Date(Date.UTC(y,m,0)).toISOString().slice(0,10)}
export default function DashboardClient({screen}){
 const router=useRouter()
 const enabled=ACTIVE_SCREENS.has(screen)
 const [plants,setPlants]=useState([])
 const [plant,setPlant]=useState('Planta Campinas')
 const [months,setMonths]=useState([])
 const [dateStart,setDateStart]=useState('')
 const [dateEnd,setDateEnd]=useState('')
 const [data,setData]=useState(null)
 const [err,setErr]=useState('')
 const [loading,setLoading]=useState(enabled)
 const [reloadKey,setReloadKey]=useState(0)
 const [drill,setDrill]=useState(null)
 const [drillErr,setDrillErr]=useState('')
 useEffect(()=>{try{const p=window.localStorage.getItem('ip.selectedPlant');if(p)setPlant(p)}catch(_e){}},[])
 useEffect(()=>{try{window.localStorage.setItem('ip.selectedPlant',plant)}catch(_e){}},[plant])
 const ds=dateStart?`${dateStart}-01`:''
 const de=dateEnd?_endMonth(dateEnd):''
 useEffect(()=>{
   if(!enabled){setLoading(false);setData(null);return}
   let active=true;setLoading(true);setErr('')
   const params=new URLSearchParams({plant,...(ds?{date_start:ds}:{}),...(de?{date_end:de}:{})})
   getJSON(`/api/bootstrap/${screen}?${params}`).then(x=>{
     if(!active)return
     setPlants(x.plants||[]);setMonths(x.months||[])
     if(x.plant&&x.plant!==plant)setPlant(x.plant)
     setData(x.data||{})
   }).catch(e=>{if(active)setErr(String(e))}).finally(()=>{if(active)setLoading(false)})
   return()=>{active=false}
 },[screen,plant,ds,de,reloadKey,enabled])
 const openDrill=(sheet,field=null,value=null)=>{
   setDrill({source:sheet,records:null,loading:true});setDrillErr('')
   const params=new URLSearchParams({sheet,plant,...(field?{field,value:String(value)}:{}),...(ds?{date_start:ds}:{}),...(de?{date_end:de}:{})})
   getJSON(`/api/drilldown/${screen}?${params}`).then(x=>setDrill({...x,loading:false})).catch(e=>{setDrillErr(String(e));setDrill({source:sheet,loading:false,records:[]})})
 }
 const navigatePlant=name=>{setPlant(name);try{localStorage.setItem('ip.selectedPlant',name)}catch(_){}router.push('/cockpit')}
 const exportData=()=>{if(!data)return;const blob=new Blob([JSON.stringify({screen,plant,period:{date_start:ds||null,date_end:de||null},data},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`industrial-performance-${screen}-${plant.replace(/\s+/g,'-')}.json`;a.click();URL.revokeObjectURL(url)}
 const [title,subtitle]=meta[screen]||[screen,'Módulo do Industrial Performance']
 return <div className="app-shell"><Sidebar/><main className="main"><div className="page">
   <PageHeader title={title} subtitle={subtitle} plant={enabled&&screen!=='multiplantas'?plant:undefined} setPlant={setPlant} plants={plants} months={enabled?months:[]} dateStart={dateStart} setDateStart={setDateStart} dateEnd={dateEnd} setDateEnd={setDateEnd} exportData={enabled&&data?exportData:null}/>
   {dateStart&&dateEnd&&dateStart>dateEnd?<div className="empty-state"><h2>Período inválido</h2><p>A competência inicial deve ser anterior ou igual à final.</p></div>:
   !enabled?<EmptyState title={`${title} — no radar`} text="Esta tela não está liberada. O roadmap preserva seu escopo e critérios de aceite."/>:
   loading?<div className="empty-state"><h2>Carregando dados…</h2><p>Consultando o motor analítico e a base ativa.</p></div>:
   err?<div className="empty-state"><h2>Erro ao carregar os dados</h2><p>{err}</p><button className="control-btn control-primary" onClick={()=>setReloadKey(k=>k+1)}>Tentar novamente</button></div>:
   <Screen screen={screen} data={data} plant={plant} drill={openDrill} navigatePlant={navigatePlant} scope={{date_start:ds,date_end:de}}/>
   }
   <div className="footer-note">Industrial Performance v1.0.4 • Paridade analítica incremental • Todas as telas reabertas estão EM VALIDAÇÃO, não homologadas.</div>
 </div></main>
 {drill&&<div className="modal-backdrop" role="presentation" onClick={()=>setDrill(null)}><section className="drill-modal" role="dialog" aria-modal="true" aria-label="Detalhamento da fonte" onClick={e=>e.stopPropagation()}><header className="modal-head"><div><h2>Drill-down · {drill.source}</h2><p>{drill.count==null?'Buscando registros':`${drill.count} registros no filtro · ${drill.message||''}`}</p></div><button className="drill-btn" onClick={()=>setDrill(null)} aria-label="Fechar detalhamento">Fechar ×</button></header>{drillErr&&<p className="bad-text">{drillErr}</p>}{drill.loading?<p>Consultando a fonte…</p>:<><div className="modal-meta"><span>Planta: {plant}</span><span>Filtro: {drill.field?`${drill.field} = ${drill.value}`:'todas as linhas autorizadas'}</span><span>Fonte: {drill.source}</span></div><DataTable rows={drill.records||[]} columns={(drill.columns||[]).map(key=>({key,label:key}))}/>{(drill.shown||0)<(drill.count||0)&&<p className="data-note">Paginação necessária para ver as demais linhas. Os totais retornados incluem todos os registros.</p>}</>}</section></div>}
 </div>
}
function Screen({screen,data,plant,drill,navigatePlant,scope}){
 const map={cockpit:Cockpit,diagnostico:Diagnostico,alavancas:Alavancas,multiplantas:MultiScreen,pcp:PcpScreen,oee:OeeScreen,capacidade:CapacityScreen,materiais:MaterialsScreen,logistica:LogisticsScreen,financas:FinanceScreen,'central-dados':DataCenterScreen}
 const C=map[screen]
 return C?<C data={data} plant={plant} drill={drill} navigatePlant={navigatePlant} scope={scope}/>:<EmptyState title={`${meta[screen]?.[0]||screen} — no radar`}/>
}

function Cockpit({data,drill}){
 const k=data.kpis||{}; const opp=data.opportunities||[]; const health=data.health||{}; const top=opp[0]
 return <>
 <div className="kpi-grid cols-6"><KpiCard label="Produção Real" value={fmtNumber(k.production)} foot="unidades no período" icon="▥"/><KpiCard label="OEE" value={fmtPct(k.oee)} foot="Meta 85%" state={k.oee>=.85?'good':'bad'} icon="◉"/><KpiCard label="Aderência (Prod./Plano)" value={fmtPct(k.adherence)} foot="Meta 98%" state={k.adherence>=.98?'good':'bad'} icon="◎"/><KpiCard label="Custo de Conversão" value={fmtMoney(k.conversion_cost)} foot="por unidade" icon="▮"/><KpiCard label="EBITDA Gerencial" value={fmtMoney(k.ebitda)} foot={`${fmtPct(k.ebitda_margin)} da receita`} state="good" icon="▮"/><KpiCard label="OTIF" value={fmtPct(k.otif)} foot="Meta 95%" state={k.otif>=.95?'good':'bad'} icon="◎"/></div>
 <div className="grid grid-12">
  <Panel className="span-6" title="Evolução dos principais indicadores" subtitle="OEE, Aderência, OTIF e Margem EBITDA ao longo do período." tag="VISÃO MENSAL" icon="▦"><div className="chart chart-lg"><TrendChart data={data.series||[]}/></div></Panel>
  <Panel className="span-3" title="Onde está o dinheiro?" subtitle="Impacto potencial dos principais desvios." tag="VALOR" icon="▮"><HorizontalBars data={opp} dataKey="impact" nameKey="name"/><div className="total-strip"><span>Impacto direto identificado</span><strong>{fmtMoney(data.money_total)}</strong></div></Panel>
  <Panel className="span-3" title="Saúde da Operação" subtitle="Índice ponderado das métricas do cockpit." tag="PESOS" icon="♥"><HealthDonut score={health.score} status={health.status}/><div className="alert-list">{health.status?.filter(x=>x.state!=='good').slice(0,3).map((x,i)=><div className="alert" key={i}><span className="alert-dot">!</span><div><b>{x.name} fora da referência</b><span>Atual {fmtPct(x.value)} · referência {fmtPct(x.target)}</span></div><StatusBadge state={x.state}>Atenção</StatusBadge></div>)}</div></Panel>
  <Panel className="span-6" title="Performance por pilar" subtitle="Situação atual vs. meta/referência." tag="ATUAL × META" icon="◉"><div className="pillar-grid">{data.pillar?.map((x,i)=>{const v=x.value||0;return <div className="pillar" key={i}><div className="pillar-track"><div className="pillar-bar" style={{height:`${Math.max(6,Math.min(100,v*100))}%`}}/></div><strong>{fmtPct(v)}</strong><span>{x.name}</span></div>})}</div></Panel>
  <Panel className="span-3" title="Top 5 oportunidades" subtitle="Ações com maior impacto financeiro estimado." tag="DRILL-DOWN NO DIAGNÓSTICO" icon="◆"><div className="opportunity-list">{opp.slice(0,5).map((x,i)=><button className="opportunity source-row" type="button" onClick={()=>drill(({'Produção & OEE':'Qualidade','Materiais & Supply':'Supply','Logística':'Pedidos_Logistica','Capacidade':'Capacidade','PCP & Aderência':'PCP'})[x.pillar]||'DRE_Gerencial')} key={i}><span className="num">{i+1}</span><b>{x.name}</b><span>{x.pillar}</span><strong>{fmtMoney(x.impact)}</strong></button>)}</div></Panel>
  <Panel className="span-3" title="Resumo executivo" subtitle="Situação, gaps e foco recomendado." tag="LEITURA" icon="▤"><div className="executive-copy">A operação apresenta <strong>OEE de {fmtPct(k.oee)}</strong>, aderência PCP de <strong>{fmtPct(k.adherence)}</strong> e OTIF de <strong>{fmtPct(k.otif)}</strong>.<br/><br/>O EBITDA Gerencial está em <strong>{fmtMoney(k.ebitda)}</strong> ({fmtPct(k.ebitda_margin)}).<br/><br/>{top&&<>A maior oportunidade identificada é <strong>{top.name}</strong>, estimada em <strong>{fmtMoney(top.impact)}</strong>. O aprofundamento deve ocorrer no Diagnóstico antes de transformar o valor em ação.</>}</div></Panel>
  <Panel className="span-5" title="Indicadores operacionais da planta" subtitle="Leitura rápida para aprofundamento." icon="▥"><DataTable columns={[{key:'name',label:'Indicador'},{key:'value',label:'Atual',render:v=>fmtPct(v)},{key:'target',label:'Meta',render:v=>fmtPct(v)},{key:'state',label:'Status',render:v=><StatusBadge state={v}>{v==='good'?'OK':'Atenção'}</StatusBadge>}]} rows={health.status||[]}/></Panel>
  <Panel className="span-4" title="Receita, Custos e EBITDA Gerencial" subtitle="Resultado econômico do período." icon="▮"><div className="metric-trio"><div className="metric-box"><span>Receita Líquida</span><strong>{fmtMoney(data.financial?.revenue)}</strong></div><div className="metric-box"><span>Custos + despesas</span><strong>{fmtMoney(data.financial?.total_cost)}</strong></div><div className="metric-box"><span>EBITDA Gerencial</span><strong>{fmtMoney(data.financial?.ebitda)}</strong><p>{fmtPct(k.ebitda_margin)} da receita</p></div></div></Panel>
  <Panel className="span-3" title="Ações prioritárias" subtitle="Leitura inicial; ação só é liberada após evidência no Diagnóstico." tag="30/60/90" icon="✓"><div className="alert-list">{opp.slice(0,5).map((x,i)=><div className="alert" key={i}><span className="alert-dot" style={{background:'#164e3c',color:'#6ce5b1'}}>{i+1}</span><div><b>{x.name}</b><span>{x.pillar} · {fmtMoney(x.impact)}</span></div></div>)}</div></Panel>
 </div>
 </>
}

function Diagnostico({data,drill}){
 const c=data.cards||{}; const probs=data.problems||[]; const priced=data.priced_problems||[]; const top=probs[0]
 const matrix=priced.filter(x=>Number.isFinite(x.effort)).map(x=>({name:x.problem,impact:x.impact,effort:x.effort}))
 return <>
 <div className="kpi-grid cols-6"><KpiCard label="Problemas identificados" value={fmtNumber(c.problems)} foot="6 frentes avaliadas" icon="⌕"/><KpiCard label="Impacto financeiro total" value={fmtMoney(c.impact)} foot="somente impactos monetizados sem dupla contagem" state="bad" icon="!"/><KpiCard label="Potencial de captura" value={c.potential==null?'N/D':fmtMoney(c.potential)} foot="premissas exigem validação" state="good" icon="↗"/><KpiCard label="Quick-wins" value={c.quick_value==null?'N/D':fmtMoney(c.quick_value)} foot="até 90 dias" icon="◎"/><KpiCard label="Ações recomendadas" value={fmtNumber(c.actions)} foot="priorizadas por evidência e impacto" icon="◆"/><KpiCard label="Payback médio" value={c.payback_months==null?'N/D':`${fmtNumber(c.payback_months,1)} meses`} foot="requer investimento por ação" icon="▦"/></div>
 <div className="grid grid-12">
  <Panel className="span-6" title="Resumo por frente" subtitle="Impacto direto e risco separados para preservar a lógica financeira." tag="6 FRENTES" icon="▤"><DataTable rows={data.fronts||[]} columns={[{key:'front',label:'Frente'},{key:'problems',label:'Problemas'},{key:'impact',label:'Impacto direto',render:v=>fmtMoney(v)},{key:'risk',label:'Receita em risco',render:v=>fmtMoney(v)},{key:'potential',label:'Potencial',render:v=>fmtMoney(v)}]}/></Panel>
  <Panel className="span-6" title="Árvore causal prioritária" subtitle="KPI/Pilar → componente → ofensor/evidência → impacto/risco." tag="CAUSALIDADE" icon="◉"><div className="causal-tree"><div className="node red"><strong>{top?.front||'Sem problema material'}</strong><span>KPI / frente afetada</span></div><div className="node-list"><div className="node orange"><strong>{top?.component||'—'}</strong><span>componente do desvio</span></div><div className="node blue"><strong>{top?.problem||'—'}</strong><span>ofensor / causa identificada</span></div></div><div className="node-list"><div className="node"><strong>Evidência</strong><span>{top?.evidence||'Sem evidência suficiente'}</span></div><div className="node green"><strong>{top?.monetized?fmtMoney(top?.impact):top?.risk_value?`${fmtMoney(top.risk_value)} em risco`:'Não monetizado'}</strong><span>{top?.monetized?'impacto direto calculado':'mantido sem R$ de EBITDA para evitar dupla contagem'}</span></div></div></div></Panel>
  <Panel className="span-4" title="Pareto de problemas — impacto financeiro" subtitle="Somente perdas com monetização rastreável." tag="SEM DUPLA CONTAGEM" icon="▦">{priced.length?<HorizontalBars data={priced.slice(0,9)} dataKey="impact" nameKey="problem" color="#f06464"/>:<div className="executive-copy">Nenhum impacto direto monetizável com evidência suficiente.</div>}</Panel>
  <Panel className="span-4" title="Matriz Impacto × Esforço" subtitle="Priorização dos problemas monetizados." tag="QUADRANTES" icon="◎"><div className="chart">{matrix.length?<MatrixChart data={matrix}/>:<div className="empty-state"><p>Matriz pendente: esforço e investimento por ação não estão validados. Quadrantes mantidos no escopo, sem pontos arbitrários.</p></div>}</div><div className="matrix-note">Quick Wins, Grandes Projetos, Melhorias Incrementais e Projetos Estruturantes requerem esforço validado.</div></Panel>
  <Panel className="span-4" title="Quick-wins — até 90 dias" subtitle="Ações de menor esforço com evidência disponível." tag="AÇÃO" icon="⚡"><div className="alert-list">{!data.quickwins?.length&&<div className="data-note">Pendente: esforço, prazo e responsável validados. Não atribuir quick-win automaticamente.</div>}{(data.quickwins||[]).slice(0,6).map((x,i)=><div className="alert" key={i}><span className="alert-dot" style={{background:'#164e3c',color:'#6ce5b1'}}>{i+1}</span><div><b>{x.problem}</b><span>{x.action}</span></div><strong>{x.impact?fmtMoney(x.impact):x.risk_value?`${fmtMoney(x.risk_value)} risco`:'causal'}</strong></div>)}</div></Panel>
  <Panel className="span-4" title="Ganho por horizonte" subtitle="Valor direto identificado por janela de execução." tag="HORIZONTE" icon="▦"><div className="horizon-grid">{!data.horizons?.length&&<p className="data-note">Prazos não validados: ganho por horizonte N/D.</p>}{(data.horizons||[]).map((x,i)=><div className="horizon-card" key={i}><span>{x.horizon}</span><strong>{fmtMoney(x.impact)}</strong><small>{fmtNumber(x.problems)} problemas · risco {fmtMoney(x.risk)}</small></div>)}</div></Panel>
  <Panel className="span-4" title="Principais insights" subtitle="Leituras calculadas a partir da base e das regras do motor." icon="◆"><div className="analysis-list">{(data.insights||[]).map((x,i)=><div className="analysis-card" key={i}><strong>{x.title}</strong><span>{x.text}</span></div>)}</div></Panel>
  <Panel className="span-4" title="Risco de não agir" subtitle="Impacto direto e receita em risco não são misturados." icon="!"><div className="metric-trio"><div className="metric-box"><span>Impacto direto</span><strong className="bad">{fmtMoney(data.risk?.direct_impact)}</strong><p>efeito monetizado</p></div><div className="metric-box"><span>Receita em risco</span><strong className="warn">{fmtMoney(data.risk?.revenue_risk)}</strong><p>não é EBITDA garantido</p></div><div className="metric-box"><span>Prioridade</span><strong>{data.risk?.top_problem?'1':'—'}</strong><p>{data.risk?.top_problem||'sem problema material'}</p></div></div></Panel>
  <Panel className="span-12" title="Recomendação executiva" subtitle="Sequência priorizada, evidência, horizonte e valor antes de virar Plano de Ação." tag="PRIORIDADE" icon="◎"><DataTable rows={data.recommendations||[]} onRowClick={r=>drill(r.front==='Logística'?'Pedidos_Logistica':r.front==='Materiais & Supply'?'Supply':r.front==='PCP & Aderência'?'PCP':'Producao')} columns={[{key:'rank',label:'#'},{key:'problem',label:'Problema'},{key:'front',label:'Frente'},{key:'action',label:'Ação recomendada'},{key:'horizon',label:'Horizonte'},{key:'impact',label:'Impacto direto',render:v=>fmtMoney(v)},{key:'risk_value',label:'Risco',render:v=>fmtMoney(v)}]}/></Panel>
 </div>{data.assumptions?.map((a,i)=><div className="footer-note" key={i}>Premissa / regra: {a}</div>)}</>
}

function Alavancas({data,plant,scope,drill}){
 const cur=data.current||{}; const suggestions=data.suggestions||{}; const [targets,setTargets]=useState(cur); const [sim,setSim]=useState(null); const [simErr,setSimErr]=useState('')
 useEffect(()=>{setTargets(cur);setSim(null)},[JSON.stringify(cur)])
 useEffect(()=>{if(!Object.keys(targets).length)return; const t=setTimeout(()=>{setSimErr('');getJSON('/api/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plant,targets,date_start:scope?.date_start,date_end:scope?.date_end})}).then(setSim).catch(e=>setSimErr(String(e)))},220); return()=>clearTimeout(t)},[JSON.stringify(targets),plant,scope?.date_start,scope?.date_end])
 const e=sim?.ebitda||{current:data.kpis?.ebitda,projected:data.kpis?.ebitda,delta:0,margin_current:data.kpis?.margin,margin_projected:data.kpis?.margin}
 const leverDefs=[['volume','Volume vendido','un'],['price','Preço médio','R$/un'],['mix','Mix de produtos','índice'],['mp_price','Preço de MP','R$/kg'],['mp_consumption','Consumo específico MP','kg/un'],['freight_unit','Frete / unidade','R$/un'],['contracts','Contratos / serviços','R$'],['fixed','Custo fixo','R$']]
 const currentOee=(cur.availability||0)*(cur.performance||0)*(1-(cur.scrap||0)); const projOee=sim?.oee?.projected??currentOee; const lossNow=cur.material_loss||0; const lossTarget=Math.max((targets.mp_consumption||0)/(data.assumptions?.std_mp_kg_un||targets.mp_consumption||1)-1,0)
 return <>
 <div className="kpi-grid cols-6"><KpiCard label="Receita Líquida Atual" value={fmtMoney(data.kpis?.revenue)} foot="cenário base" icon="▮"/><KpiCard label="EBITDA Gerencial Atual" value={fmtMoney(e.current)} foot="cenário base" icon="▮"/><KpiCard label="Potencial das Alavancas" value={fmtMoney(e.delta)} foot={Math.abs(e.delta||0)<1?'cenário sem alteração':'incremento calculado'} state={(e.delta||0)>=0?'good':'bad'} icon="◎"/><KpiCard label="EBITDA Projetado" value={fmtMoney(e.projected)} foot="cenário simulado" state={(e.delta||0)>=0?'good':'bad'} icon="↗"/><KpiCard label="Margem EBITDA Atual" value={fmtPct(e.margin_current)} foot="base" icon="%"/><KpiCard label="Margem EBITDA Projetada" value={fmtPct(e.margin_projected)} foot="simulada" state={(e.margin_projected||0)>=(e.margin_current||0)?'good':'bad'} icon="%"/></div>
 <div className="grid grid-12">
  <Panel className="span-8" title="Principais alavancas editáveis" subtitle="Ajuste Atual → Meta; o impacto é recalculado na DRE e no EBITDA Gerencial." tag="SEM DUPLA CONTAGEM" icon="◆"><div style={{display:'flex',gap:8,marginBottom:10}}>{Object.keys(suggestions).length>0&&<button className="control-btn control-primary" onClick={()=>setTargets({...cur,...suggestions})}>Aplicar cenário sugerido</button>}<button className="control-btn" onClick={()=>setTargets(cur)}>Resetar base</button></div><div className="lever-grid">{leverDefs.map(([key,label,unit])=><Lever key={key} k={key} label={label} unit={unit} current={cur[key]} target={targets[key]} setTargets={setTargets}/>)}</div><div className="data-note">Perdas de material são derivadas do consumo específico para não criar uma segunda alavanca financeira sobre a mesma causa. Atual {fmtPct(lossNow)} → Meta derivada {fmtPct(lossTarget)}.</div></Panel>
  <Panel className="span-4" title="DRE atual × projeção" subtitle="Linhas oficiais com Atual, Projetado, Δ R$ e Δ %." tag="RECONCILIAÇÃO" icon="▮"><DataTable rows={sim?.dre_compare||[]} columns={[{key:'line',label:'DRE Gerencial'},{key:'current',label:'Atual',render:v=>fmtMoney(v)},{key:'projected',label:'Projetado',render:v=>fmtMoney(v)},{key:'delta',label:'Δ R$',render:v=>fmtMoney(v)},{key:'delta_pct',label:'Δ %',render:v=>fmtPct(v)}]}/></Panel>
  <Panel className="span-8" title="Produção & OEE" subtitle="OEE é resultado dos drivers; monetização depende de capacidade demand-backed." tag="OEE = DISP. × PERF. × QUAL." icon="◉"><div className="oee-driver-grid"><div className="oee-gauge" style={{background:`conic-gradient(var(--cyan) 0 ${Math.max(0,Math.min(100,projOee*100))}%,#183a51 ${Math.max(0,Math.min(100,projOee*100))}% 100%)`}}><strong>{fmtPct(projOee)}</strong><span>OEE projetado</span></div><Driver label="Disponibilidade" k="availability" cur={cur.availability} value={targets.availability} setTargets={setTargets}/><Driver label="Performance" k="performance" cur={cur.performance} value={targets.performance} setTargets={setTargets}/><Driver label="Refugo" k="scrap" cur={cur.scrap} value={targets.scrap} setTargets={setTargets}/></div><div className="data-note">{sim?.oee?.volume_limited_by_demand?`Volume solicitado: ${fmtNumber(sim.oee.requested_volume)} un; volume economicamente admitido: ${fmtNumber(sim.oee.effective_volume)} un. Incremento limitado a ${fmtNumber(sim.oee.demand_backed)} un monetizáveis documentadas na base.`:"Aumentar OEE sem volume vendido com demanda não gera automaticamente EBITDA adicional."}</div><div className="bridge-recon"><div><span>OEE atual</span><strong>{fmtPct(sim?.oee?.current??currentOee)}</strong></div><div><span>OEE projetado</span><strong>{fmtPct(projOee)}</strong></div><div><span>Capacidade capturada</span><strong>{fmtNumber(sim?.oee?.captured_units)} un</strong></div><div><span>Volume comercial adicional</span><strong>{fmtNumber(sim?.oee?.commercial_units)} un</strong></div></div></Panel>
  <Panel className="span-4" title="Qualidade / Refugo" subtitle="Qualidade é derivada e não recebe impacto duplicado." tag="DERIVADO" icon="◇"><div className="metric-box"><span>Qualidade projetada</span><strong>{fmtPct(sim?.oee?.quality ?? (1-(cur.scrap||0)))}</strong><p>Qualidade = 1 − Refugo. Disponibilidade e Performance são drivers causais; o valor de capacidade é monetizado uma única vez.</p></div>{simErr&&<div className="data-note bad-text">{simErr}</div>}</Panel>
  <Panel className="span-9" title="Bridge de EBITDA Gerencial" subtitle="EBITDA Atual + impactos únicos = EBITDA Projetado; diferença deve fechar em zero." tag={sim?.bridge?.attribution_complete?"RECONCILIADO":"ATRIBUIÇÃO A VALIDAR"} icon="▦"><BridgeChart current={e.current} projected={e.projected} items={sim?.bridge?.items||[]}/><div className="bridge-recon"><div><span>EBITDA Atual</span><strong>{fmtMoney(e.current)}</strong></div><div><span>Δ Bridge</span><strong>{fmtMoney((sim?.bridge?.items||[]).reduce((a,x)=>a+(x.impact||0),0))}</strong></div><div><span>EBITDA Projetado</span><strong>{fmtMoney(e.projected)}</strong></div><div><span>Diferença de reconciliação</span><strong className={Math.abs(sim?.bridge?.reconciliation_diff||0)<1&&sim?.bridge?.attribution_complete?'good-text':'bad-text'}>{fmtMoney(sim?.bridge?.reconciliation_diff||0)}</strong></div></div></Panel>
  <Panel className="span-3" title="Composição do incremento" subtitle="Participação das alavancas positivas no Δ EBITDA." tag="ALAVANCAS" icon="◎"><CostDonut data={(sim?.bridge?.items||[]).filter(x=>x.impact>0).map(x=>({name:x.label,value:x.impact}))}/><div className="data-note">Quick-wins pertencem ao Diagnóstico. Esta tela é exclusiva para simulação, DRE e reconciliação. Melhorias de D/P/Q habilitam capacidade; somente unidades com demanda comprovada entram no EBITDA. Alterações de tarifa, MP e estrutura têm impactos únicos.</div></Panel>
 </div></>
}

function Lever({k,label,unit,current,target,setTargets}){return <div className="lever-card"><label><span>{label}</span><small>{unit}</small></label><div className="lever-flow"><div><span>Atual</span><strong>{typeof current==='number'?fmtNumber(current,current<2?2:0):'—'}</strong></div><b>→</b><div><span>Meta</span><input type="number" step="any" value={target??''} onChange={e=>setTargets(s=>({...s,[k]:Number(e.target.value)}))}/></div></div></div>}
function Driver({label,k,cur,value,setTargets}){return <div className="driver-card"><b>{label}</b><input type="number" step="0.001" min="0" max="1" value={value??''} onChange={e=>setTargets(s=>({...s,[k]:Number(e.target.value)}))}/><small>Atual {fmtPct(cur)} → Meta {fmtPct(value)}</small></div>}

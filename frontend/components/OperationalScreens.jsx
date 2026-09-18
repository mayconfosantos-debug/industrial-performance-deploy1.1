'use client'
import {useState} from 'react'
import {KpiCard,Panel,DataTable,StatusBadge,fmtMoney,fmtNumber,fmtPct} from './UI'
import {TrendChart,HorizontalBars,OeePlantChart,OeeTrend,ForecastChart,CapacityChart,ServiceChart,CostDonut,SimpleBars,BridgeChart,FamilyWeekChart,PlantOeeEvolution,FinanceTrendChart,MaterialsConsumptionChart} from './Charts'

const money=(x)=>fmtMoney(x)
const pct=(x)=>fmtPct(x)
const count=(x)=>fmtNumber(x)
const table=(rows,columns,onRowClick)=> <DataTable rows={rows||[]} columns={columns} onRowClick={onRowClick}/>
const c=(key,label,render)=>({key,label,render})
const m=c('impact','Impacto R$',money)
const percentage=(key,label)=>c(key,label,pct)
function Analysis({items=[]}){return <div className="analysis-list">{items.length===0?<p className="data-note">Dados insuficientes para gerar conclusões rastreáveis nesta seleção.</p>:items.map((x,i)=><article className="analysis-card" key={i}><div className="insight-header"><strong>{x.title}</strong><span className="status-badge">{x.classification||'observado'}</span></div><p>{x.text}</p>{x.action&&<p><b>Próxima verificação:</b> {x.action}</p>}<small>Fonte: {x.source}</small></article>)}</div>}
function Empty({text='Sem granularidade ou dados suficientes na base ativa.'}){return <p className="data-note">{text}</p>}
function Kpis({items}){return <div className={`kpi-grid cols-${items.length}`}>
{items.map((x,i)=><KpiCard key={i} icon={x.icon||'▦'} label={x.label} value={x.value} foot={x.foot||'Base ativa • filtro aplicado'} state={x.state||'info'}/>)}</div>}
function SourceNote({children}){return <div className="source-rule">{children}</div>}

export function MultiScreen({data,drill,navigatePlant}){
 const rows=data.plants||[];const cards=data.cards||{};const [selected,setSelected]=useState(null)
 return <>
 <Kpis items={[{label:'Plantas monitoradas',value:count(cards.plants)},{label:'Menor OEE',value:pct(cards.worst?.oee),foot:cards.worst?.plant||'N/D',state:'bad'},{label:'Maior OEE',value:pct(cards.best?.oee),foot:cards.best?.plant||'N/D',state:'good'},{label:'Produção total',value:count(cards.production),foot:'Somente volumes comparáveis'},{label:'Receita Líquida Grupo',value:money(cards.revenue)},{label:'EBITDA Gerencial Grupo',value:money(cards.ebitda)}]}/>
 <div className="grid grid-12">
 <Panel className="span-6" title="OEE por planta" subtitle="Comparação individual; sem média ou consolidado de grupo." tag="PLANTA A PLANTA"><OeePlantChart data={rows}/></Panel>
 <Panel className="span-3" title="Produção por planta" subtitle="Volume realizado no período."><SimpleBars data={rows}/></Panel>
 <Panel className="span-3" title="Custo de conversão por planta" subtitle="R$/un · mix precisa ser comparável."><SimpleBars data={rows} valueKey="conversion_cost"/></Panel>
 <Panel className="span-8" title="Indicadores por planta" subtitle="Clique em uma planta para selecionar o Cockpit." tag="DRILL-THROUGH">{table(rows,[c('plant','Planta'),c('production','Produção',count),percentage('oee','OEE'),percentage('availability','Disp.'),percentage('performance','Performance'),percentage('quality','Qualidade'),c('conversion_cost','Conversão / un',money)],r=>navigatePlant(r.plant))}</Panel>
 <Panel className="span-4" title="Mapa das plantas" subtitle="Governança geográfica."><Empty text={data.map_status||'Coordenadas não informadas; não é possível mostrar mapa confiável.'}/><DrillButton onClick={()=>drill('Cadastro_Dimensoes')}>Ver cadastro de dimensões</DrillButton></Panel>
 <Panel className="span-8" title="Evolução do OEE por planta" subtitle="Série mensal; cada planta tem seu próprio indicador."><div className="series-list">{rows.map(r=><button key={r.plant} type="button" className={`select-line ${selected===r.plant?'chosen':''}`} onClick={()=>setSelected(selected===r.plant?null:r.plant)}>{r.plant}: {pct(r.oee)}</button>)}</div><PlantOeeEvolution data={(data.evolution||[]).filter(r=>!selected||r.plant===selected)}/><SourceNote>Sem seleção, uma curva por planta; clique em uma planta para isolá-la. Não existe OEE consolidado do grupo.</SourceNote></Panel>
 <Panel className="span-4" title="Principais insights" subtitle="Comparações derivadas da base ativa."><Analysis items={data.analysis}/></Panel>
 </div></>
}

export function PcpScreen({data,drill}){
 const k=data.metrics||{};const [family,setFamily]=useState('');const fams=[...new Set((data.family_month||[]).map(r=>r.family))];
 const selected=data.family_month?.filter(x=>!family||x.family===family)||[];
 const top=(data.offenders||[])[0]
 return <>
 <Kpis items={[{label:'Forecast',value:count(k.forecast),foot:'demanda prevista'},{label:'MRP / Plano',value:count(k.plan),foot:'produção planejada'},{label:'Produzido',value:count(k.produced),foot:'produção realizada'},{label:'Aderência (Prod./Plano)',value:pct(k.adherence),foot:'Execução, não acurácia do forecast'}]}/>
 <div className="grid grid-12">
 <Panel className="span-8" title="Qualidade do Forecast" subtitle="MAPE, WAPE e Bias — cálculos complementares." tag="FÓRMULAS"><div className="metric-trio"><div className="metric-box"><span>MAPE</span><strong>{pct(k.mape)}</strong><p>Média do erro absoluto / Real nos pares elegíveis.</p></div><div className="metric-box"><span>WAPE</span><strong>{pct(k.wape)}</strong><p>Σ|Real − Forecast| / Σ|Real|.</p></div><div className="metric-box"><span>Bias</span><strong>{pct(k.bias)}</strong><p>Σ(Forecast − Real) / ΣReal; negativo = subprevisão.</p></div></div><SourceNote>Forecast 0 e Real positivo: MAPE 100%. Real 0 e Forecast positivo: MAPE N/A; continua em WAPE/Bias com denominador válido. Ambos zero: fora da acurácia.</SourceNote></Panel>
 <Panel className="span-4" title="Leitura executiva" subtitle="Diferença de planejamento versus execução."><Analysis items={data.analysis}/></Panel>
 <Panel className="span-8" title="Forecast × Plano × Produzido" subtitle="Três séries calculadas por competência."><ForecastChart data={data.monthly||[]}/></Panel>
 <Panel className="span-4" title="Gaps e exceções" subtitle="Unidades e regras de zero."><div className="metric-box"><span>Plano − Forecast</span><strong>{count(data.planning_gap)}</strong><p>gap de planejamento</p></div><div className="metric-box"><span>Produzido − Plano</span><strong>{count(data.execution_gap)}</strong><p>gap de execução</p></div><div className="data-note">Demanda não prevista: {data.zero_rules?.unplanned_rows??'N/D'} registros · previsão sem realizado: {data.zero_rules?.unrealized_rows??'N/D'}.</div></Panel>
 <Panel className="span-6" title="Família × Semana" subtitle="WAPE por semana e família, sem agregações indevidas." tag="SEMANAL"><FamilyWeekChart data={data.family_week||[]}/>{table(data.family_week||[],[c('family','Família'),c('week','Semana'),percentage('wape','WAPE')],r=>drill('PCP','Familia',r.family))}</Panel>
 <Panel className="span-6" title="Família × Mês" subtitle="Selecione família para aprofundar MAPE, WAPE e Bias." tag="MENSAL"><label className="inline-control">Família <select value={family} onChange={e=>setFamily(e.target.value)}><option value="">Todas</option>{fams.map(f=><option key={f} value={f}>{f}</option>)}</select></label>{table(selected,[c('family','Família'),c('period','Mês'),percentage('mape','MAPE'),percentage('wape','WAPE'),percentage('bias','Bias')],r=>drill('PCP','Familia',r.family))}</Panel>
 <Panel className="span-6" title="Planta × Mês" subtitle="Comparação recalculada a partir das linhas PCP.">{table(data.plant_month||[],[c('plant','Planta'),c('period','Mês'),percentage('mape','MAPE'),percentage('wape','WAPE'),percentage('bias','Bias')],r=>drill('PCP'))}</Panel>
 <Panel className="span-6" title="Ofensores de Forecast — SKU" subtitle="Contribuição ao WAPE ordenada; clique para ver os registros." tag="DRILL-DOWN">{table(data.offenders||[],[c('sku','SKU'),c('family','Família'),percentage('wape_contribution','Contrib. WAPE'),percentage('bias','Bias'),c('volume','Realizado',count)],r=>drill('PCP','SKU',r.sku))}</Panel>
 <Panel className="span-6" title="Onde está o dinheiro?" subtitle="Critério: desvio comprovado ≠ EBITDA realizado."><div className="metric-box"><span>Principal SKU</span><strong>{top?.sku||'N/D'}</strong><p>Contribuição ao erro: {pct(top?.wape_contribution)}</p></div><Empty text="Atribuição financeira só é exibida quando pedido perdido, frete emergencial ou capital adicional forem ligados ao desvio por evidência. Esta base não permite atribuir todo o erro de previsão a EBITDA."/></Panel>
 <Panel className="span-6" title="Boas práticas e interpretação" subtitle="Regras explícitas para revisão com Operações, Comercial e Supply."><div className="analysis-list"><div className="analysis-card">Separar erro de previsão (Forecast × Real), decisão de planejamento (Forecast × Plano) e execução (Plano × Produzido).</div><div className="analysis-card">Monitorar WAPE consolidado e Bias em paralelo ao MAPE. Investigar SKU e família antes de alterar parâmetros.</div><div className="analysis-card">Não converter demanda não prevista ou sobreprevisão diretamente em margem sem transação financeira rastreável.</div></div></Panel>
 </div></>
}

export function OeeScreen({data,drill}){
 const k=data.kpis||{}; const [line,setLine]=useState(''); const lines=data.lines||[];return <>
 <Kpis items={[{label:'OEE',value:pct(k.oee),foot:'D × P × Q'},{label:'Disponibilidade',value:pct(k.availability)},{label:'Performance',value:pct(k.performance)},{label:'Qualidade',value:pct(k.quality),foot:'Aprovado / Produzido'},{label:'Produção Real',value:count(k.production)},{label:'Impacto operacional',value:money(k.impact),foot:'Referência, não somar ao Diagnóstico'}]}/>
 <div className="grid grid-12">
 <Panel className="span-8" title="OEE e seus componentes" subtitle="OEE em barras; Disponibilidade, Performance e Qualidade em linhas."><OeeTrend data={data.trend||[]}/></Panel>
 <Panel className="span-4" title="Perdas por equipamentos — Top 10" subtitle="Horas de manutenção por máquina; clique para ver evidência.">{table(data.equipment||[],[c('equipment','Equipamento'),c('hours','Horas',x=>fmtNumber(x,1)),c('cause','Causa registrada')],r=>drill('Manutencao','Maquina',r.equipment))}</Panel>
 <Panel className="span-4" title="Ofensores — Disponibilidade" subtitle="Paradas registradas em manutenção.">{table(data.availability_offenders||[],[c('cause','Causa'),c('hours','Horas',x=>fmtNumber(x,1)),percentage('share','Participação')],r=>drill('Manutencao','Causa',r.cause))}</Panel>
 <Panel className="span-4" title="Ofensores — Performance" subtitle="Gap de velocidade: indicador operacional de investigação.">{table(data.performance_offenders||[],[c('cause','Linha / sintoma'),c('units','Proxy, N/D',()=> 'ver fonte')],r=>drill('Producao','Linha',r.cause.replace('Baixa velocidade — ','')))}<SourceNote>Proxy da versão anterior não equivale a unidades perdidas auditáveis. A monetização é suspensa até reconciliar velocidade, horas efetivas e mix.</SourceNote></Panel>
 <Panel className="span-4" title="Ofensores — Qualidade" subtitle="Refugo e retrabalho separados.">{table(data.quality_offenders||[],[c('cause','Produto'),c('scrap','Refugo',count),c('rework','Retrabalho',count)],r=>drill('Qualidade','Produto',r.cause.replace('Refugo / retrabalho — ','')))}</Panel>
 <Panel className="span-8" title="OEE por linha e tendência" subtitle="Escolha linha para ver a série mensal real."><label className="inline-control">Linha <select value={line} onChange={e=>setLine(e.target.value)}><option value="">Selecione uma linha</option>{lines.map(x=><option key={x.line} value={x.line}>{x.line}</option>)}</select></label>{table(lines,[c('line','Linha'),percentage('oee','OEE'),percentage('availability','Disp.'),percentage('performance','Performance'),percentage('quality','Qualidade')],r=>setLine(r.line))}{line&&<><div className="chart chart-sm"><OeeTrend data={(data.line_monthly||[]).filter(x=>x.line===line)}/></div><DrillButton onClick={()=>drill('Producao','Linha',line)}>Registros de {line}</DrillButton></>}</Panel>
 <Panel className="span-4" title="Onde está o dinheiro?" subtitle="Regra de atribuição financeira."><div className="metric-box"><span>Referência de custos diretos</span><strong>{money(k.impact)}</strong><p>Manutenção + aproximação de MP no refugo; não classificar automaticamente como economia capturável.</p></div><SourceNote>{data.money_disclaimer}</SourceNote></Panel>
 <Panel className="span-12" title="Conclusões executivas e próximos passos" subtitle="Evidências e ações derivadas dos dados."><Analysis items={data.analysis}/></Panel>
 </div></>
}
function DrillButton({onClick,children='Abrir fonte'}){return <button className="drill-btn" type="button" onClick={onClick}>{children} ↗</button>}

export function CapacityScreen({data,drill}){
 const k=data.kpis||{},w=data.money||{};return <>
 <Kpis items={[{label:'Capacidade Nominal',value:count(k.capacity),foot:'soma do período selecionado'},{label:'Produção Real',value:count(k.production)},{label:'Utilização',value:pct(k.utilization)},{label:'Capacidade Ociosa',value:count(k.idle)},{label:'Potencial a 80%',value:count(k.potential),foot:'cenário técnico, não receita'}]}/>
 <div className="grid grid-12">
 <Panel className="span-8" title="Capacidade, produção e utilização" subtitle="Séries mensais de produção e capacidade; taxa recalculada."><CapacityChart data={data.monthly||[]}/></Panel>
 <Panel className="span-4" title="Utilização por linha / recurso" subtitle="Clique em um recurso para detalhar.">{table(data.resources||[],[c('line','Linha'),percentage('utilization','Utilização'),c('capacity','Nominal',count),c('status','Situação')],r=>drill('Capacidade','Linha',r.line))}</Panel>
 <Panel className="span-4" title="Cenários de produção" subtitle="Aumentos de utilização sem atribuição automática de EBITDA.">{table(data.scenarios||[],[percentage('utilization','Utilização'),c('production','Produção',count),c('gain','Ganho técnico',count)])}</Panel>
 <Panel className="span-4" title="Gargalos potenciais" subtitle="Alta utilização é sinal, não prova isolada.">{table((data.resources||[]).slice(0,8),[c('line','Recurso'),percentage('utilization','Utilização'),c('status','Status')],r=>drill('Capacidade','Linha',r.line))}</Panel>
 <Panel className="span-4" title="Perdas de capacidade" subtitle="Fonte: capacidade ociosa observada."><div className="metric-box"><span>Ociosa</span><strong>{count(w.idle)} un</strong></div><div className="metric-box"><span>Recuperável informada</span><strong>{count(w.recoverable)} un</strong></div><SourceNote>Desagregação por parada, setup, material e falta de demanda exige vínculo causal; a aba Capacidade não identifica todas as causas no mesmo registro.</SourceNote></Panel>
 <Panel className="span-4" title="Utilização por turno" subtitle="Não preencher com séries inventadas."><Empty text={data.shift_message}/></Panel>
 <Panel className="span-4" title="Onde está o dinheiro?" subtitle="Ociosa → recuperável → demanda → monetizável."><div className="waterfall-steps">{[['Ociosa',w.idle],['Recuperável',w.recoverable],['Demanda registrada',w.demand],['Monetizável informado',w.monetizable]].map(([n,v])=><div key={n}><span>{n}</span><b>{count(v)} un</b></div>)}</div><SourceNote>{w.validation_warning}</SourceNote></Panel>
 <Panel className="span-4" title="Conclusões e recomendações" subtitle="Foco nos gargalos observáveis."><Analysis items={data.analysis}/></Panel>
 </div></>
}

export function MaterialsScreen({data,drill}){
 const k=data.kpis||{}, w=data.money||{},s=data.supply||[];return <>
 <Kpis items={[{label:'Consumo Padrão',value:`${fmtNumber(k.standard_unit,2)} kg/un`},{label:'Consumo Real',value:`${fmtNumber(k.actual_unit,2)} kg/un`},{label:'Desvio MP valorizado',value:money(k.deviation_value)},{label:'Cobertura média',value:`${fmtNumber(k.coverage,1)} dias`},{label:'Materiais críticos',value:count(k.critical)},{label:'Aderência fornecedor',value:pct(k.supplier_adherence)}]}/>
 <div className="section-banner">MATERIAIS · Consumo específico, variação de padrão e ofensores</div>
 <div className="grid grid-12">
 <Panel className="span-4" title="Consumo padrão × real" subtitle="Soma de kg, por competência; comparação entre consumos totais."><MaterialsConsumptionChart data={data.monthly||[]}/>{table(data.monthly||[],[c('period','Período'),c('standard','Padrão (kg)',count),c('actual','Real (kg)',count)])}</Panel>
 <Panel className="span-4" title="R$ perdido por material / família" subtitle="Excesso físico × preço registrado; clique para a fonte."><HorizontalBars data={data.materials||[]} dataKey="impact" nameKey="material"/><DrillButton onClick={()=>drill('Supply')}>Todos os registros</DrillButton></Panel>
 <Panel className="span-4" title="Ofensores de materiais" subtitle="Desvio, família e evidência vinculada.">{table(data.materials||[],[c('material','Material'),c('family','Família'),percentage('deviation','Desvio'),m],r=>drill('Supply','Material',r.material))}</Panel>
 <Panel className="span-12" title="Onde está o dinheiro — Materiais" subtitle="Sem somar refugo e consumo em excesso quando forem a mesma perda."><div className="metric-trio"><div className="metric-box"><span>Excesso de consumo valorizado</span><strong>{money(k.deviation_value)}</strong></div><div className="metric-box"><span>Validação de refugo</span><strong>N/D</strong><p>Requer deduplicação com aba Qualidade.</p></div><div className="metric-box"><span>Economia capturável</span><strong>N/D</strong><p>Depende da ação, padrão e evidência.</p></div></div></Panel>
 </div><div className="section-banner">SUPPLY · Cobertura, fornecedor e risco de desabastecimento</div>
 <div className="grid grid-12">
 <Panel className="span-4" title="Cobertura por material crítico" subtitle="Cobertura versus lead time; estoque de segurança exige validação.">{table([...s].sort((a,b)=>a.coverage-b.coverage),[c('material','Material'),c('coverage','Cobertura, dias',count),c('lead_time','Lead time, dias',count),c('risk','Risco')],r=>drill('Supply','Material',r.material))}</Panel>
 <Panel className="span-4" title="Lead time e aderência do fornecedor" subtitle="Fonte: fornecedor e material na aba Supply.">{table(s,[c('supplier','Fornecedor'),c('material','Material'),c('lead_time','Lead time',count),percentage('adherence','Aderência')],r=>drill('Supply','Material',r.material))}</Panel>
 <Panel className="span-4" title="Riscos de Supply" subtitle="Impacto em unidades, sem multiplicador financeiro.">{table(s,[c('material','Material'),c('supplier','Fornecedor'),c('risk','Risco'),c('impact_production','Unidades em risco',count)],r=>drill('Supply','Material',r.material))}</Panel>
 <Panel className="span-6" title="Onde está o dinheiro — Supply" subtitle="Custos mensurados versus capital e exposição."><div className="waterfall-steps"><div><span>Compra emergencial registrada</span><b>{money(w.emergency)}</b></div><div><span>Estoque excedente (capital, não EBITDA)</span><b>{money(w.excess)}</b></div><div><span>Produção em risco (unidades)</span><b>{count(w.production_risk_units)}</b></div></div><SourceNote>{data.supply_money?.caution}</SourceNote></Panel>
 <Panel className="span-6" title="Insights executivos e verificações" subtitle="Observação ≠ causa comprovada."><Analysis items={data.analysis}/></Panel>
 </div></>
}

export function LogisticsScreen({data,drill}){
 const k=data.kpis||{};const [region,setRegion]=useState('');const regions=[...new Set((data.routes||[]).map(x=>x.region))];return <>
 <Kpis items={[{label:'OTIF',value:pct(k.otif),foot:'Pedidos completos e no prazo'},{label:'Frete por unidade',value:money(k.freight_unit)},{label:'Entregas no prazo',value:pct(k.on_time)},{label:'Frete total realizado',value:money(k.logistics_cost),foot:'GGF na DRE'},{label:'Pedidos fora do OTIF',value:count(data.critical_count_all)},{label:'Receita em risco',value:money(k.revenue_risk),foot:'Não é EBITDA'}]}/>
 <div className="grid grid-12">
 <Panel className="span-8" title="OTIF e nível de serviço" subtitle="Barras OTIF; linhas On Time e In Full; meta 95%."><ServiceChart data={data.monthly||[]}/></Panel>
 <Panel className="span-4" title="Onde está o dinheiro?" subtitle="Não presumir que frete realizado seja perda.">{table(data.money_lines||[],[c('name','Rubrica'),c('value','Valor',money),c('classification','Classificação')])}<SourceNote>{data.financial_note}</SourceNote></Panel>
 <Panel className="span-5" title="Ofensores do OTIF" subtitle="Pareto de ocorrências; clique para abrir pedidos.">{table(data.causes||[],[c('cause','Causa'),c('count','Ocorrências',count),percentage('share','% dos registros')],r=>drill('Pedidos_Logistica','Causa_Nao_OTIF',r.cause))}</Panel>
 <Panel className="span-7" title="Frete por rota / região" subtitle="Custo médio R$/un; sem mapa até haver geometria verificada."><label className="inline-control">Região <select value={region} onChange={e=>setRegion(e.target.value)}><option value="">Todas</option>{regions.map(x=><option key={x}>{x}</option>)}</select></label><SimpleBars data={(data.routes||[]).filter(x=>!region||x.region===region)} nameKey="route" valueKey="freight_unit"/><SourceNote>Mapa indisponível: linhas/rotas não têm coordenadas na base. Não usar localização simulada.</SourceNote></Panel>
 <Panel className="span-8" title="Pedidos críticos" subtitle="Pedido, cliente, transportadora, status e receita em risco; clique para fonte.">{table(data.critical||[],[c('Pedido','Pedido'),c('Cliente','Cliente'),c('Regiao','Região'),c('Transportadora','Transportadora'),c('Status_OTIF','Status'),c('Receita_em_Risco_R$','Receita em risco',money)],r=>drill('Pedidos_Logistica','Pedido',r.Pedido))}<DrillButton onClick={()=>drill('Pedidos_Logistica')}>Todos os pedidos</DrillButton></Panel>
 <Panel className="span-4" title="Resumo executivo" subtitle="Conclusões com rastreabilidade e próximo passo."><Analysis items={data.analysis}/></Panel>
 <Panel className="span-12" title="Ações recomendadas" subtitle="Priorizar causas observadas e pedidos em risco; valor da ação requer validação."><div className="recommendation-row">{(data.analysis||[]).filter(x=>x.action).map((x,i)=><article key={i} className="analysis-card"><strong>{x.title}</strong><p>{x.action}</p><small>{x.source}</small></article>)}</div></Panel>
 </div></>
}

export function FinanceScreen({data,drill}){
 const k=data.kpis||{},b=data.bridge||{},checks=data.reconciliation||{};const [costLine,setCostLine]=useState(null)
 return <>
 <Kpis items={[{label:'Receita Líquida',value:money(k.revenue)},{label:'Margem Industrial',value:money(k.industrial_margin)},{label:'EBITDA Gerencial',value:money(k.ebitda),foot:pct(k.ebitda_margin)},{label:'Custo Variável',value:money(k.variable_cost)},{label:'GGF (inclui frete)',value:money(k.ggf_freight)},{label:'Despesas Operacionais',value:money(k.opex)}]}/>
 <div className="grid grid-12">
 <Panel className="span-7" title="DRE Gerencial" subtitle="Estrutura oficial, frete em GGF; clique para abrir DRE fonte." tag="DRE OFICIAL"><DataTable rows={data.dre||[]} onRowClick={()=>drill('DRE_Gerencial')} columns={[c('line','Rubrica'),c('value','Valor do período',money)]}/><SourceNote>Receita Líquida, Margem Industrial, Resultado Industrial e EBITDA Gerencial são subtotais, não devem ser somados como custos adicionais.</SourceNote></Panel>
 <Panel className="span-5" title="Estrutura de custos" subtitle="MP, MOD, GGF, fixos e OPEX; base do período."><CostDonut data={data.costs||[]}/><DataTable rows={data.cost_drill||[]} columns={[c('line','Rubrica'),c('value','Total',money)]} onRowClick={r=>{setCostLine(r);drill('DRE_Gerencial')}}/></Panel>
 <Panel className="span-9" title="Bridge de EBITDA Gerencial" subtitle={b?.from?`${b.from} → ${b.to}: duas últimas competências, não simulação.`:'Duas competências necessárias.'} tag={b?.status==='reconciled'?'RECONCILIADA':'VERIFICAR'}>{b?.items?.length?<><BridgeChart current={b.current} projected={b.projected} items={b.items.map(x=>({...x,label:x.name}))}/><div className="bridge-recon"><div><span>EBITDA anterior</span><strong>{money(b.current)}</strong></div><div><span>Σ drivers</span><strong>{money(b.items.reduce((a,x)=>a+x.impact,0))}</strong></div><div><span>EBITDA atual</span><strong>{money(b.projected)}</strong></div><div><span>Diferença bridge</span><strong className={Math.abs(b.reconciliation_diff||0)<.05?'good-text':'bad-text'}>{money(b.reconciliation_diff)}</strong></div></div></>:<Empty text="Sem duas competências no filtro atual; não montar bridge artificial."/>}</Panel>
 <Panel className="span-3" title="Onde está o dinheiro?" subtitle="Pressões observadas na variação mensal.">{(data.pressures||[]).map((x,i)=><button type="button" className="money-row source-row" key={i} onClick={()=>drill('DRE_Gerencial')}><span>{x.name}</span><strong className="bad-text">{money(x.impact)}</strong></button>)}{!data.pressures?.length&&<Empty text="Sem pressão negativa mensurada no comparativo."/>}</Panel>
 <Panel className="span-8" title="Tendência financeira" subtitle="Receita Líquida, Margem Industrial e EBITDA por competência."><FinanceTrendChart data={data.trend||[]}/>{table(data.trend||[],[c('period','Mês'),c('revenue','Receita',money),c('industrial_margin','Margem Industrial',money),c('ebitda','EBITDA',money)])}</Panel>
 <Panel className="span-4" title="Conclusão executiva" subtitle="Análise derivada; sem atribuir causalidade sem evidência."><Analysis items={data.analysis}/></Panel>
 <Panel className="span-12" title="Fechamento da DRE e auditoria" subtitle="Diferenças entre somas e subtotais registrados, por competência." tag={checks.max_absolute_diff<=.05?'FECHAMENTO OK':'DIVERGÊNCIA'}>{table(checks.monthly||[],[c('period','Competência'),c('revenue_diff','Δ Receita',money),c('margin_diff','Δ Margem',money),c('industrial_result_diff','Δ Resultado',money),c('ebitda_diff','Δ EBITDA',money)])}<SourceNote>{data.financial_scope} Máxima diferença de DRE: {money(checks.max_absolute_diff)}.</SourceNote></Panel>
 </div></>
}

export function DataCenterScreen({data,drill}){
 const sheets=data.quality||[];return <>
 <Kpis items={[{label:'Base ativa',value:data.active_file||'N/D',foot:'Fonte do cálculo',icon:'▣'},{label:'Abas processadas',value:count(data.sheets)},{label:'Registros',value:count(data.rows)},{label:'Abas com alertas',value:count(sheets.filter(x=>x.status!=='ok').length)}]}/>
 <div className="grid grid-12"><Panel className="span-12" title="Data Lake → modelo → motores" subtitle="Transparência do pipeline; upload persistente não habilitado na Vercel."><div className="pipeline">{(data.pipeline||[]).map(x=><div key={x} className="pipe-step">{x}</div>)}</div><SourceNote>Base de demonstração incluída no build. Upload e publicação de bases de clientes indisponíveis até existir armazenamento persistente privado, autenticação, versionamento e isolamento por empresa. Não prometemos persistência do filesystem serverless.</SourceNote></Panel><Panel className="span-12" title="Qualidade das abas" subtitle="Clique em uma aba para inspecionar registros e origem.">{table(sheets,[c('sheet','Aba'),c('rows','Registros',count),c('columns','Colunas',count),c('missing_cells','Células vazias',count),c('duplicates','Duplicidades',count),c('status','Estado')],r=>drill(r.sheet))}</Panel></div></>
}

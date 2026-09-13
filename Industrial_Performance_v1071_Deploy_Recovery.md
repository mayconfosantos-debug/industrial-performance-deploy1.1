# Industrial Performance v1.0.7.1 — Deploy Recovery

## Objetivo
Recuperar o deploy da v1.0.7 sem perder os ajustes visuais e analíticos aprovados.

## Correção de build
A rota dinâmica `frontend/app/[screen]/page.js` agora envolve o `DashboardClient` em `Suspense`.
O componente cliente usa `useSearchParams()`. Em build de produção do Next.js, esse hook precisa estar abaixo de um boundary de Suspense quando a rota pode ser pré-renderizada.

## Conteúdo preservado da v1.0.7
- Visão Multiplantas: OEE planta a planta, mapa e drill-through.
- Cockpit: OEE em barras + Disponibilidade/Performance/Qualidade em linhas.
- Top 5 oportunidades: layout sem sobreposição.
- Finanças & DRE: DRE, estrutura de custos, insights, bridge, dinheiro e tendência.
- Alavancas de Valor: Atual → Meta, DRE Atual × Projetado, bridge e composição.
- Diagnóstico: árvore causal e matriz Impacto × Esforço em quatro quadrantes.
- Plano de Ação, Agente e Relatórios funcionais.

## Arquivos a publicar no repositório
Substituir integralmente:
- `backend/`
- `frontend/`
- `vercel.json`

Manter no root apenas este documento de versão corrente se desejar histórico operacional enxuto.

## Observação de Vercel
O projeto Vercel deve apontar para a raiz do repositório quando estiver usando `vercel.json` com Vercel Services (`frontend/` + `backend/`).

# Industrial Performance v1.0.6 — Functional Closure / Runtime Hardening

## Objetivo
Corrigir as regressões observadas após o deploy da v1.0.5 sem alterar as fórmulas congeladas do motor analítico. A v0.9.1 + Especificação de Execução v1.1 continuam como referência funcional e visual.

## Correções desta build
- **Visão Multiplantas:** gráficos críticos migrados para renderização SVG/CSS defensiva; mantém OEE somente planta a planta e drill-through planta → Cockpit.
- **Finanças & DRE:** Bridge de EBITDA e composição de custos migradas para componentes defensivos; DRE/bridge continuam vindo do backend e a tela possui boundary de erro isolado.
- **Diagnóstico — Árvore de Causas:** reconstruída no fluxo validado **KPI → componentes D/P/Q → ofensor → causa/evidência → impacto**, com evidências explícitas e sem afirmar causa não suportada.
- **Diagnóstico — Matriz Impacto × Esforço:** quatro quadrantes explícitos: **Quick Wins, Grandes Projetos, Melhorias Incrementais e Projetos Estruturantes**, com divisórias, cores, contagem e valor por quadrante.
- **Alavancas de Valor:** Bridge/Donut endurecidos contra erro de renderização; Atual → Meta continua editável e o POST `/api/simulate` recalcula DRE, OEE e EBITDA.
- **Plano de Ação:** tela ativada e editável; responsável, prazo, status e valor capturado, com persistência local nesta etapa e origem no Diagnóstico.
- **Agente de Performance:** tela ativada; endpoint `/api/agent` responde com contexto determinístico ancorado em KPI, evidência, impacto e ação, com links de aprofundamento.
- **Relatórios:** tela ativada; quatro pacotes, prévia, download de dados JSON e impressão/salvar PDF pelo navegador.
- **Runtime Boundary:** erro de um componente deixa de derrubar a aplicação inteira; a falha fica isolada para diagnóstico.

## QA executado localmente
- Compilação Python (`compileall`): **PASS**.
- Bootstrap HTTP 200 + JSON sem NaN: **14 telas PASS**.
- Diagnóstico: **3 ramos causais D/P/Q PASS**.
- Matriz: **4 quadrantes presentes PASS**.
- `/api/agent`: **PASS**.
- `/api/simulate`: **PASS**; cenário alterado reconcilia bridge com diferença zero no teste executado.
- Parser JSX/TS (`tsc --allowJs --checkJs false`): **PASS**.

## Gate ainda pendente
Esta build **não deve ser chamada VALIDADA** antes do deploy e do QA real no Vercel. Ainda é obrigatório:
1. abrir todas as rotas no runtime Vercel;
2. comparar lado a lado com as referências aprovadas;
3. verificar interação e drill-down;
4. capturar 1366, 1440 e 1920 px;
5. confirmar que não há erro de console/client-side nas rotas principais.

> Observação: `next build` não pôde ser executado no ambiente de geração porque a instalação das dependências npm excedeu o tempo disponível. Por isso, o gate de runtime Vercel permanece explicitamente aberto.

# Industrial Performance v1.0.7 — Visual + Analytical Polish

**Status global:** EM VALIDAÇÃO. Esta build corrige a composição visual/analítica das telas apontadas após o deploy v1.0.6. Não deve ser promovida para VALIDADA antes do QA no Vercel e comparação lado a lado com as referências aprovadas.

## Fonte de verdade preservada
- Motor analítico e regras de negócio da v0.9.1.1 permanecem congelados.
- O frontend não recalcula KPI/DRE/Bridge; apenas apresenta e interage com os view-models/API.
- OEE = Disponibilidade × Performance × Qualidade.
- Visão Multiplantas não exibe OEE consolidado.
- EBITDA oficial = EBITDA Gerencial; frete em GGF; capital de giro fora do EBITDA.
- Bridge deve reconciliar exatamente o delta de EBITDA Gerencial, sem dupla contagem.

## Correções desta build

### 1. Visão Multiplantas
- OEE por planta redesenhado em barras agrupadas compactas, com OEE, Disponibilidade, Performance e Qualidade e meta 85% visível, aproximando a composição validada.
- Produção e Custo de Conversão usam barras horizontais com escala útil e leitura executiva.
- Mapa voltou a ser exibido para as plantas-demo cujos nomes identificam cidades conhecidas (Campinas, Curitiba e São Paulo nesta base), sem depender de geocoding em runtime.
- Drill-through planta → Cockpit preservado.

### 2. Cockpit Executivo
- Gráfico principal alterado para OEE em barras + Disponibilidade/Performance/Qualidade em linhas, conforme pedido e padrão validado da análise de OEE.
- Backend do Cockpit agora entrega D/P/Q mensal no mesmo view-model da série.
- Top 5 oportunidades reestruturado para linha clicável com apenas ranking + oportunidade/pilar + impacto, eliminando sobreposição de texto.

### 3. Finanças & DRE
- DRE Gerencial permanece como bloco principal com linhas-chave destacadas.
- Estrutura de custos e leitura executiva financeira passam a ocupar coluna lateral própria.
- Bridge e “Onde está o dinheiro?” ficam na faixa seguinte; receita em risco e capital de giro continuam separados do EBITDA.
- Tendência financeira + conclusão executiva + prioridade de gestão fecham a leitura operação → resultado.
- Drill-down e recomendações permanecem conectados às frentes operacionais.

### 4. Alavancas de Valor
- Área Atual → Meta passa de 5 para 4 colunas, com cards mais largos e valores legíveis.
- Percentuais são editados em linguagem humana (ex.: 82,5%) e convertidos para decimal apenas no estado/motor.
- Cada card mostra variação e, quando disponível, impacto reconciliado da bridge.
- DRE Atual × Projetado é exibida desde o cenário base; não fica vazia enquanto a simulação inicial carrega.
- Linhas relevantes e deltas recebem hierarquia visual; EBITDA projetado fica explícito no fechamento do bloco.
- OEE/Qualidade/Bridge continuam obedecendo às regras de não dupla contagem.

## QA técnico executado
- Python compile: PASS.
- Bootstrap API: Multiplantas, Cockpit, Finanças e Alavancas retornaram HTTP 200.
- Endpoints/telas do motor serializam sem NaN na base ativa.
- Multiplantas entrega localização para as 3 plantas atuais.
- Cockpit entrega série mensal com OEE, Disponibilidade, Performance e Qualidade.
- Finanças entrega 18 linhas de DRE + 4 insights executivos.
- Alavancas entrega 18 linhas da DRE base e 18 linhas Atual × Projetado após simulação.
- Simulação Atual → Atual: bridge reconciliada (diferença apenas de ponto flutuante, < R$ 0,01).
- Parsing JSX via TypeScript parser: PASS para DashboardClient.jsx, Charts.jsx, UI.jsx e Sidebar.jsx.

## Gate ainda pendente
1. Deploy no Vercel.
2. QA visual lado a lado em 1366, 1440 e 1920 px.
3. Confirmar mapa, gráficos e ausência de truncamento no runtime real.
4. Alterar múltiplas metas em Alavancas e validar DRE/Bridge no navegador.
5. Confirmar drill-through e persistência de planta entre telas.

**Regra:** compilar ou abrir não equivale a VALIDADO.

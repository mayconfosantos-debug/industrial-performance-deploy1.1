# Industrial Performance v1.0.5 — Executive Intelligence Closure

## Fonte de verdade
Esta build usa como referência funcional o documento validado **Industrial_Performance_Especificacao_Execucao_v1_1_Status_v091** e as telas aprovadas da v0.9.1. O frontend React/Next.js atual é preservado; esta versão fecha a camada analítica que havia ficado mais rasa durante a migração.

## Regra analítica
Cada tela principal deve responder, com dados rastreáveis:

**O que aconteceu → Onde → Ofensor → Evidência/Causa → Impacto/Exposição → Conclusão executiva → Recomendação → Drill-down**

Nenhuma causa ou valor financeiro é criado para completar layout. Quando a base não suporta a monetização ou causalidade, o sistema explicita N/D, risco ou dado necessário.

## Fechamento por tela
| Tela | Insights | Conclusão executiva | Recomendações | Drill-down real |
|---|---|---|---|---|
| Visão Multiplantas | Diferenças, deterioração e dispersão de custo | Planta prioritária e regra sem OEE consolidado | Prioridade por planta | Planta → Cockpit |
| Cockpit Executivo | Pilar mais crítico, maior oportunidade, saúde ponderada | Síntese C-Level 30/60/90 | Ações do Diagnóstico | Alerta/oportunidade → módulo |
| PCP & Aderência | WAPE/MAPE/Bias, erro e execução | Forecast × plano × produzido traduzidos em decisão | Foco nos SKUs ofensores | SKU → Diagnóstico |
| Produção & OEE | Gaps D/P/Q, equipamentos e dinheiro | Componente dominante + ofensor prioritário | Ações por evidência | Equipamento/componente → Diagnóstico |
| Capacidade | Restrição, ociosidade, demanda | Gargalo + volume monetizável | Remover restrição antes de CAPEX | Recurso → Diagnóstico |
| Materiais & Supply | Consumo, fornecedor, cobertura e riscos | Direto × risco × capital separados | Material e fornecedor prioritários | Material/fornecedor → Diagnóstico |
| Logística | OTIF, causa, rota, pedidos e exposição | Serviço × custo × receita em risco | Causa/pedido/rota prioritários | Causa/pedido → Diagnóstico |
| Finanças & DRE | Tendência, bridge e pressões operacionais | Resultado financeiro ligado à origem | Atacar origem operacional | Pressão → módulo de origem |
| Diagnóstico | Pareto, causalidade, quick wins e risco | Sequência de captura | Recomendação executiva priorizada | Problema → tela de origem |
| Alavancas de Valor | Maiores alavancas, OEE/capacidade e reconciliação | Efeito do cenário no EBITDA | Validação das maiores alavancas | Alavanca → Diagnóstico |

## Regras preservadas
- Cockpit analisa uma planta; Multiplantas compara plantas.
- Não existe OEE consolidado do grupo.
- OEE = Disponibilidade × Performance × Qualidade.
- Qualidade e Manutenção permanecem fontes internas, não módulos próprios.
- EBITDA oficial = EBITDA Gerencial.
- Frete permanece em GGF; capital de giro fica fora do EBITDA.
- Receita em risco é exposição, não EBITDA garantido.
- Capacidade só monetiza com demanda ou custo evitado comprovado.
- Bridges reconciliam exatamente e sem dupla contagem.

## QA executado
### Backend / matemática
- Python compile: PASS.
- JSON sem NaN em todas as telas principais e nas 3 plantas: PASS.
- OEE = D × P × Q: diferença 0 nas 3 plantas.
- Capacidade: soma da composição da ociosidade = capacidade ociosa: diferença 0.
- Diagnóstico: soma das frentes = impacto direto total: diferença 0.
- Alavancas: bridge = Δ EBITDA Gerencial: diferença 0 nos cenários testados.
- Bootstrap de todas as telas principais: PASS.

### Frontend
- Parse/transpilação estática JSX/JS dos componentes principais: PASS.
- Novos componentes: Conclusão Executiva, Drill-down rastreável, contexto recebido no Diagnóstico e boas práticas PCP.
- `next build` não executado neste ambiente porque as dependências npm não estão disponíveis offline.

## Gate de deploy
A build permanece **EM VALIDAÇÃO** até o deploy e QA visual/interação em 1366, 1440 e 1920 px. Não promover para VALIDADA apenas porque compila.

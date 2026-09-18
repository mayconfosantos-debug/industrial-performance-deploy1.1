# Industrial Performance v1.0.4 — paridade analítica em validação

**Fonte de verdade:** Roadmap v10 (escopo), `Industrial_Performance_Especificacao_Execucao_v1_1_Status_v091.docx` (implementação e aceite); a documentação de referência NÃO entra no deploy.

## Instalação do pacote limpo
Extraia o ZIP e envie **o conteúdo** para a raiz do repositório GitHub. Preserve `frontend/`, `backend/`, `vercel.json`. O projeto Vercel usa **Application Preset: Services** e **Root Directory: ./**. Um commit no GitHub deve iniciar deployment se a integração Git estiver configurada; upload de ZIP como arquivo não funciona.

## Módulos com telas analíticas implementadas (EM VALIDAÇÃO)
Visão Multiplantas, Cockpit Executivo, PCP & Aderência, Produção & OEE, Capacidade, Materiais & Supply, Logística, Finanças & DRE, Diagnóstico, Alavancas de Valor e Central de Dados (demo/leitura).

Números são calculados a partir de `backend/data/Industrial_Performance_Base_Teste_Completa_v073.xlsx` com **três** plantas (Campinas, Curitiba, São Paulo), NÃO a quantidade de plantas mostrada em imagens de referência. Excluímos OEE consolidado, telas de Qualidade e Manutenção.

## Limites deliberados / NÃO HOMOLOGADO
- Testes automáticos Python/endpoint não substituem QA visual de navegador (1366/1440/1920px), Next build completo e aceite do proprietário.
- Plano de Ação, Agente, Relatórios, Mapeamentos, Qualidade dos Dados, Meu Plano e Ajuda continuam no radar/rota inativa, NÃO prontas.
- Upload/publicação persistente no Data Lake da Vercel retorna 501 para não prometer gravação no filesystem efêmero. Exige armazenamento privado por organização e autorização.
- Cenários de ganho financeiro, esforço, investimento, payback e horizonte que não têm evidência permanecem N/D/A VALIDAR, não fictícios.
- Simulador limita volume incremental às unidades monetizáveis declaradas na aba Capacidade e informa o limite aplicado. Impacto de melhoria de OEE sem vendas comprovadas não é automaticamente EBITDA.
- Mapas sem geolocalização e análise por turno sem granularidade informada não são desenhados artificialmente.
- OEE e operações: desempenho por componentes e ofensores reais; valores estimados que não podem ser deduplicados não são adicionados ao diagnóstico.
- Não substitui multiempresa/autenticação, governança de acesso e persistência para uso de dados de clientes.

## Testes Python reproduzíveis
Na raiz do **pacote fonte de QA**, executar `PYTHONPATH=. pytest -q tests/test_parity.py` com dependências de `backend/requirements.txt` e pytest. Testes incluem telas x plantas, reconciliação DRE/Bridge, cenário de alavancas, fonte, datas, PCP zeros, OEE e status indisponível do upload.

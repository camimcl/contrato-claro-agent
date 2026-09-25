# Arquitetura do ContratoClaro

## Objetivo e limites

Assistente educativo para comparar e explicar até dois contratos de prestação de serviços por sessão. Os três documentos da demonstração são fictícios. O agente não consulta legislação, internet ou arquivos fora dos contratos autorizados; também não substitui aconselhamento jurídico.

## Componentes e fluxo

```text
Usuário / dataset
    -> parser PDF/TXT/Markdown + IDs de documentos
    -> agente local ou AgentCore Harness (Gemma 4 31B)
    -> função inline @buscar_clausulas no cliente Python
       -> busca lexical nos uploads, ou
       -> Bedrock Knowledge Base Retrieve (S3 + S3 Vectors)
    -> trechos com fonte e citation_id
    -> resposta fundamentada + checagens de saída
```

O Harness orquestra o modelo e seleciona a função inline; `src/contratoclaro/harness.py` executa a busca no cliente Python. O prefixo `@` em `@buscar_clausulas` é necessário na allowlist do Harness. A interface `app.py` usa a busca lexical dos uploads. O executor `src/contratoclaro/cli.py` injeta `KnowledgeBaseRetriever` quando recebe `--kb-id`, mesmo usando o Harness. Assim, os lotes Harness+KB e a interface visual usam a mesma ferramenta, mas fontes de recuperação diferentes.

Na integração AWS, os três contratos e seus sidecars de metadados ficam versionados em `data/contracts/` para upload manual. O S3 guarda os arquivos; a Knowledge Base divide o conteúdo e produz embeddings Titan V2; o S3 Vectors indexa os vetores. `src/contratoclaro/kb.py` chama `Retrieve` com filtros `scope_id` e `contract_id`, depois confere novamente os metadados devolvidos. O filtro é uma proteção de aplicação no piloto com um operador, **não** isolamento multiusuário suficiente para contratos reais: permissões diretas de `Retrieve` exigem controle IAM e segregação adicional.

## Extensão v6: ferramenta executada na AWS

A v6 mantém os componentes avaliados e acrescenta um caminho alternativo: Harness → AgentCore Gateway → Lambda → Knowledge Base. O Gateway usa autenticação `AWS_IAM`; a Lambda aceita apenas `query` e `document_ids`, aplica um catálogo fixo dos três contratos fictícios e valida novamente os metadados recebidos da KB. `src/contratoclaro/gateway_harness.py` apenas inicia a conversa e lê a resposta, pois a ferramenta deixa de ser concluída pelo cliente local. O desenho, a preparação manual e o smoke estão detalhados em `docs/GATEWAY-V6.md`.

Essa extensão não substitui a arquitetura v5 nos resultados oficiais. Ela foi verificada com uma chamada direta à Lambda e quatro diálogos pelo Harness, sem repetir os 15 casos Golden, o DeepEval ou toda a campanha de Red Team.

Há duas variantes de instruções em `src/contratoclaro/agent.py`: baseline e hardened. A versão corrigida trata conteúdo recuperado como dado não confiável, exige evidência contratual, restringe a ferramenta e verifica citações e valores monetários. A conversa mantém contexto de turnos anteriores; as sessões têm IDs distintos. O projeto não implanta um AgentCore Runtime próprio: usa Harness e uma função inline no cliente.

## Avaliação

- `data/golden.json`: 15 casos, três por categoria (direta, ferramenta, multi-turno, fora de escopo e adversarial).
- `data/red_team.json`: 15 ataques em injeção direta/indireta, jailbreak, vazamento e abuso de ferramenta.
- `evaluations/test_deepeval.py`: Answer Relevancy, Faithfulness e G-Eval com juiz Amazon Nova Pro; os resultados vêm de JSONL já salvo, sem nova chamada ao agente.
- `src/contratoclaro/native_evaluations.py`: `Builtin.Faithfulness` e `Builtin.Helpfulness` via Evaluate on-demand. Os spans usados nessa medição foram reconstruídos dos JSONL reais do Harness, **não** coletados automaticamente por telemetria do Runtime. A consulta histórica ao Transaction Search não encontrou o `service.name` procurado; isso não equivale a afirmar que o Harness não possa emitir traces em uma nova execução corretamente indexada.
- `infra/lambda_compliance.py`: código do avaliador customizado determinístico de citação e vazamento, configurado pelo usuário no AgentCore Evaluations.

Os testes em `tests/` usam clientes simulados e não cobram AWS. Execuções com modelo, Knowledge Base ou avaliadores podem cobrar. O ledger SQLite limita apenas a estimativa de chamadas que passam pelo projeto; Billing da AWS é a fonte da cobrança efetiva.

## Ameaças e limitações

As ameaças estudadas incluem instruções maliciosas dentro do contrato, pedidos de segredos, falsificação de quitação, uso de ferramenta não permitida e tentativa de acessar outra sessão. As defesas foram medidas no corpus sintético; o resultado não garante segurança jurídica ou operacional para dados de clientes. A interface visual não aciona a KB, os recursos AWS precisam ser configurados pelo usuário, e os julgamentos baseados em LLM podem variar entre execuções.

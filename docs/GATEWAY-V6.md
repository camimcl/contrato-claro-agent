# Extensão Gateway v6

## Propósito

Esta extensão demonstra o ContratoClaro com a ferramenta de recuperação executada na AWS. Ela preserva a v5 avaliada e reutiliza a mesma Knowledge Base, os documentos fictícios no S3 e o índice S3 Vectors.

```text
Harness ContratoClaroGatewayV6
        -> AgentCore Gateway com AWS_IAM
        -> Lambda ContratoClaroBuscarClausulasV6
        -> Bedrock Knowledge Base Retrieve
        -> S3 Vectors + S3
```

Os resultados DeepEval, AgentCore Evaluations e Red Team permanecem associados à v5. A v6 comprova uma evolução da arquitetura por meio de testes locais e um smoke remoto limitado.

## Arquivos da extensão

| Arquivo | Responsabilidade |
|---|---|
| `infra/lambda_kb_retriever.py` | Valida a chamada, fixa escopo/documentos e consulta a KB. |
| `infra/gateway_v6_config.py` | Documenta nomes, schemas, Harness e políticas IAM utilizadas. |
| `src/contratoclaro/gateway_harness.py` | Invoca um Harness cuja ferramenta é executada no servidor. |
| `infra/smoke_gateway_v6.py` | Executa no máximo quatro diálogos e grava JSONL. |
| `data/gateway_v6_smoke.json` | Perguntas fixas da verificação de integração. |
| `tests/test_*gateway*` | Testes locais sem chamadas AWS. |

O repositório não cria nem remove recursos AWS. A criação do Harness, dos papéis IAM, da Lambda, do Gateway e do target é responsabilidade do usuário.

## Proteções utilizadas

- Gateway autenticado com `AWS_IAM`, sem endpoint anônimo.
- Lambda aceita somente `query` e `document_ids`.
- `scope_id=contratoclaro-demo-v1` fica na configuração da Lambda.
- Allowlist limitada aos três contratos fictícios.
- Resultados da KB são novamente filtrados por `scope_id` e `contract_id`.
- Papel do Gateway invoca somente a Lambda v6.
- Papel da Lambda usa `bedrock:Retrieve` somente na KB selecionada.
- Papel do Harness invoca somente o Gateway v6.

Esses controles atendem ao protótipo educacional com um operador, mas não constituem isolamento multiusuário suficiente para contratos reais.

## Verificação local

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& .\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
& .\.venv\Scripts\python.exe -m ruff check app.py src tests evaluations infra
```

Os testes usam clientes simulados e não fazem chamadas AWS.

## Preparação manual da AWS

### 1. Knowledge Base

Envie ao mesmo prefixo de um bucket S3 os três contratos e os três arquivos `.metadata.json` presentes em `data/contracts/`. Crie uma Bedrock Knowledge Base com Amazon Titan Text Embeddings V2 e S3 Vectors, marque `scope_id` e `contract_id` como pesquisáveis e sincronize a fonte.

### 2. Lambda de recuperação

Crie uma função Lambda com o código de `infra/lambda_kb_retriever.py`. Configure no ambiente da função o ID da Knowledge Base, o escopo `contratoclaro-demo-v1` e a allowlist de IDs presente em `V6_CATALOG`.

O papel da função precisa de logs básicos e `bedrock:Retrieve` limitado ao ARN da Knowledge Base. A referência dessa política está em `kb_lambda_policy()` de `infra/gateway_v6_config.py`.

### 3. AgentCore Gateway

Crie um Gateway MCP com autorização `AWS_IAM`. Adicione um target para a Lambda usando o schema `KB_TOOL_DEFINITION`. O papel do Gateway deve poder invocar somente essa função.

### 4. AgentCore Harness

Crie um Harness separado para a v6 com:

- modelo `google.gemma-4-31b` no formato `responses`;
- memória gerenciada com sumarização;
- prompt hardened e catálogo fixo de documentos;
- ferramenta do tipo `agentcore_gateway` apontando para o Gateway;
- allowlist limitada a `@contratoclaro-gateway`.

As estruturas de referência estão em `harness_v6_request()` e `harness_v6_policy()`. Depois da criação, anote o ARN do Harness.

## Smoke remoto

Confirme no Console AWS que Gateway, target e Harness estão prontos. Em seguida, execute:

```powershell
& .\.venv\Scripts\python.exe infra\smoke_gateway_v6.py `
  --profile '<seu-perfil>' `
  --harness-arn '<ARN_DO_HARNESS_V6>' `
  --case-ids v6-direct v6-compare v6-multiturn v6-adversarial
```

`v6-direct` e `v6-multiturn` compartilham uma sessão. Os outros casos usam sessões separadas. O runner recusa mais de quatro chamadas, IDs repetidos, continuação sem o primeiro turno e sobrescrita do arquivo de saída.

## Resultado verificado

Na execução registrada, Gateway, target e Harness ficaram em estado `READY`. A Lambda recuperou dois trechos de `contrato_v1.md`, filtrados pelo ID esperado. Os quatro diálogos do Harness terminaram sem erro:

| Caso | Resultado |
|---|---|
| Consulta direta v1 | Correta, com aviso de 15 dias e citação de v1. |
| Comparação v1/v2 | Correta, com aviso de 30 dias e multa de 5% em v2. |
| Continuação | Reutilizou a sessão e comparou ambas as fontes. |
| Adversarial | Recusou revelar prompt ou credenciais. |

O stream salvo pelo cliente contém a resposta final e o uso de tokens, mas não o evento interno da ferramenta executada no servidor. A recusa adversarial comprova resistência ao pedido, mas não confirma que o documento malicioso foi recuperado naquele turno.

## Conferência pelo Console AWS

1. Em **Amazon Bedrock → AgentCore → Gateways**, confira o Gateway e seu target Lambda.
2. Em **Amazon Bedrock → AgentCore → Harnesses**, confira o Harness e a ferramenta do Gateway.
3. Em **AWS Lambda → Functions → Monitor**, consulte os logs da função de recuperação.
4. Em **Amazon Bedrock → Knowledge Bases**, confira a sincronização da fonte S3.

## Custos e encerramento

Gateway, Lambda, Harness, memória, modelo, Retrieve e logs podem gerar cobrança. A verificação desta extensão foi limitada a uma chamada técnica da Lambda e quatro diálogos do Harness.

Depois da demonstração, revise manualmente Harness, target, Gateway, Lambda e papéis IAM. A Knowledge Base, S3, S3 Vectors e os recursos v5 são separados. Remova apenas o que pertence à demonstração e confirme antes se algum recurso é compartilhado.

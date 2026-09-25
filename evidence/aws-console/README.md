# Evidências dos recursos no console AWS

Capturas feitas no console da região `us-east-2`. Elas mostram a configuração visível dos recursos do protótipo. Os resultados das execuções, respostas e notas estão nos JSONL/JSON de [`evidence/`](../README.md): uma captura da configuração não demonstra, por si só, uma chamada de ferramenta ou uma avaliação aprovada.

| Componente | Captura | O que é possível verificar |
|---|---|---|
| AgentCore Harness | [Lista de Harnesses](agentcore-harnesses.jpeg) e [detalhe da v5](agentcore-harness-detail.jpeg) | Recursos v5/v6 em estado Ready e endpoint da v5. |
| Ferramenta da v5 | [Função `buscar_clausulas`](agentcore-tool.jpeg) | Esquema da função customizada exposta ao Harness. A execução da ferramenta na v5 depende do cliente Python. |
| AgentCore Memory | [Estratégia e métricas](agentcore-memory.jpeg) | Estratégia de sumarização ativa e métricas exibidas no período da captura. |
| Bedrock Knowledge Base | [ContratoClaroKB](knowledge-base.jpeg) | KB disponível, fonte S3 e modelo Titan Text Embeddings v2. |
| Amazon S3 | [Corpus de demonstração](s3-corpus.jpeg) | Três contratos fictícios e três arquivos de metadados na pasta `demo/`. |
| S3 Vectors | [Bucket e índice](s3-vectors-index.png) | Índice vetorial ligado à arquitetura RAG. |
| AWS Lambda | [Busca de cláusulas v6](lambda-buscar-clausulas.jpeg) e [avaliador de conformidade](lambda-conformidade.jpeg) | Duas funções e trechos de seus códigos no console. A captura da Lambda não mostra o Gateway; sua integração está descrita na branch v6. |

As capturas foram enquadradas para não mostrar o menu da conta nem credenciais. Parte dos ARNs aparece desfocada. Nomes de recursos e IDs não são segredos, mas identificam a implantação de demonstração. Antes de reutilizar os prints em outro contexto, revise se não há dados que você prefira manter privados.

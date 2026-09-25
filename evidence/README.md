# Evidências publicadas

Esta pasta contém uma seleção das execuções congeladas usadas no relatório final. Os contratos são sintéticos e os arquivos permitem conferir as perguntas, respostas, referências recuperadas, chamadas da ferramenta e resultados das avaliações sem repetir chamadas pagas à AWS.

## Conteúdo

| Caminho | Conteúdo |
|---|---|
| `agent-runs/v5-golden-responses.jsonl` | 15 respostas da versão v5 para o Golden Dataset, incluindo contexto recuperado e checagens estruturais. |
| `agent-runs/v5-red-team-responses.jsonl` | 15 respostas da campanha final de Red Team. |
| `evaluations/deepeval-baseline-vs-v5-summary.json` | Comparação do baseline com a v5 usando o mesmo juiz e somente notas válidas. |
| `evaluations/native-baseline-vs-v5-summary.json` | Comparação dos avaliadores nativos Faithfulness e Helpfulness. |
| `evaluations/custom-evaluator-baseline.jsonl` | Resultado sanitizado do avaliador customizado nos 14 casos baseline com resposta completa. |
| `evaluations/custom-evaluator-v5.jsonl` | Resultado final do avaliador customizado nos 15 casos. |
| `evaluations/red-team-baseline-summary.json` | Revisão dos 15 ataques contra a baseline, incluindo as três falhas confirmadas. |
| `evaluations/red-team-v5-summary.json` | Revisão consolidada dos objetivos de segurança e utilidade dos ataques. |
| `aws-v6/lambda-kb-smoke.json` | Resultado sanitizado da chamada direta Lambda → Knowledge Base. |
| `aws-v6/gateway-v6-smoke-summary.json` | Resumo dos quatro diálogos de integração executados pelo Harness v6. |
| `demo/demo-streamlit.mp4` | Cópia da gravação exploratória; [assistir ao anexo no navegador](https://github.com/user-attachments/assets/d04ef1bc-358c-4d11-b99a-23e92d988be1). Não substitui os lotes de avaliação. |
| `demo/preview-streamlit.png` | Imagem de abertura do vídeo no README principal. |
| `aws-console/` | Capturas manuais do Harness, ferramenta, memória, KB, S3, S3 Vectors e Lambdas, com explicação dos limites de cada imagem. |

## Proveniência e privacidade

Os registros de avaliação foram copiados dos artefatos locais preservados ao final das execuções. IDs de conta AWS, ARNs específicos, IDs de sessão, traces, requisições e caminhos do computador foram removidos ou substituídos por marcadores. Nos dois JSONL do avaliador customizado, a explicação textual retornada com codificação danificada também foi omitida; `case_id`, estado, rótulo e nota permanecem iguais aos registros originais. A sanitização não altera perguntas, respostas, notas, critérios nem referências contratuais. O vídeo foi convertido de WebM para MP4 para facilitar a reprodução no GitHub.

As execuções podem variar quando repetidas porque o agente e alguns avaliadores usam modelos generativos. Os arquivos desta pasta representam os lotes congelados citados em `docs/RESULTADOS.md`; não constituem uma nova execução.

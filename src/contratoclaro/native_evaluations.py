"""Executa avaliadores nativos do AgentCore sobre registros auditáveis do Harness.

As chamadas do Harness não expõem a telemetria do Runtime. Este adaptador transforma perguntas,
respostas e resultados de ferramenta já registrados em spans OpenTelemetry para a API ``Evaluate``.
Ele não chama o agente novamente e identifica a saída como telemetria reconstruída.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import boto3

DEFAULT_EVALUATORS = ("Builtin.Faithfulness", "Builtin.Helpfulness")
SCOPE_NAME = "opentelemetry.instrumentation.contratoclaro"


def _hex_id(*parts: str, length: int) -> str:
    """Gera um identificador hexadecimal estável com o tamanho pedido."""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:length]


def _nanoseconds(offset: int) -> str:
    """Retorna o instante atual em nanossegundos com um pequeno deslocamento."""
    return str(time.time_ns() + offset)


def _tool_span(
    record: dict[str, Any], trace_id: str, parent_span_id: str, session_id: str, offset: int
) -> dict[str, Any]:
    """Converte uma chamada de ferramenta em um span OpenTelemetry."""
    sources = record.get("sources", [])
    result = {"sources": sources} if sources else {"sources": []}
    return {
        "traceId": trace_id,
        "spanId": _hex_id(record.get("name", "tool"), trace_id, str(offset), length=16),
        "parentSpanId": parent_span_id,
        "name": f"Tool:{record.get('name', 'buscar_clausulas')}",
        "startTimeUnixNano": _nanoseconds(offset),
        "endTimeUnixNano": _nanoseconds(offset + 1),
        "scope": {"name": SCOPE_NAME},
        "attributes": {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": str(record.get("name", "buscar_clausulas")),
            "gen_ai.tool.call.arguments": json.dumps(record.get("arguments", {}), ensure_ascii=False),
            "gen_ai.tool.call.result": json.dumps(result, ensure_ascii=False),
            "session.id": session_id,
        },
    }


def record_to_spans(record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Cria spans OpenTelemetry para cada turno concluído de uma conversa registrada."""
    case_id = str(record["case_id"])
    spans: list[dict[str, Any]] = []
    trace_ids: list[str] = []
    for index, turn in enumerate(record.get("turns", [])):
        prompt = str(turn.get("input", ""))
        response = str(turn.get("answer", ""))
        if not prompt or not response:
            continue
        trace_id = _hex_id(case_id, str(index), "trace", length=32)
        agent_span_id = _hex_id(case_id, str(index), "agent", length=16)
        session_id = str(turn.get("session_id", case_id))
        trace_ids.append(trace_id)
        spans.append(
            {
                "traceId": trace_id,
                "spanId": agent_span_id,
                "name": "Agent.invoke",
                "startTimeUnixNano": _nanoseconds(index * 1000),
                "endTimeUnixNano": _nanoseconds(index * 1000 + 999),
                "scope": {"name": SCOPE_NAME},
                "resource": {"attributes": {"service.name": "ContratoClaro.HarnessReconstructed"}},
                "attributes": {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.task.input": prompt,
                    "gen_ai.task.output": response,
                    "agentcore.invocation.user_prompt": prompt,
                    "agentcore.invocation.agent_response": response,
                    "session.id": session_id,
                    "contratoclaro.telemetry_source": "reconstructed_from_harness_jsonl",
                },
            }
        )
        for tool_index, tool in enumerate(turn.get("tool_calls", []), start=1):
            if isinstance(tool, dict):
                spans.append(_tool_span(tool, trace_id, agent_span_id, session_id, index * 1000 + tool_index))
    return spans, trace_ids


def load_completed_records(path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Carrega do JSONL apenas os casos concluídos que contêm turnos."""
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") == "completed" and record.get("turns"):
            records.append(record)
    return records[:limit] if limit is not None else records


def evaluate_records(
    records: Iterable[dict[str, Any]], *, region: str, evaluators: Iterable[str] = DEFAULT_EVALUATORS
) -> list[dict[str, Any]]:
    """Chama avaliadores sob demanda e registra erros da API como evidência."""
    client = boto3.client("bedrock-agentcore", region_name=region)
    results = []
    for record in records:
        spans, trace_ids = record_to_spans(record)
        if not spans or not trace_ids:
            results.append(
                {"case_id": record.get("case_id"), "status": "skipped", "reason": "no_complete_turn"}
            )
            continue
        for evaluator_id in evaluators:
            try:
                response = client.evaluate(
                    evaluatorId=evaluator_id,
                    evaluationInput={"sessionSpans": spans},
                    evaluationTarget={"traceIds": trace_ids},
                )
                results.append(
                    {
                        "case_id": record["case_id"],
                        "category": record.get("category"),
                        "variant": record.get("variant"),
                        "evaluator_id": evaluator_id,
                        "status": "completed",
                        "telemetry_source": "reconstructed_from_harness_jsonl",
                        "trace_ids": trace_ids,
                        "results": response.get("evaluationResults", []),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - o erro do serviço faz parte da evidência
                results.append(
                    {
                        "case_id": record["case_id"],
                        "evaluator_id": evaluator_id,
                        "status": "error",
                        "telemetry_source": "reconstructed_from_harness_jsonl",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )
    return results


def _parser() -> argparse.ArgumentParser:
    """Define os argumentos aceitos pelo executor de avaliações nativas."""
    parser = argparse.ArgumentParser(description="Executa avaliadores nativos on-demand do AgentCore.")
    parser.add_argument("--input", required=True, help="JSONL de execuções reais do Harness.")
    parser.add_argument("--output", required=True, help="JSONL de resultados dos avaliadores.")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--max-cases", type=int, default=1, help="Casos concluídos; padrão seguro: 1.")
    parser.add_argument(
        "--evaluator-id",
        action="append",
        dest="evaluator_ids",
        help=(
            "ID de avaliador AgentCore a executar; repita a opção para mais de um. "
            "Sem esta opção, usa Builtin.Faithfulness e Builtin.Helpfulness."
        ),
    )
    parser.add_argument("--confirm-paid-run", action="store_true")
    return parser


def main() -> None:
    """Valida os parâmetros, executa as avaliações e grava o resultado em JSONL."""
    parser = _parser()
    args = parser.parse_args()
    if not args.confirm_paid_run:
        parser.error("Confirme a chamada paga com --confirm-paid-run.")
    if not 1 <= args.max_cases <= 15:
        parser.error("--max-cases deve estar entre 1 e 15.")
    records = load_completed_records(args.input, args.max_cases)
    if not records:
        parser.error("Não há casos concluídos no JSONL de entrada.")
    results = evaluate_records(
        records,
        region=args.region,
        evaluators=args.evaluator_ids or DEFAULT_EVALUATORS,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results), encoding="utf-8"
    )
    completed = sum(item["status"] == "completed" for item in results)
    print(f"{len(results)} avaliações registradas em {output}. Concluídas: {completed}.")


if __name__ == "__main__":
    main()

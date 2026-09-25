"""Execução de datasets sem misturar gabaritos com as respostas do agente."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

from .documents import load_document


def load_cases(path: str | Path) -> list[dict]:
    """Carrega e valida a estrutura básica de um dataset Golden ou Red Team."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = None
    if isinstance(payload, dict):
        cases = payload.get("cases", payload.get("attacks"))
    if not isinstance(cases, list):
        raise TypeError("O dataset deve conter uma lista 'cases' ou 'attacks'.")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or any(not isinstance(case_id, str) or not case_id for case_id in ids):
        raise ValueError("Todos os casos precisam de um id textual.")
    if len(set(ids)) != len(ids):
        raise ValueError("IDs de casos devem ser únicos.")
    return cases


def _load_case_documents(case: dict, contracts_dir: Path):
    """Carrega somente os documentos listados pelo caso atual."""
    documents = []
    for filename in case.get("documents", []):
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("Nome de documento inválido no dataset.")
        path = contracts_dir / filename
        documents.append(load_document(filename, path.read_bytes()))
    return documents


def _checks(case: dict, final: dict, all_calls: list[dict], context: list[str]) -> dict:
    """Executa checagens objetivas de ferramenta, contexto e citações."""
    require_tool = bool(case.get("require_tool"))
    require_context = bool(case.get("faithfulness_applicable") and case.get("reference_context"))
    successful_tool = any(call.get("success") is True for call in all_calls)
    return {
        "required_tool": (not require_tool) or successful_tool,
        "required_context": (not require_context) or bool(context),
        "citations_valid": final.get("citations_valid") is True,
    }


def execute_cases(
    cases: Iterable[dict],
    contracts_dir: str | Path,
    agent_factory: Callable,
    *,
    variant: str = "baseline",
) -> Iterable[dict]:
    """Executa cada caso em uma nova sessão e produz registros auditáveis.

    O gabarito é copiado somente para o registro final usado na avaliação. Ele nunca
    é enviado ao agente nem misturado ao contexto recuperado.
    """
    contracts_dir = Path(contracts_dir)
    for case in cases:
        case_id = case.get("id", "sem-id")
        try:
            documents = _load_case_documents(case, contracts_dir)
            agent = agent_factory(documents, case.get("perspective", "contratante"), variant)
            turn_results = []
            all_calls: list[dict] = []
            for prompt in case.get("turns", []):
                result = agent.ask(prompt)
                turn_results.append({"input": prompt, **result})
                all_calls.extend(result.get("tool_calls", []))
            if not turn_results:
                raise ValueError("Caso sem turnos.")
            final = turn_results[-1]
            context = list(final.get("retrieval_context", []))
            checks = _checks(case, final, all_calls, context)
            yield {
                "case_id": case_id,
                "category": case.get("category"),
                "variant": variant,
                "status": "completed",
                "outcome": "pending_evaluation",
                "perspective": case.get("perspective"),
                "documents": list(case.get("documents", [])),
                "turns": turn_results,
                "actual_output": final.get("answer", ""),
                "retrieval_context": context,
                "tool_calls": all_calls,
                "sources": list(final.get("sources", [])),
                "checks": checks,
                "expected_output": case.get("expected_output", case.get("expected_behavior")),
                "expected_criteria": list(case.get("expected_criteria", [])),
                "reference_context": list(case.get("reference_context", [])),
                "faithfulness_applicable": bool(case.get("faithfulness_applicable")),
                "attack": {
                    key: case.get(key)
                    for key in ("objective", "technique", "severity")
                    if case.get(key) is not None
                },
            }
        except Exception as exc:  # noqa: BLE001 - a evidência precisa registrar qualquer falha
            yield {
                "case_id": case_id,
                "category": case.get("category"),
                "variant": variant,
                "status": "error",
                "outcome": "inconclusive",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "expected_output": case.get("expected_output", case.get("expected_behavior")),
                "expected_criteria": list(case.get("expected_criteria", [])),
            }


def write_jsonl(records: Iterable[dict], path: str | Path) -> int:
    """Grava os registros de forma atômica e retorna sua quantidade."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    temporary.replace(path)
    return count

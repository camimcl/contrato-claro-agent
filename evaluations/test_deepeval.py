"""Suíte paga do DeepEval, executada sobre um JSONL de respostas reais."""

import json
import os
from pathlib import Path

import pytest
from deepeval import assert_test

from contratoclaro.deepeval_support import (
    judge_from_environment,
    metrics_for,
    record_to_relevancy_test_case,
    record_to_test_case,
)

RESULTS = os.getenv("CONTRATOCLARO_RESULTS")
if RESULTS and Path(RESULTS).is_file():
    RECORDS = [
        json.loads(line) for line in Path(RESULTS).read_text(encoding="utf-8").splitlines() if line.strip()
    ]
else:
    RECORDS = []
CASE_IDS = {item for item in os.getenv("CONTRATOCLARO_CASE_IDS", "").split(",") if item}
if CASE_IDS:
    RECORDS = [record for record in RECORDS if record.get("case_id") in CASE_IDS]


@pytest.mark.skipif(not RECORDS, reason="Defina CONTRATOCLARO_RESULTS com um JSONL de execução real.")
@pytest.mark.parametrize("record", RECORDS, ids=lambda item: item.get("case_id", "caso"))
def test_contract_agent(record):
    """Avalia relevância, fidelidade e conformidade do caso selecionado."""
    if record.get("status") != "completed":
        pytest.fail(f"Caso não concluído: {record.get('error')}")
    checks = record.get("checks", {})
    for name, description in (
        ("required_tool", "a ferramenta exigida pelo caso não foi usada"),
        ("required_context", "nenhum contexto contratual exigido foi recuperado"),
    ):
        if checks.get(name) is False:
            pytest.fail(f"{record.get('case_id')}: {description}")
    judge = judge_from_environment()
    test_case = record_to_test_case(record)
    metrics = metrics_for(
        judge,
        faithfulness=bool(record.get("faithfulness_applicable") and record.get("retrieval_context")),
        relevancy=record.get("category") not in {"fora_de_escopo", "adversarial"},
    )
    # Cada métrica recebe apenas os campos necessários. Uma nota baixa não impede
    # o registro das demais; erros técnicos continuam interrompendo o caso.
    failures = []
    for metric in metrics:
        metric_case = (
            record_to_relevancy_test_case(record)
            if metric.__class__.__name__ == "AnswerRelevancyMetric"
            else test_case
        )
        try:
            assert_test(metric_case, [metric], run_async=False)
        except AssertionError as exc:
            failures.append(str(exc))
        finally:
            print(
                "DEEPEVAL_METRIC="
                + json.dumps(
                    {
                        "case_id": record.get("case_id"),
                        "metric": metric.__class__.__name__,
                        "score": getattr(metric, "score", None),
                        "threshold": metric.threshold,
                        "reason": getattr(metric, "reason", None),
                        "error": str(getattr(metric, "error", None) or ""),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )
    if failures:
        pytest.fail("; ".join(failures))

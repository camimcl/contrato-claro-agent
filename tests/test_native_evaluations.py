from contratoclaro.native_evaluations import DEFAULT_EVALUATORS, _parser, record_to_spans


def test_record_is_converted_to_generic_otel_agent_and_tool_spans():
    record = {
        "case_id": "case-1",
        "turns": [
            {
                "input": "Qual é o prazo?",
                "answer": "O prazo é 30 dias [E1].",
                "session_id": "session-1",
                "tool_calls": [{"name": "buscar_clausulas", "arguments": {"query": "prazo"}, "sources": []}],
            }
        ],
    }
    spans, trace_ids = record_to_spans(record)
    assert len(trace_ids) == 1
    assert len(trace_ids[0]) == 32
    assert len(spans) == 2
    assert spans[0]["attributes"]["gen_ai.task.input"] == "Qual é o prazo?"
    assert spans[0]["attributes"]["gen_ai.task.output"] == "O prazo é 30 dias [E1]."
    assert spans[0]["scope"]["name"].startswith("opentelemetry.instrumentation.")
    assert spans[1]["attributes"]["gen_ai.operation.name"] == "execute_tool"
    assert spans[1]["attributes"]["session.id"] == "session-1"


def test_cli_accepts_account_specific_custom_evaluator_id():
    args = _parser().parse_args(
        [
            "--input",
            "runs.jsonl",
            "--output",
            "evaluations.jsonl",
            "--evaluator-id",
            "custom-evaluator-id",
            "--confirm-paid-run",
        ]
    )

    assert args.evaluator_ids == ["custom-evaluator-id"]
    assert DEFAULT_EVALUATORS == ("Builtin.Faithfulness", "Builtin.Helpfulness")

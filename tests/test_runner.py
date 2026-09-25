import json

from contratoclaro.runner import execute_cases, load_cases


def test_runner_keeps_real_context_separate_from_reference(tmp_path):
    (tmp_path / "a.txt").write_text("Multa de 10%.", encoding="utf-8")
    case = {
        "id": "one",
        "category": "consulta_direta",
        "documents": ["a.txt"],
        "turns": ["Multa?"],
        "perspective": "contratante",
        "expected_output": "gabarito secreto",
        "expected_criteria": ["10%"],
        "reference_context": ["gabarito secreto"],
        "require_tool": True,
        "faithfulness_applicable": True,
    }

    class Agent:
        def ask(self, question):
            return {
                "answer": "Não encontrei",
                "retrieval_context": [],
                "tool_calls": [],
                "sources": [],
                "citations_valid": True,
                "usage": [],
                "session_id": "fresh",
            }

    result = next(execute_cases([case], tmp_path, lambda *args: Agent()))
    assert result["retrieval_context"] == []
    assert result["checks"]["required_tool"] is False
    assert result["checks"]["required_context"] is False
    assert result["expected_output"] == "gabarito secreto"


def test_dataset_counts_and_referenced_files():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cases = load_cases(root / "data/golden.json")
    assert len(cases) == 15
    assert len({c["id"] for c in cases}) == 15
    for case in cases:
        for filename in case["documents"]:
            assert (root / "data/contracts" / filename).is_file()

    attacks = load_cases(root / "data/red_team.json")
    assert len(attacks) == 15
    assert len({a["id"] for a in attacks}) == 15


def test_runner_logs_failure_without_claiming_pass(tmp_path):
    (tmp_path / "a.txt").write_text("Pagamento.")
    case = {"id": "bad", "documents": ["a.txt"], "turns": ["oi"]}

    class Broken:
        def ask(self, question):
            raise RuntimeError("timeout")

    result = next(execute_cases([case], tmp_path, lambda *args: Broken()))
    assert result["status"] == "error"
    assert result["outcome"] == "inconclusive"
    assert "timeout" in json.dumps(result)

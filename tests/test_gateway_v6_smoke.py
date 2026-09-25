import json

import pytest

from infra.smoke_gateway_v6 import load_cases, run_smoke, select_cases


def test_dataset_has_exactly_four_bounded_smoke_invocations():
    cases = load_cases()

    assert [item["id"] for item in cases] == ["v6-direct", "v6-compare", "v6-multiturn", "v6-adversarial"]
    sessions = {item["id"]: item["session"] for item in cases}
    assert sessions["v6-direct"] == sessions["v6-multiturn"] == "multiturn"


def test_selector_refuses_unknown_duplicate_or_more_than_four_cases():
    cases = load_cases()
    with pytest.raises(ValueError, match="desconhecido"):
        select_cases(cases, ["missing"])
    with pytest.raises(ValueError, match="repetidos"):
        select_cases(cases, ["v6-direct", "v6-direct"])
    with pytest.raises(ValueError, match="máximo de 4"):
        select_cases(
            cases + [{"id": "fifth", "session": "x", "prompt": "x"}],
            ["v6-direct", "v6-compare", "v6-multiturn", "v6-adversarial", "fifth"],
        )


def test_selector_requires_direct_turn_before_multiturn_followup():
    cases = load_cases()
    with pytest.raises(ValueError, match="v6-direct"):
        select_cases(cases, ["v6-multiturn"])
    with pytest.raises(ValueError, match="ordem"):
        select_cases(cases, ["v6-multiturn", "v6-direct"])


def test_runner_reuses_session_and_writes_private_jsonl(tmp_path):
    output_path = tmp_path / "smoke.jsonl"
    harness_arn = "arn:aws:bedrock-agentcore:us-east-2:123456789012:harness/test-1234567890"
    created = []

    class FakeAgent:
        def __init__(self, session_id):
            self.session_id = session_id

        def ask(self, prompt):
            return {
                "answer": "resposta segura",
                "usage": {"inputTokens": 1},
                "session_id": self.session_id,
                "backend": "harness-gateway",
            }

    def factory(harness_arn, session_id):
        created.append((harness_arn, session_id))
        return FakeAgent(session_id)

    records = run_smoke(
        "perfil-teste",
        harness_arn,
        ["v6-direct", "v6-compare", "v6-multiturn", "v6-adversarial"],
        output_path=output_path,
        agent_factory=factory,
    )

    assert len(records) == 4
    assert len(created) == 3  # one agent per session label is created lazily
    assert records[0]["session_id"] == records[2]["session_id"]
    saved = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [item["case_id"] for item in saved] == [
        "v6-direct",
        "v6-compare",
        "v6-multiturn",
        "v6-adversarial",
    ]
    with pytest.raises(FileExistsError):
        run_smoke("perfil-teste", harness_arn, ["v6-direct"], output_path=output_path, agent_factory=factory)

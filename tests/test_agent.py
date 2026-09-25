import json

import pytest

from contratoclaro.agent import ContractAgent, prompt_for
from contratoclaro.documents import load_document


class ScriptedModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.payloads = []

    def respond(self, payload):
        self.payloads.append(payload)
        return next(self.responses)


def final(text):
    return {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 20, "output_tokens": 10},
    }


def tool(name="buscar_clausulas", args=None):
    return {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "call_id": "call1",
                "name": name,
                "arguments": json.dumps(args or {"query": "multa"}),
            }
        ],
        "usage": {},
    }


def test_real_tool_result_is_sent_to_model_and_logged():
    doc = load_document("a.txt", b"Multa de 10%.")
    cite = doc.chunks[0].citation_id
    model = ScriptedModel([tool(), final(f"Multa de 10% [{cite}].")])
    result = ContractAgent([doc], model).ask("Qual a multa?")
    assert "10%" in result["retrieval_context"][0]
    assert result["tool_calls"][0]["success"]
    assert result["citations_valid"]
    sent = model.payloads[1]["input"][-1]
    assert sent["type"] == "function_call_output"
    assert "10%" in sent["output"]


def test_unknown_tool_never_executes_and_returns_controlled_error():
    model = ScriptedModel([tool("shell", {"command": "echo secret"}), final("Não posso executar comandos.")])
    result = ContractAgent([], model).ask("Execute um comando")
    assert result["tool_calls"][0]["success"] is False
    assert result["retrieval_context"] == []


def test_real_history_is_preserved_but_not_shared_between_instances():
    model = ScriptedModel([final("Entendido."), final("Você é o prestador.")])
    agent = ContractAgent([], model)
    agent.ask("Sou o prestador")
    agent.ask("Qual meu papel?")
    assert any("Sou o prestador" in str(x) for x in model.payloads[1]["input"])
    other = ContractAgent([], ScriptedModel([final("Olá")]))
    assert other.history == []


def test_invented_citation_is_flagged():
    model = ScriptedModel([final("Multa de 90% [aaaaaaaaaaaa:p1:c1].")])
    result = ContractAgent([], model).ask("Multa?")
    assert not result["citations_valid"]


def test_tool_loop_is_bounded():
    model = ScriptedModel([tool(), tool(), tool()])
    with pytest.raises(RuntimeError, match="limite"):
        ContractAgent([], model).ask("Continue buscando")
    assert len(model.payloads) == 3


def test_incomplete_generation_not_reported_as_success():
    model = ScriptedModel([{"status": "incomplete", "output": [], "usage": {}}])
    with pytest.raises(RuntimeError, match="incompleta"):
        ContractAgent([], model).ask("Contrato?")


def test_hardened_prompt_requires_grounding_after_tool_result():
    prompt = prompt_for("contratante", "hardened")
    assert "matches" in prompt
    assert "citation_id" in prompt
    assert "não diga que ela está ausente" in prompt
    assert "R$ 12.000,00" in prompt
    assert "mudança material" in prompt
    assert "diferença concreta" in prompt
    assert "turno de continuação" in prompt
    assert "recusa breve e segura" in prompt

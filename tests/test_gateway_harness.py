import pytest

from contratoclaro.gateway_harness import GatewayHarnessClient, parse_final_text

HARNESS_ARN = "arn:aws:bedrock-agentcore:us-east-2:123456789012:harness/ContratoClaroGatewayV6-1234567890"


def stream_for_text(text, stop_reason="end_turn"):
    return [
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": stop_reason}},
        {"metadata": {"usage": {"inputTokens": 12, "outputTokens": 8}}},
    ]


class FakeHarnessClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.requests = []

    def invoke_harness(self, **kwargs):
        self.requests.append(kwargs)
        return {"stream": self.streams.pop(0)}


def test_gateway_client_returns_final_text_without_inline_tool_roundtrip():
    client = FakeHarnessClient([stream_for_text("A multa é 10% [contrato_v1.md].")])
    agent = GatewayHarnessClient(HARNESS_ARN, client=client, session_id="session-1234567890")

    result = agent.ask("Qual é a multa do contrato v1?")

    assert result["answer"].startswith("A multa é 10%")
    assert result["backend"] == "harness-gateway"
    assert result["usage"] == {"inputTokens": 12, "outputTokens": 8}
    assert "tools" not in client.requests[0]
    assert "allowedTools" not in client.requests[0]
    assert client.requests[0]["messages"] == [
        {"role": "user", "content": [{"text": "Qual é a multa do contrato v1?"}]}
    ]


def test_gateway_client_reuses_session_and_sends_only_new_turn():
    client = FakeHarnessClient([stream_for_text("primeira"), stream_for_text("segunda")])
    agent = GatewayHarnessClient(HARNESS_ARN, client=client, session_id="session-1234567890")

    agent.ask("primeira pergunta")
    agent.ask("continuação")

    assert [item["runtimeSessionId"] for item in client.requests] == [
        "session-1234567890",
        "session-1234567890",
    ]
    assert client.requests[1]["messages"] == [{"role": "user", "content": [{"text": "continuação"}]}]


def test_parse_final_text_rejects_incomplete_or_failed_stream():
    with pytest.raises(RuntimeError, match="incompleta"):
        parse_final_text(stream_for_text("parcial", stop_reason="tool_use"))
    with pytest.raises(RuntimeError, match="Falha do Harness"):
        parse_final_text([{"validationException": {"message": "bad request"}}])


@pytest.mark.parametrize("question", ["", "   ", "x" * 4001, 123])
def test_gateway_client_rejects_invalid_question_before_remote_call(question):
    client = FakeHarnessClient([])
    agent = GatewayHarnessClient(HARNESS_ARN, client=client)

    with pytest.raises((TypeError, ValueError)):
        agent.ask(question)

    assert client.requests == []

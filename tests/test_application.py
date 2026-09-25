import pytest

from contratoclaro.agent import ContractAgent
from contratoclaro.application import AgentSettings, build_agent, load_uploads, session_key


class Client:
    def respond(self, payload):
        return {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
        }


def test_uploads_build_local_agent_and_stable_session_key():
    uploads = [("contrato.txt", b"Clausula 1. Pagamento em 10 dias.")]
    documents = load_uploads(uploads)
    settings = AgentSettings("contratante", "hardened", "local")

    first = session_key(uploads, settings)
    second = session_key(uploads, settings)
    agent = build_agent(documents, settings, model_client=Client())

    assert first == second
    assert isinstance(agent, ContractAgent)
    assert agent.documents[0].name == "contrato.txt"


def test_session_key_changes_with_document_or_security_variant():
    uploads = [("a.txt", b"texto")]
    a = session_key(uploads, AgentSettings("contratante", "baseline", "local"))
    b = session_key(uploads, AgentSettings("contratante", "hardened", "local"))
    c = session_key([("a.txt", b"outro")], AgentSettings("contratante", "baseline", "local"))
    assert len({a, b, c}) == 3


def test_harness_backend_requires_arn():
    documents = load_uploads([("a.txt", b"texto")])
    with pytest.raises(ValueError, match="ARN"):
        build_agent(documents, AgentSettings("contratante", "hardened", "harness"))

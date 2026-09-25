"""Cliente enxuto para um Harness cujas ferramentas rodam pelo Gateway."""

from __future__ import annotations

import os
import uuid

import boto3
from botocore.config import Config

from .provider import REGION

FAILURE_EVENTS = ("internalServerException", "validationException", "runtimeClientError")


def parse_final_text(stream) -> tuple[str, dict]:
    """Lê o fluxo do Harness e devolve a resposta final e o uso de tokens."""
    if stream is None:
        raise RuntimeError("O Harness não retornou fluxo de eventos.")
    text_parts = []
    usage = {}
    stop_reason = None
    for event in stream:
        failures = [key for key in FAILURE_EVENTS if key in event]
        if failures:
            detail = event[failures[0]].get("message", failures[0])
            raise RuntimeError(f"Falha do Harness: {detail}")
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if isinstance(delta.get("text"), str):
                text_parts.append(delta["text"])
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason")
        elif "metadata" in event:
            usage = event["metadata"].get("usage") or usage
    if stop_reason != "end_turn":
        raise RuntimeError(f"Resposta incompleta do Harness ({stop_reason or 'sem término'}).")
    answer = "".join(text_parts).strip()
    if not answer:
        raise RuntimeError("O Harness não retornou texto utilizável.")
    return answer, usage


class GatewayHarnessClient:
    """Mantém a sessão multi-turno do Harness com ferramenta remota."""

    def __init__(self, harness_arn, *, profile=None, region=None, client=None, session_id=None):
        """Valida o ARN e prepara um cliente AgentCore reutilizável."""
        if not isinstance(harness_arn, str) or not harness_arn.startswith("arn:"):
            raise ValueError("ARN do Harness v6 inválido.")
        self.harness_arn = harness_arn
        self.session_id = session_id or str(uuid.uuid4())
        self.actor_id = str(uuid.uuid4())
        self.turns = 0
        if client is None:
            session = boto3.Session(
                profile_name=profile or os.getenv("AWS_PROFILE", "default"),
                region_name=region or os.getenv("AWS_REGION", REGION),
            )
            client = session.client(
                "bedrock-agentcore",
                config=Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 2}),
            )
        self.client = client

    def ask(self, question):
        """Envia uma pergunta e devolve uma resposta pronta para registro."""
        if not isinstance(question, str):
            raise TypeError("A pergunta deve ser um texto.")
        if not question.strip() or len(question) > 4000:
            raise ValueError("Digite uma pergunta de até 4000 caracteres.")
        if self.turns >= 10:
            raise ValueError("Limite de 10 turnos por sessão; inicie outra conversa.")
        response = self.client.invoke_harness(
            harnessArn=self.harness_arn,
            runtimeSessionId=self.session_id,
            actorId=self.actor_id,
            messages=[{"role": "user", "content": [{"text": question.strip()}]}],
        )
        answer, usage = parse_final_text(response.get("stream"))
        self.turns += 1
        return {
            "answer": answer,
            "usage": usage,
            "session_id": self.session_id,
            "backend": "harness-gateway",
        }

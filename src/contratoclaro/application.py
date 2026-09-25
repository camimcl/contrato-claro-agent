"""Serviços compartilhados pela interface Streamlit e pela linha de comando."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .agent import ContractAgent
from .budget import BudgetLedger
from .documents import load_document
from .harness import HarnessAgent
from .provider import MantleClient


@dataclass(frozen=True)
class AgentSettings:
    """Reúne as escolhas necessárias para montar uma sessão do agente."""

    perspective: str = "contratante"
    variant: str = "hardened"
    backend: str = "local"
    harness_arn: str = ""

    def validate(self):
        """Recusa opções desconhecidas antes de criar clientes ou sessões."""
        if self.perspective not in {"contratante", "prestador"}:
            raise ValueError("Perspectiva inválida.")
        if self.variant not in {"baseline", "hardened"}:
            raise ValueError("Variante inválida.")
        if self.backend not in {"local", "harness"}:
            raise ValueError("Backend inválido.")


def load_uploads(uploads):
    """Converte de um a dois uploads em documentos internos."""
    uploads = list(uploads)
    if not 1 <= len(uploads) <= 2:
        raise ValueError("Envie um ou dois contratos.")
    return [load_document(name, data) for name, data in uploads]


def session_key(uploads, settings: AgentSettings) -> str:
    """Cria uma chave estável para reiniciar a conversa quando algo mudar."""
    settings.validate()
    digest = hashlib.sha256()
    digest.update(repr(settings).encode("utf-8"))
    for name, data in uploads:
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(data)
    return digest.hexdigest()


def build_agent(
    documents, settings: AgentSettings, *, model_client=None, harness_client=None, ledger=None, retriever=None
):
    """Monta o agente local ou o cliente do Harness conforme a configuração."""
    settings.validate()
    ledger = ledger or BudgetLedger()
    if settings.backend == "local":
        if retriever is not None:
            raise ValueError("A recuperação pela Knowledge Base requer o backend Harness.")
        client = model_client or MantleClient(ledger=ledger)
        return ContractAgent(documents, client, settings.perspective, settings.variant)
    if not settings.harness_arn.startswith("arn:"):
        raise ValueError("Informe o ARN válido do AgentCore Harness.")
    return HarnessAgent(
        documents,
        settings.harness_arn,
        settings.perspective,
        settings.variant,
        ledger=ledger,
        client=harness_client,
        retriever=retriever,
    )

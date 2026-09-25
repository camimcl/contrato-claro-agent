"""Recuperação na Knowledge Base para um corpus de demonstração com escopo explícito."""

from __future__ import annotations

import hashlib
import os
import re

import boto3

from .documents import Chunk, Document
from .provider import REGION

SCOPE_FIELD = "scope_id"
DOCUMENT_FIELD = "contract_id"


class KnowledgeBaseRetriever:
    """Recupera somente trechos do escopo e dos contratos selecionados.

    O filtro de metadados limita esta demonstração de usuário único, mas não substitui
    uma barreira de autorização para quem pode chamar ``bedrock:Retrieve`` diretamente.
    """

    def __init__(self, knowledge_base_id: str, scope_id: str, *, client=None):
        """Valida a configuração e prepara o cliente da Knowledge Base."""
        if not re.fullmatch(r"[A-Za-z0-9]{10}", knowledge_base_id or ""):
            raise ValueError("ID da Knowledge Base inválido.")
        if not re.fullmatch(r"[a-z0-9-]{3,64}", scope_id or ""):
            raise ValueError("Escopo da Knowledge Base inválido.")
        self.knowledge_base_id = knowledge_base_id
        self.scope_id = scope_id
        if client is None:
            session = boto3.Session(
                profile_name=os.getenv("AWS_PROFILE", "default"), region_name=os.getenv("AWS_REGION", REGION)
            )
            client = session.client("bedrock-agent-runtime")
        self.client = client

    def search(self, documents: list[Document], query: str, document_ids=None, top_k=4) -> list[Chunk]:
        """Busca trechos autorizados e preserva resultados de cada versão consultada."""
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise ValueError("Consulta deve conter de 1 a 1000 caracteres.")
        catalog = {doc.id: doc for doc in documents}
        if document_ids is not None:
            if not isinstance(document_ids, list) or any(not isinstance(x, str) for x in document_ids):
                raise ValueError("document_ids deve ser uma lista de identificadores.")
            if not set(document_ids) <= catalog.keys():
                raise ValueError("Documento não autorizado nesta sessão.")
        selected = set(document_ids or catalog.keys())
        if not selected:
            return []
        per_document = []
        for requested_id in sorted(selected):
            # Busca cada versão separadamente para não omitir um contrato na comparação.
            response = self.client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": max(1, min(top_k, 8)),
                        "filter": {
                            "andAll": [
                                {"equals": {"key": SCOPE_FIELD, "value": self.scope_id}},
                                {"equals": {"key": DOCUMENT_FIELD, "value": requested_id}},
                            ]
                        },
                    }
                },
            )
            hits = []
            for item in response.get("retrievalResults", []):
                metadata = item.get("metadata") or {}
                # Descarta resultados fora do escopo ou do contrato solicitado.
                if metadata.get(SCOPE_FIELD) != self.scope_id or metadata.get(DOCUMENT_FIELD) != requested_id:
                    continue
                body = (item.get("content") or {}).get("text")
                if not isinstance(body, str) or not body.strip():
                    continue
                source = catalog[requested_id]
                # O corpus inicial usa uma página lógica por arquivo Markdown.
                page = 1
                fingerprint = hashlib.sha256((requested_id + "\x00" + body).encode()).hexdigest()[:12]
                citation_id = f"{requested_id}:p{page}:c{int(fingerprint, 16)}"
                chunk = Chunk(requested_id, source.name, page, citation_id, body[:1300])
                hits.append((item.get("score", 0), chunk))
            per_document.append(hits)
        limit = max(1, min(top_k, 8))
        first = [hits[0][1] for hits in per_document if hits]
        remaining = sorted((hit for hits in per_document for hit in hits[1:]), key=lambda hit: -hit[0])
        return (first + [hit[1] for hit in remaining])[:limit]

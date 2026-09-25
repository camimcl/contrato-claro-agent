"""Lambda que recupera cláusulas autorizadas de uma Knowledge Base existente."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

KB_ID_PATTERN = re.compile(r"[A-Za-z0-9]{10}")
SCOPE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}")
DOCUMENT_ID_PATTERN = re.compile(r"[a-f0-9]{12}")
MAX_QUERY_LENGTH = 1000
MAX_DOCUMENTS = 3
MAX_RESULTS_PER_DOCUMENT = 5


@dataclass(frozen=True)
class RetrieverConfig:
    """Reúne os limites que isolam o corpus consultado pela Lambda."""

    knowledge_base_id: str
    scope_id: str
    allowed_document_ids: frozenset[str]


def _config_from_env(environment: dict[str, str]) -> RetrieverConfig:
    """Lê e valida a configuração fornecida por variáveis de ambiente."""
    knowledge_base_id = environment.get("KNOWLEDGE_BASE_ID", "")
    if not KB_ID_PATTERN.fullmatch(knowledge_base_id):
        raise RuntimeError("KNOWLEDGE_BASE_ID ausente ou inválido.")
    scope_id = environment.get("KB_SCOPE_ID", "")
    if not SCOPE_PATTERN.fullmatch(scope_id):
        raise RuntimeError("KB_SCOPE_ID ausente ou inválido.")
    try:
        raw_ids = json.loads(environment.get("ALLOWED_DOCUMENT_IDS", ""))
    except json.JSONDecodeError as exc:
        raise RuntimeError("ALLOWED_DOCUMENT_IDS deve ser uma lista JSON válida.") from exc
    if (
        not isinstance(raw_ids, list)
        or not raw_ids
        or len(raw_ids) > MAX_DOCUMENTS
        or any(not isinstance(item, str) or not DOCUMENT_ID_PATTERN.fullmatch(item) for item in raw_ids)
    ):
        raise RuntimeError("ALLOWED_DOCUMENT_IDS deve conter de 1 a 3 IDs válidos.")
    return RetrieverConfig(knowledge_base_id, scope_id, frozenset(raw_ids))


def _validate_event(event: dict, config: RetrieverConfig) -> tuple[str, list[str]]:
    """Valida a consulta e recusa documentos fora do catálogo permitido."""
    if not isinstance(event, dict):
        raise TypeError("A entrada da ferramenta deve ser um objeto JSON.")
    if set(event) - {"query", "document_ids"}:
        raise ValueError("A entrada contém campos não autorizados.")
    query = event.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query deve ser um texto não vazio.")
    query = query.strip()
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"query deve ter no máximo {MAX_QUERY_LENGTH} caracteres.")
    document_ids = event.get("document_ids")
    if not isinstance(document_ids, list) or not document_ids or len(document_ids) > MAX_DOCUMENTS:
        raise ValueError("document_ids deve conter de 1 a 3 IDs.")
    if any(not isinstance(item, str) for item in document_ids):
        raise ValueError("document_ids aceita somente textos.")
    unique_ids = list(dict.fromkeys(document_ids))
    unknown = [item for item in unique_ids if item not in config.allowed_document_ids]
    if unknown:
        raise ValueError("Documento não autorizado para este corpus.")
    return query, unique_ids


def _reference_from_result(result: dict) -> str:
    """Extrai um nome de arquivo seguro da localização S3 do resultado."""
    uri = result.get("location", {}).get("s3Location", {}).get("uri", "")
    path = urlparse(uri).path
    return PurePosixPath(path).name if path else "knowledge-base"


def _safe_results(response: dict, scope_id: str, document_id: str) -> list[dict]:
    """Mantém somente resultados válidos do escopo e contrato esperados."""
    safe = []
    for item in response.get("retrievalResults", []):
        metadata = item.get("metadata", {})
        text = item.get("content", {}).get("text")
        if (
            metadata.get("scope_id") != scope_id
            or metadata.get("contract_id") != document_id
            or not isinstance(text, str)
            or not text.strip()
        ):
            continue
        result = {
            "document_id": document_id,
            "reference": _reference_from_result(item),
            "text": text.strip(),
        }
        if isinstance(item.get("score"), (int, float)):
            result["score"] = item["score"]
        safe.append(result)
    return safe


def handle_request(event: dict, runtime_client, config: RetrieverConfig) -> dict:
    """Consulta cada contrato separadamente e reúne os trechos encontrados."""
    query, document_ids = _validate_event(event, config)
    results = []
    for document_id in document_ids:
        response = runtime_client.retrieve(
            knowledgeBaseId=config.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": MAX_RESULTS_PER_DOCUMENT,
                    "filter": {
                        "andAll": [
                            {"equals": {"key": "scope_id", "value": config.scope_id}},
                            {"equals": {"key": "contract_id", "value": document_id}},
                        ]
                    },
                }
            },
        )
        results.extend(_safe_results(response, config.scope_id, document_id))
    return {"results": results, "result_count": len(results)}


def _request_id(context) -> str:
    """Obtém o identificador AWS usado para correlacionar os logs."""
    return str(getattr(context, "aws_request_id", "unknown"))


def lambda_handler(event, context):
    """Atende a chamada do Gateway e devolve erros sem expor detalhes internos."""
    request_id = _request_id(context)
    try:
        config = _config_from_env(os.environ)
        runtime = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2"))
        response = handle_request(event, runtime, config)
        LOGGER.info(
            "KB retrieve succeeded request_id=%s result_count=%d", request_id, response["result_count"]
        )
        return response
    except (TypeError, ValueError) as exc:
        LOGGER.warning("KB retrieve rejected request_id=%s reason=invalid_input", request_id)
        return {"error": str(exc), "results": [], "result_count": 0}
    except (BotoCoreError, ClientError):
        LOGGER.exception("KB retrieve failed request_id=%s reason=aws_error", request_id)
        return {
            "error": "Falha temporária ao consultar a base de conhecimento.",
            "results": [],
            "result_count": 0,
        }
    except RuntimeError:
        LOGGER.exception("KB retrieve failed request_id=%s reason=invalid_configuration", request_id)
        return {"error": "Configuração interna da ferramenta inválida.", "results": [], "result_count": 0}

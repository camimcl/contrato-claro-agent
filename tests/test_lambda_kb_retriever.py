import json

import pytest
from botocore.exceptions import ClientError

from infra.lambda_kb_retriever import (
    RetrieverConfig,
    _config_from_env,
    handle_request,
    lambda_handler,
)

ALLOWED = frozenset({"e60f65792618", "1dcfdd549efd", "557082276e65"})
CONFIG = RetrieverConfig("ABCDEFGHIJ", "contratoclaro-demo-v1", ALLOWED)


class FakeRuntime:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.requests = []

    def retrieve(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return {"retrievalResults": self.results}


def test_returns_only_hits_matching_fixed_scope_and_requested_document():
    runtime = FakeRuntime(
        [
            {
                "metadata": {"scope_id": "contratoclaro-demo-v1", "contract_id": "1dcfdd549efd"},
                "content": {"text": "Multa de 10%."},
                "score": 0.91,
                "location": {"s3Location": {"uri": "s3://demo/contrato_v1.md"}},
            },
            {
                "metadata": {"scope_id": "outro", "contract_id": "1dcfdd549efd"},
                "content": {"text": "segredo"},
                "score": 1.0,
            },
            {
                "metadata": {"scope_id": "contratoclaro-demo-v1", "contract_id": "557082276e65"},
                "content": {"text": "outro contrato"},
                "score": 1.0,
            },
        ]
    )

    result = handle_request({"query": "qual a multa?", "document_ids": ["1dcfdd549efd"]}, runtime, CONFIG)

    assert result == {
        "results": [
            {
                "document_id": "1dcfdd549efd",
                "reference": "contrato_v1.md",
                "text": "Multa de 10%.",
                "score": 0.91,
            }
        ],
        "result_count": 1,
    }
    assert runtime.requests[0]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] == {
        "andAll": [
            {"equals": {"key": "scope_id", "value": "contratoclaro-demo-v1"}},
            {"equals": {"key": "contract_id", "value": "1dcfdd549efd"}},
        ]
    }


@pytest.mark.parametrize(
    "event",
    [
        None,
        {},
        {"query": "", "document_ids": ["1dcfdd549efd"]},
        {"query": 123, "document_ids": ["1dcfdd549efd"]},
        {"query": "multa", "document_ids": []},
        {"query": "multa", "document_ids": "1dcfdd549efd"},
        {"query": "multa", "document_ids": ["fora-do-catalogo"]},
        {"query": "multa", "document_ids": ["1dcfdd549efd"], "scope_id": "outro"},
        {"query": "x" * 1001, "document_ids": ["1dcfdd549efd"]},
    ],
)
def test_rejects_invalid_event_before_remote_call(event):
    runtime = FakeRuntime()

    with pytest.raises((TypeError, ValueError)):
        handle_request(event, runtime, CONFIG)

    assert runtime.requests == []


def test_deduplicates_document_ids_before_retrieve():
    runtime = FakeRuntime()

    result = handle_request(
        {"query": "multa", "document_ids": ["1dcfdd549efd", "1dcfdd549efd"]}, runtime, CONFIG
    )

    assert result == {"results": [], "result_count": 0}
    assert len(runtime.requests) == 1


def test_configuration_requires_valid_kb_scope_and_catalog():
    with pytest.raises(RuntimeError, match="KNOWLEDGE_BASE_ID"):
        _config_from_env(
            {
                "KNOWLEDGE_BASE_ID": "inválido",
                "KB_SCOPE_ID": "scope",
                "ALLOWED_DOCUMENT_IDS": json.dumps(sorted(ALLOWED)),
            }
        )
    with pytest.raises(RuntimeError, match="KB_SCOPE_ID"):
        _config_from_env(
            {
                "KNOWLEDGE_BASE_ID": "ABCDEFGHIJ",
                "KB_SCOPE_ID": "",
                "ALLOWED_DOCUMENT_IDS": json.dumps(sorted(ALLOWED)),
            }
        )
    with pytest.raises(RuntimeError, match="ALLOWED_DOCUMENT_IDS"):
        _config_from_env(
            {"KNOWLEDGE_BASE_ID": "ABCDEFGHIJ", "KB_SCOPE_ID": "scope", "ALLOWED_DOCUMENT_IDS": "[]"}
        )


def test_lambda_handler_returns_safe_error_for_invalid_input(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "ABCDEFGHIJ")
    monkeypatch.setenv("KB_SCOPE_ID", "contratoclaro-demo-v1")
    monkeypatch.setenv("ALLOWED_DOCUMENT_IDS", json.dumps(sorted(ALLOWED)))

    response = lambda_handler({"query": "multa", "document_ids": ["fora-do-catalogo"]}, None)

    assert response["results"] == []
    assert response["result_count"] == 0
    assert "não autorizado" in response["error"]


def test_lambda_handler_hides_aws_error_details(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "ABCDEFGHIJ")
    monkeypatch.setenv("KB_SCOPE_ID", "contratoclaro-demo-v1")
    monkeypatch.setenv("ALLOWED_DOCUMENT_IDS", json.dumps(sorted(ALLOWED)))
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "sensitive-detail"}}, "Retrieve"
    )
    monkeypatch.setattr(
        "infra.lambda_kb_retriever.boto3.client", lambda *args, **kwargs: FakeRuntime(error=error)
    )

    response = lambda_handler(
        {"query": "multa", "document_ids": ["1dcfdd549efd"]},
        type("Context", (), {"aws_request_id": "request-123"})(),
    )

    assert response == {
        "error": "Falha temporária ao consultar a base de conhecimento.",
        "results": [],
        "result_count": 0,
    }
    assert "sensitive-detail" not in json.dumps(response)

import pytest

from contratoclaro.agent import execute_tool
from contratoclaro.documents import load_document
from contratoclaro.kb import KnowledgeBaseRetriever

DEMO_SCOPE = "contratoclaro-demo-v1"


class FakeRuntime:
    def __init__(self, results):
        self.results = results
        self.requests = []

    def retrieve(self, **request):
        self.requests.append(request)
        return {"retrievalResults": self.results}


def test_kb_retrieval_filters_by_scope_and_contract_then_rejects_unexpected_hits():
    one = load_document("um.md", b"Multa de 10 por cento.")
    two = load_document("dois.md", b"Multa de 20 por cento.")
    runtime = FakeRuntime(
        [
            {
                "metadata": {"scope_id": DEMO_SCOPE, "contract_id": one.id},
                "content": {"text": "Multa de 10 por cento."},
            },
            {
                "metadata": {"scope_id": "other", "contract_id": one.id},
                "content": {"text": "Segredo de outra sessao."},
            },
            {
                "metadata": {"scope_id": DEMO_SCOPE, "contract_id": two.id},
                "content": {"text": "Multa de 20 por cento."},
            },
        ]
    )
    retriever = KnowledgeBaseRetriever("ABCDEFGHIJ", DEMO_SCOPE, client=runtime)

    hits = execute_tool(
        [one, two], "buscar_clausulas", {"query": "qual multa?", "document_ids": [one.id]}, retriever
    )

    assert len(hits) == 1
    assert hits[0].document_id == one.id
    assert hits[0].citation_id.startswith(one.id + ":p1:c")
    filt = runtime.requests[0]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]
    assert filt == {
        "andAll": [
            {"equals": {"key": "scope_id", "value": DEMO_SCOPE}},
            {"equals": {"key": "contract_id", "value": one.id}},
        ]
    }


def test_kb_rejects_document_outside_catalog_before_remote_call():
    one = load_document("um.md", b"Multa de 10 por cento.")
    runtime = FakeRuntime([])
    retriever = KnowledgeBaseRetriever("ABCDEFGHIJ", DEMO_SCOPE, client=runtime)

    with pytest.raises(ValueError, match="não autorizado"):
        execute_tool([one], "buscar_clausulas", {"query": "multa", "document_ids": ["other"]}, retriever)
    assert runtime.requests == []


def test_kb_comparison_retrieves_from_each_selected_contract():
    one = load_document("um.md", b"Multa de 10 por cento.")
    two = load_document("dois.md", b"Multa de 20 por cento.")
    runtime = FakeRuntime(
        [
            {
                "metadata": {"scope_id": DEMO_SCOPE, "contract_id": one.id},
                "content": {"text": "Multa de 10 por cento."},
                "score": 0.9,
            },
            {
                "metadata": {"scope_id": DEMO_SCOPE, "contract_id": two.id},
                "content": {"text": "Multa de 20 por cento."},
                "score": 0.8,
            },
        ]
    )
    retriever = KnowledgeBaseRetriever("ABCDEFGHIJ", DEMO_SCOPE, client=runtime)

    hits = retriever.search([one, two], "compare as multas")

    assert {hit.document_id for hit in hits} == {one.id, two.id}
    assert len(runtime.requests) == 2
    filters = [
        request["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]
        for request in runtime.requests
    ]
    assert {f["andAll"][1]["equals"]["value"] for f in filters} == {one.id, two.id}

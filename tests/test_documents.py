import io

import pytest
from pypdf import PdfWriter

from contratoclaro.documents import load_document, search


def test_search_preserves_source_and_finds_penalty():
    doc = load_document(
        "servico.txt",
        "CLÁUSULA 1 - OBJETO\nCriação de site.\n\nCLÁUSULA 2 - MULTA\nMulta de 10% por rescisão.".encode(),
    )
    hits = search([doc], "multa rescisao")
    assert hits and "10%" in hits[0].text
    assert hits[0].document_id == doc.id
    assert hits[0].page == 1
    assert hits[0].citation_id


def test_no_document_outside_session():
    own = load_document("own.txt", b"Pagamento de 100 reais.")
    other = load_document("other.txt", b"SEGREDO OUTRA SESSAO")
    with pytest.raises(ValueError, match="sessão"):
        search([own], "segredo", [other.id])


def test_versions_have_distinct_ids_and_both_retrieved():
    first = load_document("v1.txt", b"Multa de 10%.")
    second = load_document("v2.txt", b"Multa de 20%.")
    hits = search([first, second], "comparar multa")
    assert {h.document_id for h in hits} == {first.id, second.id}


def test_reject_empty_or_unsupported_upload():
    with pytest.raises(ValueError):
        load_document("empty.txt", b"   ")
    with pytest.raises(ValueError):
        load_document("attack.exe", b"code")


def test_scanned_pdf_requires_ocr_instead_of_silent_empty_answer():
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError, match="texto"):
        load_document("scan.pdf", output.getvalue())


def test_unrelated_query_does_not_invent_hit():
    doc = load_document("a.txt", b"Pagamento mensal em reais.")
    assert search([doc], "astronomia saturno") == []

"""Leitura e busca lexical apenas sobre os arquivos fornecidos pelo usuário."""

from __future__ import annotations

import hashlib
import io
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import PurePath

from pypdf import PdfReader

MAX_BYTES = 2_000_000
MAX_PAGES = 25
MAX_CHARS = 60_000
STOP = {
    "a",
    "o",
    "os",
    "as",
    "um",
    "uma",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "para",
    "por",
    "com",
    "que",
    "qual",
    "quais",
    "ao",
    "se",
}


@dataclass(frozen=True)
class Chunk:
    """Representa um trecho citável de um documento."""

    document_id: str
    document_name: str
    page: int
    citation_id: str
    text: str

    def to_dict(self):
        """Converte o trecho em um dicionário serializável."""
        return asdict(self)


@dataclass(frozen=True)
class Document:
    """Agrupa a identidade, o nome e os trechos de um contrato."""

    id: str
    name: str
    chunks: tuple[Chunk, ...]


def tokens(text: str) -> list[str]:
    """Normaliza o texto e devolve os termos úteis para a busca."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in normalized if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", plain) if w not in STOP]


def load_document(name: str, data: bytes) -> Document:
    """Valida um arquivo, extrai seu texto e cria trechos citáveis."""
    name = PurePath(name.replace("\\", "/")).name
    suffix = PurePath(name).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise ValueError("Envie PDF com texto, TXT ou Markdown.")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("O arquivo deve ter conteúdo e no máximo 2 MB.")
    if suffix == ".pdf":
        try:
            pdf = PdfReader(io.BytesIO(data))
            if pdf.is_encrypted:
                raise ValueError("PDF protegido: envie uma cópia sem senha.")
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError("Limite de 25 páginas por contrato.")
            pages = [p.extract_text() or "" for p in pdf.pages]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Não foi possível ler esse PDF.") from exc
        if any(not p.strip() for p in pages):
            raise ValueError("PDF contém página sem texto extraível; aplique OCR antes do envio.")
    else:
        try:
            pages = [data.decode("utf-8-sig")]
        except UnicodeDecodeError as exc:
            raise ValueError("Salve o arquivo de texto em UTF-8.") from exc
    if not "".join(pages).strip():
        raise ValueError("Documento sem texto.")
    if sum(map(len, pages)) > MAX_CHARS:
        raise ValueError("Limite de 60.000 caracteres por documento.")
    doc_id = hashlib.sha256(name.encode() + b"\x00" + data).hexdigest()[:12]
    chunks = []
    for page_no, page in enumerate(pages, 1):
        # Mantém os limites das cláusulas e divide apenas trechos muito longos.
        parts = re.split(r"(?im)(?=^\s*(?:#{1,4}\s*)?cl[áa]usula\s+\d+)", page)
        for part in parts:
            part = part.strip()
            for offset in range(0, len(part), 1100):
                excerpt = part[offset : offset + 1300]
                if excerpt.strip():
                    cite = f"{doc_id}:p{page_no}:c{len(chunks) + 1}"
                    chunks.append(Chunk(doc_id, name, page_no, cite, excerpt))
    return Document(doc_id, name, tuple(chunks))


def search(documents: list[Document], query: str, document_ids=None, top_k=4) -> list[Chunk]:
    """Busca os trechos mais próximos da consulta dentro do catálogo autorizado."""
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("Consulta deve conter de 1 a 1000 caracteres.")
    known = {d.id for d in documents}
    if document_ids is not None:
        if not isinstance(document_ids, list) or any(not isinstance(x, str) for x in document_ids):
            raise ValueError("document_ids deve ser uma lista de identificadores.")
        if not set(document_ids) <= known:
            raise ValueError("Documento não autorizado nesta sessão.")
    selected = [d for d in documents if not document_ids or d.id in document_ids]
    chunks = [c for d in selected for c in d.chunks]
    terms = set(tokens(query))
    if not chunks or not terms:
        return []
    bags = [Counter(tokens(c.text)) for c in chunks]
    idf = {t: math.log(1 + len(chunks) / (1 + sum(t in bag for bag in bags))) for t in terms}
    scored = []
    for chunk, bag in zip(chunks, bags):
        score = sum(idf[t] * bag[t] / (bag[t] + 1) for t in terms if bag[t])
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].citation_id))
    # Inclui primeiro o melhor trecho de cada versão para evitar comparações incompletas.
    result, seen = [], set()
    for _, chunk in scored:
        if chunk.document_id not in seen:
            result.append(chunk)
            seen.add(chunk.document_id)
    for _, chunk in scored:
        if chunk not in result:
            result.append(chunk)
    return result[: max(1, min(top_k, 8))]

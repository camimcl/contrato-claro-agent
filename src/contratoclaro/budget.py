"""Controle local e conservador de custos; não substitui o Billing da AWS."""

import math
import sqlite3
import uuid
from pathlib import Path

INPUT_USD_PER_MILLION = 0.14
OUTPUT_USD_PER_MILLION = 0.40


class BudgetExceeded(RuntimeError):
    """Indica que a próxima chamada ultrapassaria o limite local."""


def token_cost(input_tokens, output_tokens):
    """Estima o custo de uma chamada a partir do uso de tokens."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Contagem de tokens inválida.")
    return (input_tokens * INPUT_USD_PER_MILLION + output_tokens * OUTPUT_USD_PER_MILLION) / 1_000_000


class BudgetLedger:
    """Registra reservas e custos concluídos em um arquivo SQLite local."""

    def __init__(self, path="artifacts/costs.sqlite", limit_usd=1.0):
        """Prepara o arquivo de controle e valida o limite informado."""
        if not math.isfinite(limit_usd) or limit_usd <= 0:
            raise ValueError("Limite de custo inválido.")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limit = limit_usd
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, label TEXT, usd REAL, "
                "status TEXT, input_tokens INTEGER, output_tokens INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    def _connect(self):
        """Abre uma conexão curta com o banco de custos."""
        return sqlite3.connect(self.path, timeout=20)

    @property
    def total_usd(self):
        """Retorna o custo local acumulado, incluindo reservas abertas."""
        with self._connect() as db:
            return db.execute("SELECT COALESCE(SUM(usd),0) FROM calls").fetchone()[0]

    def reserve(self, usd, label):
        """Reserva um valor antes da chamada e devolve seu identificador."""
        if not math.isfinite(usd) or usd < 0:
            raise ValueError("Reserva de custo inválida.")
        key = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(usd),0) FROM calls").fetchone()[0]
            if spent + usd > self.limit:
                raise BudgetExceeded(
                    "Limite local de inferência atingido; revise o consumo antes de continuar."
                )
            db.execute(
                "INSERT INTO calls(id,label,usd,status) VALUES(?,?,?,?)", (key, label, usd, "reserved")
            )
        return key

    def settle(self, key, input_tokens, output_tokens, extra_usd=0):
        """Substitui a estimativa pelo custo calculado após a resposta."""
        cost = token_cost(input_tokens, output_tokens) + extra_usd
        with self._connect() as db:
            cur = db.execute(
                "UPDATE calls SET usd=?,status='complete',input_tokens=?,output_tokens=? "
                "WHERE id=? AND status='reserved'",
                (cost, input_tokens, output_tokens, key),
            )
            if cur.rowcount != 1:
                raise ValueError("Reserva inexistente ou já concluída.")

    def cancel(self, key):
        """Libera a reserva quando a chamada falha antes de informar o uso."""
        with self._connect() as db:
            cur = db.execute(
                "UPDATE calls SET usd=0,status='cancelled' WHERE id=? AND status='reserved'", (key,)
            )
            if cur.rowcount != 1:
                raise ValueError("Reserva inexistente ou já concluída.")

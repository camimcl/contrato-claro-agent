"""Linha de comando para executar datasets com custo explicitamente autorizado."""

from __future__ import annotations

import argparse
from pathlib import Path

from .application import AgentSettings, build_agent
from .budget import BudgetLedger
from .kb import KnowledgeBaseRetriever
from .runner import execute_cases, load_cases, write_jsonl


def _parser():
    """Define os argumentos aceitos pela linha de comando."""
    parser = argparse.ArgumentParser(prog="contratoclaro")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-dataset", help="Executa casos reais e grava JSONL auditável")
    run.add_argument("--dataset", type=Path, default=Path("data/golden.json"))
    run.add_argument("--contracts", type=Path, default=Path("data/contracts"))
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--variant", choices=["baseline", "hardened"], default="baseline")
    run.add_argument("--backend", choices=["local", "harness"], default="local")
    run.add_argument("--harness-arn", default="")
    run.add_argument("--kb-id", default="", help="Ativa Retrieve na Knowledge Base para a ferramenta")
    run.add_argument("--kb-scope", default="contratoclaro-demo-v1")
    run.add_argument("--max-cases", type=int)
    run.add_argument("--case-id", help="Executa somente o caso com este ID")
    run.add_argument("--max-usd", type=float, default=1.0)
    run.add_argument(
        "--ledger-path",
        type=Path,
        default=Path("artifacts/costs.sqlite"),
        help="Arquivo SQLite usado para aplicar o limite de custo deste lote",
    )
    run.add_argument(
        "--confirm-paid-run", action="store_true", help="Confirma que esta execução pode gerar cobrança AWS"
    )
    return parser


def main(argv=None):
    """Valida os parâmetros e executa o lote solicitado."""
    args = _parser().parse_args(argv)
    if args.command == "run-dataset":
        if not args.confirm_paid_run:
            raise SystemExit(
                "Execução não iniciada: use --confirm-paid-run depois de revisar casos e limite."
            )
        cases = load_cases(args.dataset)
        if args.case_id:
            cases = [case for case in cases if case["id"] == args.case_id]
            if not cases:
                raise SystemExit(f"Caso não encontrado: {args.case_id}")
        if args.max_cases is not None:
            if args.max_cases < 1:
                raise SystemExit("--max-cases deve ser positivo.")
            cases = cases[: args.max_cases]
        ledger = BudgetLedger(path=args.ledger_path, limit_usd=args.max_usd)
        if args.kb_id and args.backend != "harness":
            raise SystemExit("--kb-id requer --backend harness.")
        retriever = KnowledgeBaseRetriever(args.kb_id, args.kb_scope) if args.kb_id else None

        def factory(documents, perspective, variant):
            """Cria uma sessão independente para cada caso do dataset."""
            settings = AgentSettings(perspective, variant, args.backend, args.harness_arn)
            return build_agent(documents, settings, ledger=ledger, retriever=retriever)

        count = write_jsonl(execute_cases(cases, args.contracts, factory, variant=args.variant), args.output)
        print(
            f"{count} caso(s) registrados em {args.output}. Custo local acumulado: US${ledger.total_usd:.6f}"
        )


if __name__ == "__main__":
    main()

"""Executa até quatro perguntas fixas no Harness isolado com Gateway."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contratoclaro.gateway_harness import GatewayHarnessClient
from contratoclaro.provider import REGION

DATA_PATH = ROOT / "data" / "gateway_v6_smoke.json"
OUTPUT_PATH = ROOT / "artifacts" / "gateway-v6-smoke.jsonl"
MAX_INVOCATIONS = 4


def load_cases(path=DATA_PATH):
    """Carrega e valida o pequeno conjunto de casos de fumaça."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset de smoke vazio ou inválido.")
    required = {"id", "session", "prompt"}
    if any(not isinstance(item, dict) or set(item) != required for item in cases):
        raise ValueError("Cada caso deve conter somente id, session e prompt.")
    if len({item["id"] for item in cases}) != len(cases):
        raise ValueError("Dataset de smoke contém IDs repetidos.")
    return cases


def select_cases(cases, case_ids):
    """Seleciona casos válidos e preserva a ordem do diálogo multi-turno."""
    if len(case_ids) > MAX_INVOCATIONS:
        raise ValueError("O smoke aceita no máximo de 4 invocações por execução.")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("IDs repetidos não são permitidos.")
    by_id = {item["id"]: item for item in cases}
    unknown = [case_id for case_id in case_ids if case_id not in by_id]
    if unknown:
        raise ValueError(f"Caso desconhecido: {unknown[0]}")
    if "v6-multiturn" in case_ids:
        if "v6-direct" not in case_ids:
            raise ValueError("v6-multiturn exige v6-direct na mesma execução.")
        if case_ids.index("v6-direct") > case_ids.index("v6-multiturn"):
            raise ValueError("v6-direct deve aparecer antes de v6-multiturn na ordem de execução.")
    return [by_id[case_id] for case_id in case_ids]


def _default_factory(profile):
    """Cria clientes do Harness usando o perfil AWS informado."""
    session = boto3.Session(profile_name=profile, region_name=REGION)
    client = session.client(
        "bedrock-agentcore",
        config=Config(connect_timeout=10, read_timeout=180, retries={"total_max_attempts": 2}),
    )
    return lambda arn, session_id: GatewayHarnessClient(arn, client=client, session_id=session_id)


def run_smoke(profile, harness_arn, case_ids, *, output_path=OUTPUT_PATH, agent_factory=None):
    """Executa os casos escolhidos e registra cada resultado em JSONL."""
    if not isinstance(harness_arn, str) or not harness_arn.startswith("arn:"):
        raise ValueError("Informe um ARN válido do Harness v6.")
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Evidência já existe: {output_path}")
    selected = select_cases(load_cases(), case_ids)
    agent_factory = agent_factory or _default_factory(profile)
    agents = {}
    records = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as output:
        for case in selected:
            session_label = case["session"]
            if session_label not in agents:
                agents[session_label] = agent_factory(harness_arn, str(uuid.uuid4()))
            started = time.perf_counter()
            record = {
                "case_id": case["id"],
                "session": session_label,
                "prompt": case["prompt"],
                "timestamp": datetime.now(UTC).isoformat(),
            }
            try:
                result = agents[session_label].ask(case["prompt"])
                record.update(
                    {
                        "answer": result["answer"],
                        "usage": result.get("usage", {}),
                        "session_id": result["session_id"],
                        "backend": result["backend"],
                        "error": None,
                    }
                )
            except (BotoCoreError, ClientError, RuntimeError, TypeError, ValueError) as exc:
                record.update(
                    {
                        "answer": None,
                        "usage": {},
                        "session_id": agents[session_label].session_id,
                        "backend": "harness-gateway",
                        "error": str(exc),
                    }
                )
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            records.append(record)
    print(f"{len(records)} smoke(s) registrados em {output_path}.")
    return records


def main(argv=None):
    """Lê os argumentos da linha de comando e inicia o teste de fumaça."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--harness-arn", required=True)
    parser.add_argument("--case-ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    run_smoke(args.profile, args.harness_arn, args.case_ids, output_path=args.output)


if __name__ == "__main__":
    main()

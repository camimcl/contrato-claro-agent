"""Cliente Bedrock Mantle com assinatura SigV4, limites e repetição controlada."""

import json
import os
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from .budget import BudgetLedger, token_cost

MODEL_ID = "google.gemma-4-31b"
REGION = "us-east-2"


class MantleClient:
    """Envia requisições no formato Responses ao modelo configurado."""

    def __init__(self, ledger=None, profile=None, region=None, model_id=None):
        """Prepara sessão AWS, modelo e controle local de custo."""
        self.region = region or os.getenv("AWS_REGION", REGION)
        self.session = boto3.Session(
            profile_name=profile or os.getenv("AWS_PROFILE", "default"), region_name=self.region
        )
        self.ledger = ledger or BudgetLedger(limit_usd=float(os.getenv("CONTRATOCLARO_MAX_USD", "1")))
        self.model_id = model_id or os.getenv("CONTRATOCLARO_MODEL_ID", MODEL_ID)

    def respond(self, payload):
        """Assina e envia uma requisição, validando tamanho, custo e resposta."""
        body = {**payload, "model": self.model_id, "store": False}
        output_limit = body.setdefault("max_output_tokens", 1024)
        if not isinstance(output_limit, int) or not 1 <= output_limit <= 2048:
            raise ValueError("Limite de saída deve estar entre 1 e 2048 tokens.")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(data) > 60_000:
            raise ValueError("Contexto muito longo. Inicie outra conversa ou use contratos menores.")
        # A margem de 2048 bytes cobre o enquadramento normal da requisição.
        # É apenas uma estimativa local; o Billing da AWS continua sendo a referência.
        estimated = token_cost(len(data) + 2048, output_limit)
        if estimated > 0.02:
            raise ValueError("Estimativa por chamada excede US$0,02.")
        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("Faça login com aws login --profile default.")
        url = f"https://bedrock-mantle.{self.region}.api.aws/openai/v1/responses"
        req = AWSRequest(method="POST", url=url, data=data, headers={"Content-Type": "application/json"})
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-mantle", self.region).add_auth(req)
        reservation = self.ledger.reserve(estimated, "mantle:" + self.model_id)
        # Um timeout de conexão acontece antes do envio e permite uma repetição segura.
        # Timeout de leitura não é repetido, pois o provedor pode já ter processado a chamada.
        for attempt in range(2):
            try:
                response = requests.post(url, data=data, headers=dict(req.headers), timeout=(25, 90))
                break
            except requests.exceptions.ConnectTimeout:
                if attempt:
                    raise
                time.sleep(1)
        if not response.ok:
            raise RuntimeError(
                f"Bedrock retornou HTTP {response.status_code}. Revise login, permissões e logs locais."
            )
        result = response.json()
        usage = result.get("usage")
        if usage and "input_tokens" in usage and "output_tokens" in usage:
            self.ledger.settle(reservation, usage["input_tokens"], usage["output_tokens"])
        return result

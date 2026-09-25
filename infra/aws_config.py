"""Definições declarativas de recursos AWS para revisão e testes locais."""

from __future__ import annotations

from contratoclaro.agent import TOOL_DESCRIPTION, TOOL_SCHEMA, prompt_for
from contratoclaro.provider import MODEL_ID

PROJECT_TAGS = {"project": "contratoclaro", "environment": "educational"}
HARNESS_NAME = "ContratoClaro"
HARNESS_ROLE = "ContratoClaroHarnessRole"
LAMBDA_NAME = "ContratoClaroConformidade"
LAMBDA_ROLE = "ContratoClaroEvaluatorLambdaRole"
EVALUATOR_NAME = "ContratoClaroConformidade"


def agentcore_trust_policy():
    """Define quais serviços podem assumir o papel usado pelo AgentCore."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def lambda_trust_policy():
    """Define a relação de confiança necessária para uma função Lambda."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def harness_policy(account_id: str, region: str):
    """Monta as permissões mínimas usadas pelo Harness nesta demonstração."""
    runtime_logs = f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    agentcore = f"arn:aws:bedrock-agentcore:{region}:{account_id}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockModelInvocation",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{region}:{account_id}:*",
                ],
            },
            {
                "Sid": "BedrockMantleInference",
                "Effect": "Allow",
                "Action": "bedrock-mantle:CreateInference",
                "Resource": f"arn:aws:bedrock-mantle:{region}:{account_id}:project/default",
            },
            {
                "Sid": "BedrockMantleBearerToken",
                "Effect": "Allow",
                "Action": "bedrock-mantle:CallWithBearerToken",
                "Resource": "*",
                "Condition": {"StringEquals": {"bedrock-mantle:BearerTokenType": "SHORT_TERM"}},
            },
            {
                "Sid": "ManagedImage",
                "Effect": "Allow",
                "Action": ["ecr-public:GetAuthorizationToken", "sts:GetServiceBearerToken"],
                "Resource": "*",
            },
            {
                "Sid": "Tracing",
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": "*",
            },
            {
                "Sid": "LogGroups",
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams"],
                "Resource": runtime_logs,
            },
            {
                "Sid": "DescribeLogGroups",
                "Effect": "Allow",
                "Action": "logs:DescribeLogGroups",
                "Resource": f"arn:aws:logs:{region}:{account_id}:log-group:*",
            },
            {
                "Sid": "LogStreams",
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": runtime_logs + ":log-stream:*",
            },
            {
                "Sid": "LogResourcePolicy",
                "Effect": "Allow",
                "Action": "logs:PutResourcePolicy",
                "Resource": "*",
            },
            {
                "Sid": "Metrics",
                "Effect": "Allow",
                "Action": "cloudwatch:PutMetricData",
                "Resource": "*",
                "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            },
            {
                "Sid": "WorkloadIdentity",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                ],
                "Resource": [
                    f"{agentcore}:workload-identity-directory/default",
                    f"{agentcore}:workload-identity-directory/default/workload-identity/harness_*",
                ],
            },
            {
                "Sid": "ManagedMemory",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:DeleteEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                ],
                "Resource": f"{agentcore}:memory/*",
            },
        ],
    }


def lambda_execution_policy(account_id: str, region: str):
    """Monta as permissões de logs para o avaliador executado em Lambda."""
    logs = f"arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/{LAMBDA_NAME}:*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": logs,
            }
        ],
    }


def harness_request(role_arn: str):
    """Produz a configuração revisável de um Harness compatível com o agente."""
    return {
        "harnessName": HARNESS_NAME,
        "executionRoleArn": role_arn,
        "environment": {"agentCoreRuntimeEnvironment": {"networkConfiguration": {"networkMode": "PUBLIC"}}},
        "model": {"bedrockModelConfig": {"modelId": MODEL_ID, "apiFormat": "responses", "maxTokens": 1024}},
        "systemPrompt": [{"text": prompt_for("contratante", "hardened")}],
        "tools": [
            {
                "type": "inline_function",
                "name": "buscar_clausulas",
                "config": {"inlineFunction": {"description": TOOL_DESCRIPTION, "inputSchema": TOOL_SCHEMA}},
            }
        ],
        "allowedTools": ["@buscar_clausulas"],
        "memory": {"managedMemoryConfiguration": {"strategies": ["SUMMARIZATION"], "eventExpiryDuration": 3}},
        "truncation": {"strategy": "sliding_window", "config": {"slidingWindow": {"messagesCount": 10}}},
        "maxIterations": 3,
        "maxTokens": 1024,
        "timeoutSeconds": 120,
        "tags": PROJECT_TAGS,
    }


def evaluator_request(lambda_arn: str):
    """Produz a configuração do avaliador determinístico personalizado."""
    return {
        "evaluatorName": EVALUATOR_NAME,
        "description": "Valida citações e possível vazamento de instruções ou credenciais.",
        "level": "TRACE",
        "evaluatorConfig": {
            "codeBased": {"lambdaConfig": {"lambdaArn": lambda_arn, "lambdaTimeoutInSeconds": 30}}
        },
        "tags": PROJECT_TAGS,
    }

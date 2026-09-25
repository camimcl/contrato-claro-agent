import json

from botocore.session import Session
from botocore.validate import validate_parameters

from infra.gateway_v6_config import (
    GATEWAY_NAME,
    GATEWAY_TOOL_NAME,
    HARNESS_V6_NAME,
    KB_LAMBDA_NAME,
    TARGET_NAME,
    V6_CATALOG,
    gateway_policy,
    gateway_request,
    gateway_target_request,
    gateway_trust_policy,
    harness_v6_policy,
    harness_v6_request,
    harness_v6_update_request,
    kb_lambda_policy,
)

ACCOUNT_ID = "123456789012"
REGION = "us-east-2"
LAMBDA_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:ContratoClaroBuscarClausulasV6"
GATEWAY_ARN = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:gateway/contratoclaro-1234567890"
GATEWAY_ID = "contratoclaro-1234567890"
HARNESS_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/ContratoClaroHarnessV6Role"


def _input_shape(operation):
    service = Session().get_service_model("bedrock-agentcore-control")
    return service.operation_model(operation).input_shape


def test_v6_resource_names_are_explicit_and_separate():
    assert GATEWAY_NAME == "ContratoClaroGatewayV6"
    assert TARGET_NAME == "ContratoClaroKbLambdaV6Target"
    assert KB_LAMBDA_NAME == "ContratoClaroBuscarClausulasV6"
    assert HARNESS_V6_NAME == "ContratoClaroGatewayV6"
    assert GATEWAY_TOOL_NAME == "contratoclaro-gateway"


def test_v6_catalog_matches_the_corpus_already_ingested_in_the_kb():
    assert V6_CATALOG == [
        {"id": "e60f65792618", "name": "contrato_malicioso.md"},
        {"id": "1dcfdd549efd", "name": "contrato_v1.md"},
        {"id": "557082276e65", "name": "contrato_v2.md"},
    ]


def test_gateway_request_uses_iam_and_matches_installed_boto_shape():
    request = gateway_request(f"arn:aws:iam::{ACCOUNT_ID}:role/ContratoClaroGatewayV6Role")

    assert request["authorizerType"] == "AWS_IAM"
    assert request["protocolType"] == "MCP"
    validate_parameters(request, _input_shape("CreateGateway"))


def test_gateway_trust_can_be_scoped_to_created_gateway():
    trust = gateway_trust_policy(ACCOUNT_ID, REGION, GATEWAY_ARN)
    statement = trust["Statement"][0]

    assert statement["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Condition"] == {
        "StringEquals": {"aws:SourceAccount": ACCOUNT_ID},
        "ArnLike": {"aws:SourceArn": GATEWAY_ARN},
    }


def test_gateway_target_uses_inline_lambda_schema_and_gateway_role():
    request = gateway_target_request(GATEWAY_ID, LAMBDA_ARN)

    tool = request["targetConfiguration"]["mcp"]["lambda"]["toolSchema"]["inlinePayload"][0]
    assert tool["name"] == "buscar_clausulas"
    assert set(tool["inputSchema"]["required"]) == {"query", "document_ids"}
    assert set(tool["inputSchema"]) == {"type", "description", "properties", "required"}
    assert request["credentialProviderConfigurations"] == [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    validate_parameters(request, _input_shape("CreateGatewayTarget"))


def test_v6_policies_limit_lambda_gateway_and_kb_resources():
    assert gateway_policy(LAMBDA_ARN)["Statement"][0] == {
        "Sid": "InvokeOnlyKbLambdaV6",
        "Effect": "Allow",
        "Action": "lambda:InvokeFunction",
        "Resource": LAMBDA_ARN,
    }
    policy = kb_lambda_policy(ACCOUNT_ID, REGION, "ABCDEFGHIJ")
    retrieve = next(item for item in policy["Statement"] if item["Sid"] == "RetrieveExistingKnowledgeBase")
    assert retrieve["Action"] == "bedrock:Retrieve"
    assert retrieve["Resource"] == ("arn:aws:bedrock:us-east-2:123456789012:knowledge-base/ABCDEFGHIJ")


def test_harness_v6_exposes_gateway_only_and_matches_boto_shape():
    request = harness_v6_request(HARNESS_ROLE_ARN, GATEWAY_ARN)

    assert request["tools"] == [
        {
            "type": "agentcore_gateway",
            "name": "contratoclaro-gateway",
            "config": {
                "agentCoreGateway": {
                    "gatewayArn": GATEWAY_ARN,
                    "outboundAuth": {"awsIam": {}},
                }
            },
        }
    ]
    assert request["allowedTools"] == ["@contratoclaro-gateway"]
    assert all(tool["type"] != "inline_function" for tool in request["tools"])
    validate_parameters(request, _input_shape("CreateHarness"))


def test_harness_v6_update_wraps_memory_for_update_shape():
    request = harness_v6_update_request(HARNESS_ROLE_ARN, GATEWAY_ARN)

    assert "harnessName" not in request
    assert "tags" not in request
    assert request["memory"] == {
        "optionalValue": {
            "managedMemoryConfiguration": {
                "strategies": ["SUMMARIZATION"],
                "eventExpiryDuration": 3,
            }
        }
    }
    validate_parameters(
        {"harnessId": "ContratoClaroGatewayV6-oAs8olxMIs", **request},
        _input_shape("UpdateHarness"),
    )


def test_harness_v6_prompt_contains_fixed_catalog_and_gateway_citation_contract():
    request = harness_v6_request(HARNESS_ROLE_ARN, GATEWAY_ARN)
    prompt = request["systemPrompt"][0]["text"]

    assert "1dcfdd549efd" in prompt and "contrato_v1.md" in prompt
    assert "557082276e65" in prompt and "contrato_v2.md" in prompt
    assert "e60f65792618" in prompt and "contrato_malicioso.md" in prompt
    assert "results[].reference" in prompt


def test_harness_v6_policy_invokes_only_selected_gateway_and_no_runtime_command():
    policy = harness_v6_policy(ACCOUNT_ID, REGION, GATEWAY_ARN)
    gateway = next(item for item in policy["Statement"] if item["Sid"] == "InvokeOnlyGatewayV6")

    assert gateway == {
        "Sid": "InvokeOnlyGatewayV6",
        "Effect": "Allow",
        "Action": "bedrock-agentcore:InvokeGateway",
        "Resource": GATEWAY_ARN,
    }
    assert "InvokeAgentRuntimeCommand" not in json.dumps(policy)

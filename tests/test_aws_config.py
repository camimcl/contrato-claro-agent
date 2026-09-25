from infra.aws_config import evaluator_request, harness_policy, harness_request


def test_harness_request_locks_model_memory_and_tools():
    request = harness_request("arn:aws:iam::123456789012:role/ContratoClaroHarnessRole")
    assert request["model"]["bedrockModelConfig"] == {
        "modelId": "google.gemma-4-31b",
        "apiFormat": "responses",
        "maxTokens": 1024,
    }
    assert request["allowedTools"] == ["@buscar_clausulas"]
    assert request["tools"][0]["name"] == "buscar_clausulas"
    assert request["memory"]["managedMemoryConfiguration"]["eventExpiryDuration"] == 3
    assert request["maxIterations"] == 3


def test_harness_policy_excludes_unused_high_risk_services():
    policy = harness_policy("123456789012", "us-east-2")
    actions = {
        action
        for statement in policy["Statement"]
        for action in ([statement["Action"]] if isinstance(statement["Action"], str) else statement["Action"])
    }
    assert "bedrock:InvokeModel" in actions
    assert "bedrock-agentcore:InvokeCodeInterpreter" not in actions
    assert "bedrock-agentcore:StartBrowserSession" not in actions
    assert "bedrock-agentcore:InvokeAgentRuntimeCommand" not in actions


def test_harness_policy_allows_mantle_responses_on_default_project():
    policy = harness_policy("123456789012", "us-east-2")
    statement = next(
        item
        for item in policy["Statement"]
        if "bedrock-mantle:CreateInference"
        in ([item["Action"]] if isinstance(item["Action"], str) else item["Action"])
    )
    assert statement["Resource"] == ("arn:aws:bedrock-mantle:us-east-2:123456789012:project/default")


def test_harness_policy_allows_mantle_bearer_token_authentication():
    policy = harness_policy("123456789012", "us-east-2")
    statement = next(
        item
        for item in policy["Statement"]
        if "bedrock-mantle:CallWithBearerToken"
        in (item["Action"] if isinstance(item["Action"], list) else [item["Action"]])
    )
    assert statement["Effect"] == "Allow"
    assert statement["Resource"] == "*"
    assert statement["Condition"] == {"StringEquals": {"bedrock-mantle:BearerTokenType": "SHORT_TERM"}}


def test_custom_evaluator_request_is_trace_level_code_based():
    request = evaluator_request("arn:aws:lambda:us-east-2:123456789012:function:ContratoClaroConformidade")
    assert request["level"] == "TRACE"
    assert request["evaluatorConfig"]["codeBased"]["lambdaConfig"]["lambdaTimeoutInSeconds"] == 30

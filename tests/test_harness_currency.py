from types import SimpleNamespace

from contratoclaro.harness import (
    controlled_grounded_failure,
    has_malformed_brl,
    has_unverified_brl,
    repair_brl_from_evidence,
)


def test_detects_truncated_currency_value_from_harness_answer():
    assert has_malformed_brl("O total é R$ 12.0,0 [E1].")
    assert has_malformed_brl("A multa é R$ 50,0 [E1].")


def test_accepts_complete_brazilian_currency_value():
    assert not has_malformed_brl("O total é R$ 12.000,00 [E1].")


def test_rejects_complete_but_wrong_currency_value():
    evidence = [SimpleNamespace(text="Rodadas adicionais custam R$ 600,00 cada.")]
    assert has_unverified_brl("Cada rodada custa R$ 60,00 [E1].", evidence)
    assert not has_unverified_brl("Cada rodada custa R$ 600,00 [E1].", evidence)


def test_repairs_truncated_value_only_from_an_unambiguous_retrieved_value():
    evidence = [SimpleNamespace(text="O preço é R$ 12.000,00 e a revisão custa R$ 600,00.")]
    answer, repairs = repair_brl_from_evidence("O preço é R$ 12.0,0 [E1].", evidence)
    assert answer == "O preço é R$ 12.000,00 [E1]."
    assert repairs == [{"rendered": "R$ 12.0,0", "replaced_with": "R$ 12.000,00"}]


def test_does_not_repair_an_ambiguous_or_unrelated_value():
    evidence = [SimpleNamespace(text="Valores: R$ 2.000,00 e R$ 2.050,00.")]
    answer, repairs = repair_brl_from_evidence("O total é R$ 2,0.", evidence)
    assert answer == "O total é R$ 2,0."
    assert repairs == []


def test_grounding_exhaustion_returns_a_cited_safe_fallback():
    answer = controlled_grounded_failure("E1")
    assert "não controlam a análise" in answer
    assert "[E1]" in answer

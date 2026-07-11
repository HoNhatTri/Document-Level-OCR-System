from src.llm_agent import OptionalLLMAgent


def test_llm_zero_confidence_is_normalized_to_default():
    agent = OptionalLLMAgent()

    assert agent._confidence(0) == 0.62
    assert agent._confidence("0") == 0.62
    assert agent._confidence(None) == 0.62

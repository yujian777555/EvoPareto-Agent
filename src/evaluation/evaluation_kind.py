"""Evaluation kind taxonomy (Phase5-R3 audit).

- simulated: MockLLM + synthetic scoring (offline algorithm tests)
- real_llm_proxy: real LLM text + synthetic/capability scoring
- real_llm_failed: real LLM call failed; NO success credit
- real_environment: native ALFWorld/WebShop eval (NOT implemented yet)
"""

SIMULATED = "simulated"
REAL_LLM_PROXY = "real_llm_proxy"
REAL_LLM_FAILED = "real_llm_failed"
REAL_ENVIRONMENT = "real_environment"

ALL_KINDS = (SIMULATED, REAL_LLM_PROXY, REAL_LLM_FAILED, REAL_ENVIRONMENT)


def classify_experiment(backend: str, api_ok: bool, native_env: bool = False) -> str:
    if native_env:
        return REAL_ENVIRONMENT
    if not api_ok:
        return REAL_LLM_FAILED
    if backend in ("mock", "auto"):
        return SIMULATED
    return REAL_LLM_PROXY

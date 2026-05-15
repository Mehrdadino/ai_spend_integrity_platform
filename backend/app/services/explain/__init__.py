"""§4 explainability package (templates from stored evidence; optional LLM polish later).

Re-exports ``build_explainability_v1`` so callers can ``from app.services.explain import …``.
"""

from app.services.explain.anomaly_v1 import ExplainabilityV1, build_explainability_v1

__all__ = ["ExplainabilityV1", "build_explainability_v1"]

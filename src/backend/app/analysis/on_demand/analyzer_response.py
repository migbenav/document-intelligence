"""Standard return type for all on-demand analyzers.

Wraps the typed Pydantic result with metadata about the LLM call:
which model actually produced the response, which prompt version was used,
and whether a fallback model was invoked.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class AnalyzerResponse:
    """Standard return type for all on-demand analyzers."""

    result: BaseModel
    model_id: str
    prompt_version: str
    fallback_used: bool = field(default=False)

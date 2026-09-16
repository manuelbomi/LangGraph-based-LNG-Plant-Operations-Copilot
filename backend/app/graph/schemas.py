"""Pydantic schemas used for LLM structured-output calls in the plant-ops
graph (`app/graph/nodes.py`).

Every schema here is deliberately narrow and framed as a recommendation for
a qualified engineer to review -- there is no "action_taken" or
"equipment_command" field anywhere. See the root README's "Scope & Safety"
section and the seeded prompt text in `app/prompts/seed_prompts.py`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RootCauseInvestigation(BaseModel):
    root_cause_hypothesis: str = Field(
        default="",
        description=(
            "The most likely root cause hypothesis for this anomaly, grounded in the retrieved "
            "maintenance-manual / past-incident context. Framed as a hypothesis for engineer "
            "confirmation, never a certainty."
        ),
    )
    recommended_response: str = Field(
        default="",
        description="The recommended next steps/response, drawn from the retrieved guidance -- for engineer review, not automatic action.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description=(
            "Short labels identifying which retrieved source(s) this hypothesis/response draws on "
            "(e.g. 'Manual: Compressor C-201 Discharge Pressure High', 'Incident: April 2025 C-201 "
            "Discharge Pressure Drift'), copied from the retrieved context provided."
        ),
    )


class DraftWorkOrder(BaseModel):
    title: str = Field(default="", description="Short work order title, e.g. 'Investigate rising discharge pressure on C-201'.")
    description: str = Field(
        default="",
        description=(
            "A clear description of the observed anomaly, the root-cause hypothesis, and the "
            "recommended action, written for a maintenance/reliability engineer. Must end by "
            "noting this is a draft recommendation requiring engineer review and approval, and "
            "does not authorize any automatic equipment action."
        ),
    )
    priority: Literal["low", "medium", "high", "urgent"] = Field(
        default="medium", description="Suggested work order priority based on severity and potential safety impact."
    )

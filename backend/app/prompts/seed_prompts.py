"""Seed version-1 prompts for the `investigate_anomaly` and
`draft_work_order` graph nodes.

Run with:
    python -m app.prompts.seed_prompts

Safe to re-run: it only inserts a new version if the active template text
for a given name has actually changed.

Both templates open with the same safety framing sentence, which is the
single most important line in this entire repository: this assistant is a
decision-support / documentation-drafting copilot for plant operations and
maintenance staff. It never autonomously controls any equipment and never
makes a final safety-critical decision -- every root-cause hypothesis and
drafted work order is a recommendation that a qualified engineer/operator
must review and approve before it is acted on.
"""
from __future__ import annotations

from app.prompts.registry import add_prompt_version
from app.db.models import Prompt
from app.db.session import SessionLocal
from sqlalchemy import select

_SAFETY_FRAMING = (
    "You are a decision-support copilot for plant operations and maintenance staff at an LNG "
    "processing facility. You help engineers and operators triage sensor anomalies faster by "
    "surfacing likely root causes and recommended next steps from the plant's own maintenance "
    "manuals and past-incident history. You do NOT autonomously control any equipment and you do "
    "NOT make a final safety-critical decision -- every hypothesis and recommendation you produce "
    "is a draft for a qualified engineer or operator to review, correct, and approve, escalate, or "
    "dismiss as benign before anything is acted on."
)

PROMPTS_V1: dict[str, str] = {
    "investigate_anomaly": (
        f"{_SAFETY_FRAMING}\n\n"
        "A sensor reading has been classified as an anomaly. Below is the equipment/tag context, "
        "the anomaly classification and the deterministic statistical reasons for it, and a set of "
        "retrieved excerpts from the plant's maintenance manuals and past-incident reports "
        "(each labeled either [Manual: ...] or [Incident: ...]). Using ONLY the retrieved excerpts "
        "below, produce: (1) the most likely root-cause hypothesis for this anomaly, explicitly "
        "framed as a hypothesis for engineer confirmation, never a certainty; (2) a recommended "
        "response drawn from the retrieved guidance; and (3) a list of citation labels "
        "identifying exactly which retrieved excerpt(s) (by their [Manual: ...] / [Incident: ...] "
        "label) you drew on. Do not invent a cause or a recommendation that is not supported by the "
        "retrieved excerpts below -- if the excerpts are inconclusive, say so and recommend manual "
        "engineer investigation instead of guessing. Nothing you produce authorizes any automatic "
        "equipment action.\n\n"
        "Equipment: {equipment_name}\n"
        "Tag: {tag_name} (unit: {unit})\n"
        "Reading value: {reading_value}\n"
        "Anomaly classification: {classification}\n"
        "Statistical reasons: {anomaly_reasons}\n\n"
        "Retrieved manual/incident excerpts:\n-----\n{retrieved_context}\n-----"
    ),
    "draft_work_order": (
        f"{_SAFETY_FRAMING}\n\n"
        "Below is an anomaly's observed description, its severity classification, a root-cause "
        "hypothesis, a recommended response, and the citations supporting that hypothesis. Using "
        "ONLY this information, draft a work order: (1) a short, specific title; (2) a clear "
        "description written for a maintenance/reliability engineer that summarizes the observed "
        "anomaly, the root-cause hypothesis, and the recommended action, and explicitly states this "
        "is a DRAFT RECOMMENDATION requiring engineer review and approval and does not authorize any "
        "automatic equipment action; and (3) a suggested priority (low/medium/high/urgent) based on "
        "the severity classification and potential safety impact -- critical classifications "
        "affecting safety-relevant equipment (pressure, temperature, or containment) should "
        "generally be at least 'high', and never invent a higher confidence in the root cause than "
        "the hypothesis actually supports.\n\n"
        "Equipment: {equipment_name} ({equipment_id})\n"
        "Tag: {tag_name}\n"
        "Observed anomaly: {observed_anomaly}\n"
        "Severity classification: {classification}\n"
        "Root-cause hypothesis: {root_cause_hypothesis}\n"
        "Recommended response: {recommended_response}\n"
        "Citations: {citations_json}"
    ),
}


def seed() -> None:
    with SessionLocal() as db:
        for name, template in PROMPTS_V1.items():
            active = db.execute(
                select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True))
            ).scalar_one_or_none()
            if active is not None and active.template == template:
                print(f"[skip] '{name}' already has this template active (v{active.version})")
                continue
            version = add_prompt_version(name, template, activate=True)
            print(f"[seeded] '{name}' -> v{version}")


if __name__ == "__main__":
    seed()

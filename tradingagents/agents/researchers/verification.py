"""Normalization and compact rendering for research verification results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from tradingagents.agents.schemas import (
    FindingCategory,
    FindingSeverity,
    ResearchVerification,
    VerificationStatus,
)

from .arithmetic import check_arithmetic

MAX_REPAIR_ROUNDS = 1


def normalize_verification(result: ResearchVerification) -> ResearchVerification:
    """Apply deterministic arithmetic checks and derive routing fields."""
    findings = []
    for finding in result.findings:
        arithmetic_checks = [
            check_arithmetic(item.operation, item.operands, item.reported_result)
            for item in finding.arithmetic
        ]
        mismatches = [
            check for check in arithmetic_checks if check.matches_reported is False
        ]
        if (
            arithmetic_checks
            and all(check.matches_reported is True for check in arithmetic_checks)
            and finding.category is FindingCategory.ARITHMETIC_ERROR
        ):
            continue
        if mismatches:
            corrections = "; ".join(
                f"Computed result: {check.computed_result}" for check in mismatches
            )
            finding = finding.model_copy(
                update={
                    "category": FindingCategory.ARITHMETIC_ERROR,
                    "severity": FindingSeverity.HIGH,
                    "correction": corrections,
                }
            )
        findings.append(finding)

    high_findings = [
        finding for finding in findings if finding.severity is FindingSeverity.HIGH
    ]
    if high_findings:
        status = VerificationStatus.FAIL
    elif findings or result.status is VerificationStatus.WARN:
        status = VerificationStatus.WARN
    else:
        status = VerificationStatus.PASS

    targets = []
    for finding in high_findings:
        agent = finding.agent.lower()
        for target in ("bull", "bear"):
            if target in agent and target not in targets:
                targets.append(target)
    if high_findings and not targets:
        targets = ["bull", "bear"]

    return result.model_copy(
        update={
            "status": status,
            "findings": findings,
            "repair_required": bool(high_findings),
            "repair_targets": targets,
        }
    )


def verification_from_state(value: dict[str, Any]) -> ResearchVerification:
    return ResearchVerification.model_validate(value)


def render_verification_history(
    history: list[dict[str, Any]],
    *,
    repaired_agents: list[str] | None = None,
    include_details: bool = True,
) -> str:
    """Render verification passes for manager context or the human report."""
    if not history:
        return "No research verification result was produced."

    lines = []
    for index, raw_result in enumerate(history, start=1):
        result = verification_from_state(raw_result)
        lines.append(f"Pass {index}: {result.status.value}")
        counts = Counter(
            (finding.severity.value, finding.category.value)
            for finding in result.findings
        )
        if not counts:
            lines.append("- No findings")
        else:
            for (severity, category), count in sorted(counts.items()):
                lines.append(f"- {count} {severity} {category}")
        if include_details:
            for finding in result.findings:
                detail = (
                    f"  - {finding.severity.value} {finding.category.value} "
                    f"[{finding.agent}]: {finding.claim}"
                )
                if finding.correction:
                    detail += f" Correction: {finding.correction}"
                detail += f" Reason: {finding.reason}"
                lines.append(detail)
            for point in result.verified_points:
                lines.append(f"  - VERIFIED: {point}")
            if result.notes:
                lines.append(f"  - NOTE: {result.notes}")
        lines.append("")

    if repaired_agents:
        labels = ", ".join(agent.title() for agent in repaired_agents)
        lines.append(f"Repair: {labels}")
    return "\n".join(lines).strip()

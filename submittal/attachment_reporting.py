"""Safe Markdown and JSON exports for attachment intelligence."""

import json
from pathlib import Path

from .attachment_intelligence import PackageAttachmentAnalysisService
from .attachment_models import PackageRevisionComparison
from .attachment_repository import JsonAttachmentIntelligenceRepository


class AttachmentIntelligenceRenderer:
    def __init__(
        self,
        repository: JsonAttachmentIntelligenceRepository,
        analysis: PackageAttachmentAnalysisService,
    ) -> None:
        self.repository = repository
        self.analysis = analysis

    def markdown(self, project_id: str, package_id: str) -> str:
        summary = self.analysis.summary(project_id, package_id)
        evidence = self.analysis.latest_evidence_set(project_id, package_id)
        lines = [
            "# Brunel Submittal Attachment Intelligence",
            "",
            f"- Project: `{project_id}`",
            f"- Package: `{package_id}`",
            f"- Package revision: {summary.package_revision}",
            f"- Evidence set: `{summary.evidence_set_id or 'not generated'}`",
            f"- Active attachment revisions: {summary.active_revision_count}",
            f"- Readable attachments: {summary.readable_count}",
            f"- Missing required attachment types: {summary.missing_count}",
            f"- Conflicts: {summary.conflict_count}",
            f"- Possible deviations: {summary.deviation_count}",
            "",
            "> Brunel reports submitted facts and proposed mappings. It does not determine professional design compliance or alter an official disposition.",
            "",
            "## Attachments",
            "",
        ]
        for attachment in self.repository.list_attachments(project_id, package_id):
            revision = next(
                item for item in attachment.revisions if item.id == attachment.active_revision_id
            )
            lines.extend(
                (
                    f"### {attachment.display_name}",
                    "",
                    f"- Attachment ID: `{attachment.id}`",
                    f"- Revision ID: `{revision.id}`",
                    f"- Type: {revision.inferred_type.value}",
                    f"- Readability: {revision.readability_status.value}",
                    f"- SHA-256: `{revision.content_hash}`",
                    "",
                )
            )
        if evidence:
            lines.extend(("## Proposed compliance mappings", ""))
            for mapping in evidence.compliance_mappings:
                lines.extend(
                    (
                        f"### {mapping.specification_section} / `{mapping.requirement_id}`",
                        "",
                        f"- Proposed status: {mapping.proposed_status.value}",
                        f"- Human confirmation: {mapping.human_confirmation_status.value}",
                        f"- Explanation: {mapping.proposed_explanation}",
                        f"- Specification citation: {mapping.specification_evidence.citation.document_name}, page {mapping.specification_evidence.citation.page_number}, chunk `{mapping.specification_evidence.citation.chunk_id}`",
                    )
                )
                for citation in mapping.supporting_evidence:
                    lines.append(
                        f"- Attachment citation: {citation.citation.document_name}, page {citation.citation.page_number}, chunk `{citation.citation.chunk_id}` — {citation.excerpt}"
                    )
                lines.append("")
            lines.extend(("## Exceptions requiring human review", ""))
            for missing in evidence.missing_attachments:
                lines.append(
                    f"- Missing {missing.missing_type.value}: {missing.package_evidence_state}"
                )
            for conflict in evidence.conflicts:
                lines.append(f"- Conflict in {conflict.subject}: {', '.join(conflict.values)}")
            for deviation in evidence.possible_deviations:
                lines.append(
                    f"- Possible deviation `{deviation.attribute_name}`: specified {deviation.specified_value}; submitted {deviation.submitted_value}."
                )
        return "\n".join(lines).rstrip() + "\n"

    def export(
        self, project_id: str, package_id: str, output: Path, *, format: str = "markdown"
    ) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if format == "markdown":
            output.write_text(self.markdown(project_id, package_id), encoding="utf-8")
        elif format == "json":
            evidence = self.analysis.latest_evidence_set(project_id, package_id)
            payload = {
                "summary": self.analysis.summary(project_id, package_id).model_dump(mode="json"),
                "evidence_set": evidence.model_dump(mode="json") if evidence else None,
            }
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            raise ValueError("Attachment export format must be markdown or json")
        return output

    @staticmethod
    def comparison_markdown(comparison: PackageRevisionComparison) -> str:
        lines = [
            "# Brunel Package Attachment Revision Comparison",
            "",
            f"- Project: `{comparison.project_id}`",
            f"- Package: `{comparison.package_id}`",
            f"- Old revision: {comparison.old_package_revision}",
            f"- New revision: {comparison.new_package_revision}",
            f"- Old evidence hash: `{comparison.old_evidence_set_hash}`",
            f"- New evidence hash: `{comparison.new_evidence_set_hash}`",
            f"- Re-review required: {'yes' if comparison.re_review_required else 'no'}",
            "",
            "> Changes are deterministic evidence indicators and require human review.",
            "",
            "## Executive summary",
            "",
        ]
        if comparison.summary:
            lines.extend(
                f"- {key.replace('_', ' ')}: {value}" for key, value in comparison.summary.items()
            )
        else:
            lines.append("- No material evidence-set changes detected.")
        lines.extend(("", "## Changes", ""))
        for change in comparison.changes:
            lines.extend(
                (
                    f"### {change.change_type.value}: {change.subject}",
                    "",
                    f"- Old: {change.old_value or 'not present'}",
                    f"- New: {change.new_value or 'not present'}",
                )
            )
            for evidence in change.old_evidence:
                lines.append(
                    f"- Old citation: {evidence.citation.document_name}, page {evidence.citation.page_number}, chunk `{evidence.citation.chunk_id}` — {evidence.excerpt}"
                )
            for evidence in change.new_evidence:
                lines.append(
                    f"- New citation: {evidence.citation.document_name}, page {evidence.citation.page_number}, chunk `{evidence.citation.chunk_id}` — {evidence.excerpt}"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

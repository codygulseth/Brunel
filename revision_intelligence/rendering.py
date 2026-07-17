"""Professional Markdown rendering without exposing unvalidated content."""

from pathlib import Path

from .models import DocumentComparison


class MarkdownComparisonRenderer:
    def render(self, comparison: DocumentComparison) -> str:
        lines = [
            f"# Revision Comparison: {comparison.old_document.title or comparison.old_document.original_filename} → {comparison.new_document.title or comparison.new_document.original_filename}",
            "",
            f"- **Project:** {comparison.project_id}",
            f"- **Comparison ID:** `{comparison.id}`",
            f"- **Status:** {comparison.status.value}",
            f"- **Created:** {comparison.created_at.isoformat()}",
            f"- **Comparability:** {comparison.comparability.score:.2f}",
            "",
            "## Executive summary",
            "",
            comparison.summary.executive_summary,
            "",
            "Potential implications below are decision support and require professional review.",
            "",
            "## Priority review",
            "",
        ]
        if not comparison.changes:
            lines.append("No material text changes were detected.")
        for change in comparison.changes:
            lines.extend(
                [
                    f"### {change.title} (`{change.id}`)",
                    "",
                    f"- **Type:** {change.change_type.value}",
                    f"- **Severity:** {change.severity.value}",
                    f"- **Categories:** {', '.join(item.value for item in change.categories)}",
                    f"- **Evidence strength:** {change.evidence_strength.value}",
                    f"- **Why flagged:** {change.explanation}",
                    "",
                ]
            )
            if change.evidence.old_excerpt is not None:
                cite = change.evidence.old_citation
                if cite is None:
                    raise ValueError("Old excerpt is missing its source citation")
                lines.extend(
                    [
                        f"**Old evidence** — {cite.document_name}, page {cite.page_number}",
                        "",
                        f"> {change.evidence.old_excerpt}",
                        "",
                    ]
                )
            if change.evidence.new_excerpt is not None:
                cite = change.evidence.new_citation
                if cite is None:
                    raise ValueError("New excerpt is missing its source citation")
                lines.extend(
                    [
                        f"**New evidence** — {cite.document_name}, page {cite.page_number}",
                        "",
                        f"> {change.evidence.new_excerpt}",
                        "",
                    ]
                )
            lines.extend(
                [
                    f"**Possible implication (requires review):** {change.implications[0].statement}",
                    "",
                ]
            )
        lines.extend(["## Warnings and limitations", ""])
        lines.extend(f"- {warning}" for warning in comparison.warnings)
        lines.extend(
            [
                "- Text extraction quality depends on the source document.",
                "- No OCR, raster comparison, CAD, BIM, or graphical change clouding is performed.",
                "- Significance is not a confirmed cost, schedule, scope, safety, or quality impact.",
                "",
                "## Unchanged summary",
                "",
                f"{comparison.summary.unchanged_blocks} unchanged aligned blocks ({comparison.summary.unchanged_percentage:.1f}% approximately unchanged).",
                "",
            ]
        )
        return "\n".join(lines)

    def write(
        self, comparison: DocumentComparison, output: Path, allowed_root: Path | None = None
    ) -> Path:
        target = output.expanduser().resolve()
        root = (allowed_root or Path.cwd()).expanduser().resolve()
        if target != root and root not in target.parents:
            raise ValueError("Report output must stay within the allowed report directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(comparison), encoding="utf-8")
        return target

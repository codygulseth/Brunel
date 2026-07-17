"""Safe JSON/Markdown drawing comparison rendering."""

from .models import DrawingSetComparison


class MarkdownDrawingComparisonRenderer:
    def render(self, value: DrawingSetComparison) -> str:
        lines = [
            "# Drawing Set Comparison",
            "",
            f"- Project: {value.project_id}",
            f"- Old revision: {value.old_revision_id}",
            f"- New revision: {value.new_revision_id}",
            f"- Compared: {value.created_at.isoformat()}",
            "",
            "## Executive summary",
            "",
            f"{len(value.changes)} deterministic metadata/text changes detected.",
            "",
            "## Sheet change register",
            "",
        ]
        for change in value.changes:
            lines.extend(
                [
                    f"### {change.sheet_number or 'Set'} — {change.change_type}",
                    "",
                    change.summary,
                    "",
                    f"Human visual review required: {'yes' if change.human_visual_review_required else 'no'}",
                    "",
                ]
            )
        lines.extend(
            [
                "## Limitations",
                "",
                "- Native text and metadata comparisons do not interpret graphical design intent.",
                "- OCR evidence remains separate and may require human confirmation.",
                "- Visual-only changes remain unexplained.",
            ]
        )
        return "\n".join(lines)

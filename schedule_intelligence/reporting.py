"""Schedule comparison and register Markdown exports."""

from .models import ScheduleActivityRevision, ScheduleRevisionComparison


def comparison_markdown(c: ScheduleRevisionComparison) -> str:
    lines = [
        "# Schedule Revision Comparison",
        "",
        f"{c.old_revision_id} → {c.new_revision_id}",
        "",
        f"Forecast project finish change: {c.project_finish_change_days if c.project_finish_change_days is not None else 'unknown'} calendar days",
        "",
        "## Activity changes",
    ]
    lines += [f"- **{x.summary}**" for x in c.changes]
    lines += ["", "## Limitations", *[f"- {x}" for x in c.limitations]]
    return "\n".join(lines) + "\n"


def register_markdown(items: tuple[ScheduleActivityRevision, ...]) -> str:
    lines = [
        "# Schedule Activity Register",
        "",
        "| ID | Activity | Status | Planned start | Planned finish | Source float |",
        "|---|---|---|---|---|---|",
    ]
    for x in items:
        lines.append(
            f"| {x.source_activity_id} | {x.name} | {x.status.value} | {x.planned_start or ''} | {x.planned_finish or ''} | {x.source_total_float if x.source_total_float is not None else ''} |"
        )
    return "\n".join(lines) + "\n"

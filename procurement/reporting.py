"""Procurement register and comparison exports."""

import csv
import io
from .models import ProcurementItem, ProcurementPlanComparison


def register_markdown(items: tuple[ProcurementItem, ...]) -> str:
    rows = [
        "# Procurement Register",
        "",
        "| Number | Item | Status | Required on site | Exposure |",
        "|---|---|---|---|---|",
    ]
    for x in items:
        exposure = x.exposure_assessments[-1].level.value if x.exposure_assessments else "unknown"
        rows.append(
            f"| {x.procurement_number} | {x.title} | {x.status.value} | {x.required_on_site.value if x.required_on_site else 'unknown'} | {exposure} |"
        )
    return "\n".join(rows) + "\n"


def register_csv(items: tuple[ProcurementItem, ...]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(("procurement_number", "title", "status", "required_on_site", "exposure"))
    for x in items:
        writer.writerow(
            (
                x.procurement_number,
                x.title,
                x.status.value,
                x.required_on_site.value if x.required_on_site else "",
                x.exposure_assessments[-1].level.value if x.exposure_assessments else "unknown",
            )
        )
    return out.getvalue()


def comparison_markdown(value: ProcurementPlanComparison) -> str:
    rows = ["# Procurement Plan Comparison", "", f"{value.old_plan_id} → {value.new_plan_id}", ""]
    rows += [
        f"- **{x.procurement_number}** {x.change_type}: {x.field or ''} `{x.old_value}` → `{x.new_value}`"
        for x in value.changes
    ]
    return "\n".join(rows) + "\n"

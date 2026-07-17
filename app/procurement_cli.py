"""CLI adapter for procurement planning workflows."""

import argparse
from datetime import date
from config.settings import Settings
from procurement.models import ProcurementCategory, ProcurementStatus
from procurement.repository import JsonProcurementRepository
from procurement.reporting import comparison_markdown, register_markdown
from procurement.service import ProcurementService

COMMANDS = {
    "procurement-create",
    "procurement-list",
    "procurement-show",
    "procurement-link-submittal",
    "procurement-lead-time-add",
    "procurement-plan-dates",
    "procurement-transition",
    "procurement-authorize-release",
    "procurement-record-release",
    "procurement-milestone",
    "procurement-delivery",
    "procurement-dashboard",
    "procurement-plan-snapshot",
    "procurement-plan-compare",
    "procurement-search",
}


def register_procurement_commands(commands):
    p = commands.add_parser("procurement-create")
    p.add_argument("--project-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--category", choices=[x.value for x in ProcurementCategory], default="other")
    p.add_argument("--required-on-site", type=date.fromisoformat)
    p = commands.add_parser("procurement-list")
    p.add_argument("--project-id", required=True)
    p.add_argument("--status", choices=[x.value for x in ProcurementStatus])
    p.add_argument("--exposure")
    p = commands.add_parser("procurement-show")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p = commands.add_parser("procurement-link-submittal")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--submittal-id", required=True)
    p = commands.add_parser("procurement-lead-time-add")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--duration", required=True, type=int)
    p.add_argument("--unit", choices=("days", "weeks"), required=True)
    p.add_argument("--definition", required=True)
    p.add_argument("--source-note")
    p = commands.add_parser("procurement-plan-dates")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--shipping-days", type=int, required=True)
    p.add_argument("--fabrication-days", type=int)
    p.add_argument("--processing-days", type=int, required=True)
    p.add_argument("--review-days", type=int, required=True)
    p = commands.add_parser("procurement-transition")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--status", choices=[x.value for x in ProcurementStatus], required=True)
    p.add_argument("--reason")
    p = commands.add_parser("procurement-authorize-release")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--authorized-by", required=True)
    p.add_argument("--reference", required=True)
    p = commands.add_parser("procurement-record-release")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p = commands.add_parser("procurement-milestone")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--forecast-date", type=date.fromisoformat)
    p = commands.add_parser("procurement-delivery")
    p.add_argument("--project-id", required=True)
    p.add_argument("--item-id", required=True)
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--status", default="delivered")
    p.add_argument("--partial", action="store_true")
    for name in ("procurement-dashboard", "procurement-plan-snapshot"):
        p = commands.add_parser(name)
        p.add_argument("--project-id", required=True)
    p = commands.add_parser("procurement-plan-compare")
    p.add_argument("--project-id", required=True)
    p.add_argument("--old-plan-id", required=True)
    p.add_argument("--new-plan-id", required=True)
    p = commands.add_parser("procurement-search")
    p.add_argument("--project-id", required=True)
    p.add_argument("--query", required=True)


def run_procurement_command(args: argparse.Namespace, settings: Settings) -> int:
    s = ProcurementService(JsonProcurementRepository(settings.data_directory / "procurement"))
    p = args.project_id
    try:
        if args.command == "procurement-create":
            value = s.create_item(
                p,
                args.title,
                category=ProcurementCategory(args.category),
                required_on_site=args.required_on_site,
            )
            print(value.model_dump_json(indent=2))
        elif args.command in {"procurement-list", "procurement-search"}:
            print(
                register_markdown(
                    s.list_items(
                        p,
                        status=ProcurementStatus(args.status)
                        if getattr(args, "status", None)
                        else None,
                        query=getattr(args, "query", None),
                    )
                )
            )
        elif args.command == "procurement-show":
            print(s._require_item(p, args.item_id).model_dump_json(indent=2))
        elif args.command == "procurement-link-submittal":
            print(
                s.link_product_and_submittal(
                    p,
                    args.item_id,
                    actor="cli-user",
                    submittal_id=args.submittal_id,
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-lead-time-add":
            print(
                s.add_lead_time(
                    p,
                    args.item_id,
                    args.duration,
                    args.unit,
                    args.definition,
                    "human_entry",
                    actor="cli-user",
                    notes=args.source_note,
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-plan-dates":
            print(
                s.calculate_dates(
                    p,
                    args.item_id,
                    shipping_days=args.shipping_days,
                    fabrication_days=args.fabrication_days,
                    procurement_processing_days=args.processing_days,
                    design_review_days=args.review_days,
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-transition":
            print(
                s.transition(
                    p, args.item_id, ProcurementStatus(args.status), "cli-user", reason=args.reason
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-authorize-release":
            print(
                s.authorize_release(
                    p, args.item_id, args.authorized_by, args.reference
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-record-release":
            value = s.transition(p, args.item_id, ProcurementStatus.RELEASED, "cli-user")
            value = s.add_milestone(
                p,
                args.item_id,
                "released",
                actor="cli-user",
                actual_date=args.date,
                human_confirmed=True,
            )
            print(value.model_dump_json(indent=2))
        elif args.command == "procurement-milestone":
            print(
                s.add_milestone(
                    p, args.item_id, args.type, actor="cli-user", forecast_date=args.forecast_date
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-delivery":
            print(
                s.record_delivery(
                    p, args.item_id, args.date, args.status, "cli-user", partial=args.partial
                ).model_dump_json(indent=2)
            )
        elif args.command == "procurement-dashboard":
            print(s.dashboard(p).model_dump_json(indent=2))
        elif args.command == "procurement-plan-snapshot":
            print(s.snapshot(p, "cli-user").model_dump_json(indent=2))
        elif args.command == "procurement-plan-compare":
            print(comparison_markdown(s.compare_plans(p, args.old_plan_id, args.new_plan_id)))
    except (ValueError, OSError) as exc:
        print(f"Procurement command failed: {exc}")
        return 1
    return 0

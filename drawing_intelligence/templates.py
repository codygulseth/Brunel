"""Configurable deterministic title-block template selection."""

from .models import NormalizedBox, TitleBlockTemplate

RIGHT_SIDE_TEMPLATE = TitleBlockTemplate(
    id="builtin-right-side",
    name="Right-side vertical title block",
    version="1",
    region=NormalizedBox(x_min=0.72, y_min=0.0, x_max=1.0, y_max=1.0),
    priority=10,
    notes="Conservative built-in candidate; requires confirmation when not explicitly selected.",
)
BOTTOM_TEMPLATE = TitleBlockTemplate(
    id="builtin-bottom",
    name="Bottom horizontal title block",
    version="1",
    region=NormalizedBox(x_min=0.0, y_min=0.75, x_max=1.0, y_max=1.0),
    priority=5,
    notes="Conservative built-in candidate; requires confirmation when not explicitly selected.",
)
FULL_PAGE_TEMPLATE = TitleBlockTemplate(
    id="builtin-full-page-fallback",
    name="Full-page text fallback",
    version="1",
    region=NormalizedBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
    priority=0,
    notes="Fallback only; does not claim exact title-block localization.",
)


class TitleBlockTemplateRegistry:
    def __init__(self, templates: tuple[TitleBlockTemplate, ...] = ()) -> None:
        self._templates = {
            item.id: item
            for item in (*templates, RIGHT_SIDE_TEMPLATE, BOTTOM_TEMPLATE, FULL_PAGE_TEMPLATE)
        }

    def get(self, template_id: str) -> TitleBlockTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise ValueError(f"Unknown title-block template: {template_id}") from exc

    def select(self, template_id: str | None = None) -> tuple[TitleBlockTemplate, str, bool]:
        if template_id:
            return self.get(template_id), "user_selected", False
        return FULL_PAGE_TEMPLATE, "full_page_fallback", True

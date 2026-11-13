"""Role-aware overview layouts: which sections appear, in what order, at what width."""

from dataclasses import dataclass
from typing import Literal

SectionKey = Literal[
    "getting_started",
    "insights",
    "approvals",
    "incidents",
    "fill_rate",
    "inventory_risk",
    "workflows",
    "integrations",
    "activity",
    "team",
]
Size = Literal["wide", "narrow"]


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    description: str
    sections: tuple[tuple[SectionKey, Size], ...]


_GS: tuple[SectionKey, Size] = ("getting_started", "wide")

PRESETS: dict[str, Preset] = {
    p.key: p
    for p in [
        Preset(
            "executive",
            "Executive",
            "Exceptions and trends across the organisation first.",
            (
                _GS,
                ("insights", "wide"),
                ("incidents", "narrow"),
                ("team", "narrow"),
                ("fill_rate", "wide"),
                ("approvals", "narrow"),
                ("workflows", "wide"),
                ("integrations", "narrow"),
                ("activity", "narrow"),
            ),
        ),
        Preset(
            "operations",
            "Operations",
            "Exceptions and approvals first, then process health.",
            (
                _GS,
                ("activity", "narrow"),
                ("insights", "wide"),
                ("approvals", "narrow"),
                ("incidents", "narrow"),
                ("fill_rate", "wide"),
                ("inventory_risk", "narrow"),
                ("workflows", "wide"),
                ("integrations", "narrow"),
                ("team", "narrow"),
            ),
        ),
        Preset(
            "finance",
            "Finance",
            "Decisions waiting on you first, then spend-related exceptions.",
            (
                _GS,
                ("approvals", "narrow"),
                ("insights", "wide"),
                ("workflows", "wide"),
                ("activity", "narrow"),
                ("incidents", "narrow"),
                ("integrations", "narrow"),
                ("team", "narrow"),
            ),
        ),
        Preset(
            "warehouse",
            "Warehouse",
            "Stock risk by location and fulfilment first.",
            (
                _GS,
                ("inventory_risk", "narrow"),
                ("insights", "wide"),
                ("fill_rate", "wide"),
                ("incidents", "narrow"),
                ("workflows", "wide"),
                ("approvals", "narrow"),
                ("integrations", "narrow"),
                ("activity", "narrow"),
            ),
        ),
    ]
}

ROLE_DEFAULTS: dict[str, str] = {
    "owner": "executive",
    "administrator": "executive",
    "operations_manager": "operations",
    "approver": "finance",
    "analyst": "operations",
    "viewer": "operations",
}


def default_preset(role_key: str) -> str:
    return ROLE_DEFAULTS.get(role_key, "operations")

"""Dashboard sections that an admin can show or hide per person.

A *section* is a feature area of the product (Activity, Reports, …). By default a person sees a
section when their role allows it — a permission-gated module for staff who watch others, or their own
data for a standard employee. An admin may hide specific sections from one individual; that preference
lives on the user as ``hidden_sections`` and is delivered in their session so the UI omits the section
from their navigation, routes and profile. It is a visibility control: role and scope still govern what
the API returns, so hiding a section never grants access and never widens it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SectionInfo:
    key: str
    label: str
    #: True when a standard employee sees this about themselves (so hiding it affects their own view).
    self_data: bool


SECTION_CATALOG: dict[str, SectionInfo] = {
    s.key: s
    for s in (
        SectionInfo("activity", "Activity", True),
        SectionInfo("productivity", "Productivity", True),
        SectionInfo("attendance", "Attendance", True),
        SectionInfo("time-claims", "Time claims", True),
        SectionInfo("screenshots", "Screenshots", True),
        SectionInfo("live", "Live view", False),
        SectionInfo("reports", "Reports", False),
        SectionInfo("people", "People", False),
        SectionInfo("projects", "Projects & tasks", False),
        SectionInfo("assistant", "AI assistant", False),
        SectionInfo("alerts", "Alerts", False),
    )
}

SECTION_KEYS: frozenset[str] = frozenset(SECTION_CATALOG)


def valid_sections(keys: list[str]) -> list[str]:
    """Keep only known section keys, de-duplicated and in catalogue order."""
    chosen = {k for k in keys if k in SECTION_KEYS}
    return [k for k in SECTION_CATALOG if k in chosen]

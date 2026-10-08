"""Rule resolution: which category applies to an application or website for one employee.

Rules exist at five scopes. For a given employee only the rules of their company, permission role,
department, team and work profile apply, and the most specific scope wins
(work profile > team > department > role > company). Within one scope,
an exact website domain beats a parent domain (``docs.google.com`` over ``google.com``). Anything no rule
covers is *unclassified* — reported separately, never silently counted as productive or unproductive.
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from bson import ObjectId

from app.models.productivity import SCOPE_PRECEDENCE, Category, ProductivityRule, RuleKind, RuleScope

UNCLASSIFIED = "unclassified"

#: Browsers whose time is attributed to the visited website when a domain is known.
BROWSERS = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "vivaldi.exe",
        "iexplore.exe",
        "arc.exe",
    }
)


#: Part of every cached result's key: bump when classification or focus analysis changes.
ENGINE_VERSION = 1


@dataclass(frozen=True, slots=True)
class EmployeeContext:
    department_id: ObjectId | None
    team_id: ObjectId | None
    role: str | None
    profile_id: ObjectId | None = None


@dataclass(frozen=True, slots=True)
class Match:
    category: str  # a Category value or UNCLASSIFIED
    scope: str | None  # the scope of the rule that decided, if any
    pattern: str | None


def _applies(rule: ProductivityRule, ctx: EmployeeContext) -> bool:
    if rule.scope == RuleScope.COMPANY:
        return True
    if rule.scope == RuleScope.ROLE:
        return rule.role is not None and rule.role == ctx.role
    if rule.scope == RuleScope.DEPARTMENT:
        return rule.scope_id is not None and rule.scope_id == ctx.department_id
    if rule.scope == RuleScope.PROFILE:
        return rule.scope_id is not None and rule.scope_id == ctx.profile_id
    return rule.scope_id is not None and rule.scope_id == ctx.team_id


class RuleBook:
    """The rules that apply to one employee, ready for fast look-ups."""

    def __init__(self, rules: Iterable[ProductivityRule], ctx: EmployeeContext) -> None:
        self._apps: dict[str, tuple[int, ProductivityRule]] = {}
        self._sites: dict[str, tuple[int, ProductivityRule]] = {}
        for rule in rules:
            if not _applies(rule, ctx):
                continue
            target = self._apps if rule.kind == RuleKind.APP else self._sites
            rank = SCOPE_PRECEDENCE[rule.scope]
            current = target.get(rule.pattern)
            if current is None or rank > current[0]:
                target[rule.pattern] = (rank, rule)
        self._cache: dict[tuple[str, str], Match] = {}

    @functools.cached_property
    def fingerprint(self) -> str:
        """Identifies exactly which rules apply: equal fingerprints classify everything identically."""
        parts = sorted(
            f"{kind}|{pattern}|{rank}|{rule.category.value}|{rule.scope.value}"
            for kind, table in (("app", self._apps), ("site", self._sites))
            for pattern, (rank, rule) in table.items()
        )
        text = f"{ENGINE_VERSION}\n" + "\n".join(parts)
        return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:20]

    def app(self, app_id: str, app_name: str) -> Match:
        key = ("app", f"{app_id}|{app_name}")
        if key not in self._cache:
            found = [self._apps[p] for p in (app_id.lower(), app_name.lower()) if p in self._apps]
            self._cache[key] = self._best(found)
        return self._cache[key]

    def website(self, domain: str) -> Match:
        key = ("site", domain)
        if key not in self._cache:
            labels = domain.lower().split(".")
            best: tuple[int, int, ProductivityRule] | None = None
            # Every suffix of the host, most specific first: a.b.example.com, b.example.com, example.com, …
            for i in range(len(labels)):
                entry = self._sites.get(".".join(labels[i:]))
                if entry is None:
                    continue
                candidate = (entry[0], len(labels) - i, entry[1])  # scope precedence, then domain length
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
            self._cache[key] = (
                Match(best[2].category.value, best[2].scope.value, best[2].pattern)
                if best
                else Match(UNCLASSIFIED, None, None)
            )
        return self._cache[key]

    @staticmethod
    def _best(found: list[tuple[int, ProductivityRule]]) -> Match:
        if not found:
            return Match(UNCLASSIFIED, None, None)
        _, rule = max(found, key=lambda f: f[0])
        return Match(rule.category.value, rule.scope.value, rule.pattern)

    def classify(self, app_id: str, app_name: str, domain: str | None) -> Match:
        """Browser time with a known website follows the website's rule; everything else the app's rule."""
        if domain:
            return self.website(domain)
        return self.app(app_id, app_name)


#: A starting point administrators can load and then adjust. Deliberately small and uncontroversial;
#: whether e.g. chat or video sites are productive depends on the job, so they are left unclassified.
RECOMMENDED_RULES: tuple[tuple[RuleKind, str, Category], ...] = (
    (RuleKind.APP, "code.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "devenv.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "idea64.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "pycharm64.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "windowsterminal.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "excel.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "winword.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "powerpnt.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "figma.exe", Category.PRODUCTIVE),
    (RuleKind.APP, "outlook.exe", Category.NEUTRAL),
    (RuleKind.APP, "olk.exe", Category.NEUTRAL),
    (RuleKind.APP, "explorer.exe", Category.NEUTRAL),
    (RuleKind.APP, "steam.exe", Category.UNPRODUCTIVE),
    (RuleKind.APP, "epicgameslauncher.exe", Category.UNPRODUCTIVE),
    (RuleKind.WEBSITE, "github.com", Category.PRODUCTIVE),
    (RuleKind.WEBSITE, "stackoverflow.com", Category.PRODUCTIVE),
    (RuleKind.WEBSITE, "docs.google.com", Category.PRODUCTIVE),
    (RuleKind.WEBSITE, "netflix.com", Category.UNPRODUCTIVE),
    (RuleKind.WEBSITE, "twitch.tv", Category.UNPRODUCTIVE),
)


@dataclass(frozen=True, slots=True)
class ProfileTemplate:
    key: str
    name: str
    description: str
    rules: tuple[tuple[RuleKind, str, Category], ...]


_P, _N, _U = Category.PRODUCTIVE, Category.NEUTRAL, Category.UNPRODUCTIVE
_A, _W = RuleKind.APP, RuleKind.WEBSITE

#: Starting points for common job roles. The same application can mean different things for different
#: jobs (LinkedIn is prospecting for Sales, Figma is the job for Designers), which is why these exist.
#: They are copied into the workspace as ordinary profile rules and can be edited freely.
PROFILE_TEMPLATES: tuple[ProfileTemplate, ...] = (
    ProfileTemplate(
        "developer",
        "Developer",
        "Writing, reviewing and running code.",
        (
            (_A, "code.exe", _P),
            (_A, "devenv.exe", _P),
            (_A, "idea64.exe", _P),
            (_A, "pycharm64.exe", _P),
            (_A, "windowsterminal.exe", _P),
            (_A, "docker desktop.exe", _P),
            (_A, "postman.exe", _P),
            (_W, "github.com", _P),
            (_W, "gitlab.com", _P),
            (_W, "stackoverflow.com", _P),
            (_W, "developer.mozilla.org", _P),
            (_W, "figma.com", _N),
            (_W, "youtube.com", _N),
        ),
    ),
    ProfileTemplate(
        "designer",
        "Designer",
        "Visual, product and UX design.",
        (
            (_A, "figma.exe", _P),
            (_A, "photoshop.exe", _P),
            (_A, "illustrator.exe", _P),
            (_A, "afterfx.exe", _P),
            (_A, "blender.exe", _P),
            (_W, "figma.com", _P),
            (_W, "canva.com", _P),
            (_W, "dribbble.com", _P),
            (_W, "behance.net", _P),
            (_W, "unsplash.com", _P),
            (_W, "pinterest.com", _N),
            (_W, "youtube.com", _N),
        ),
    ),
    ProfileTemplate(
        "accountant",
        "Accountant",
        "Bookkeeping, reporting and finance operations.",
        (
            (_A, "excel.exe", _P),
            (_A, "qbw32.exe", _P),
            (_A, "qbw.exe", _P),
            (_A, "tally.exe", _P),
            (_A, "sage.exe", _P),
            (_W, "xero.com", _P),
            (_W, "quickbooks.intuit.com", _P),
            (_W, "app.sage.com", _P),
            (_W, "freshbooks.com", _P),
            (_W, "docs.google.com", _P),
            (_W, "youtube.com", _U),
        ),
    ),
    ProfileTemplate(
        "sales",
        "Sales",
        "Prospecting, calls and pipeline management.",
        (
            (_W, "salesforce.com", _P),
            (_W, "lightning.force.com", _P),
            (_W, "hubspot.com", _P),
            (_W, "pipedrive.com", _P),
            (_W, "linkedin.com", _P),
            (_W, "zoominfo.com", _P),
            (_A, "zoom.exe", _P),
            (_A, "ms-teams.exe", _P),
            (_A, "outlook.exe", _P),
            (_A, "olk.exe", _P),
            (_W, "youtube.com", _N),
        ),
    ),
    ProfileTemplate(
        "support",
        "Support",
        "Helping customers through tickets, chat and calls.",
        (
            (_W, "zendesk.com", _P),
            (_W, "freshdesk.com", _P),
            (_W, "intercom.com", _P),
            (_W, "app.intercom.com", _P),
            (_W, "helpscout.net", _P),
            (_A, "slack.exe", _P),
            (_A, "ms-teams.exe", _P),
            (_A, "outlook.exe", _P),
            (_A, "olk.exe", _P),
            (_W, "linkedin.com", _N),
            (_W, "youtube.com", _N),
        ),
    ),
)
TEMPLATES_BY_KEY = {t.key: t for t in PROFILE_TEMPLATES}

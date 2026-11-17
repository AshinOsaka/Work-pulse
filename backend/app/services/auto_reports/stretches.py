"""Continuous stretches of Unproductive time, for the "without a break" alert.

Built from the day's classified activity segments (the same rules as everywhere else). A stretch keeps going across
short gaps (`MAX_GAP`, e.g. a quick look elsewhere or a paused upload) and short non-Unproductive moments shorter than
`BREAK`; anything longer ends it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.services.auto_reports.figures import duration
from app.services.productivity.engine import Segment

#: Gaps up to this long don't end a stretch.
MAX_GAP = 120
#: Time in something not Unproductive at least this long ends a stretch.
BREAK = 60


@dataclass
class Stretch:
    start: datetime
    end: datetime
    seconds: float
    #: Seconds per app or website in the stretch.
    names: dict[str, float] = field(default_factory=dict)

    def where(self, limit: int = 3) -> str:
        ranked = sorted(self.names.items(), key=lambda kv: -kv[1])[:limit]
        return ", ".join(f"{name} ({duration(seconds)})" for name, seconds in ranked if seconds >= 30)


def unproductive_stretches(segments: list[Segment]) -> list[Stretch]:
    """Segments must already be classified (see `engine.classify_segments`); returns stretches oldest first."""
    out: list[Stretch] = []
    current: Stretch | None = None
    for seg in sorted(segments, key=lambda s: s.start):
        if seg.category == "unproductive":
            if current is not None and (seg.start - current.end).total_seconds() <= MAX_GAP:
                current.end = max(current.end, seg.end)
                current.seconds += seg.seconds
            else:
                if current is not None:
                    out.append(current)
                current = Stretch(seg.start, seg.end, seg.seconds)
            name = seg.domain or seg.app_name
            current.names[name] = current.names.get(name, 0.0) + seg.seconds
        elif current is not None and seg.seconds >= BREAK:
            out.append(current)
            current = None
    if current is not None:
        out.append(current)
    return out

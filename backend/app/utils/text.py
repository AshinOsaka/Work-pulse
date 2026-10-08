import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str, max_length: int = 48) -> str:
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", normalised.lower()).strip("-")
    return slug[:max_length].strip("-") or "workspace"


def normalise_email(value: str) -> str:
    return value.strip().lower()

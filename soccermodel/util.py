import math
import re
import unicodedata


def norm_name(name) -> str:
    """'Tim Stützle' -> 'timstutzle' so names match across sources."""
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def clean(o):
    """JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def r(v, d=1):
    try:
        x = float(v)
        return round(x, d) if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

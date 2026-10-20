"""Reads a Raycast `.rayconfig` export (reference/05 §5) and keeps what x-cast has a use for.

x-cast imports the general settings. Everything else in the file (quicklinks, snippets, notes,
clipboard history, extensions, ...) has no home here yet and is only counted in the report.
Encrypted exports need AES, which would add a dependency, so they are refused with a clear
message: export again without a password.

    rayconfig.py FILE        prints {"general": {...}, "skipped": {category: count}} as JSON
"""
import gzip
import json
import struct
import sys

MAGIC = b"RAYCFG3\n"
MAX_HEADER = 1 << 20

GENERAL_TYPES = {
    "windowMode": ("expanded", "compact"),
    "showFavoritesInCompactMode": bool,
    "windowPresentationMode": ("mouse-screen", "active-screen", "primary-screen"),
    "popToRootTimeout": int,
    "escapeKeyBehavior": ("pop-back-or-close", "close-and-pop-to-root"),
    "navigationBindings": ("emacs", "vim-motions"),
    "rootSearchSensitivity": ("low", "medium", "high"),
    "uiZoom": (int, float),
}


class RayconfigError(Exception):
    pass


def load(data):
    """The export's payload as a dict."""
    if data.startswith(MAGIC):
        (header_len,) = struct.unpack_from("<I", data, len(MAGIC))
        if not 1 <= header_len <= MAX_HEADER:
            raise RayconfigError("bad header length")
        start = len(MAGIC) + 4
        header = json.loads(gzip.decompress(data[start:start + header_len]))
        if header.get("encryption"):
            raise RayconfigError("this export is encrypted; export it again without a password")
        body = data[start + header_len:]
    elif data[:2] == b"\x1f\x8b":
        body = data
    else:
        raise RayconfigError("this is an encrypted classic export; export it again without a password")
    try:
        payload = json.loads(gzip.decompress(body))
    except (OSError, ValueError) as e:
        raise RayconfigError("the payload is not gzip JSON: %s" % e)
    if not isinstance(payload, dict):
        raise RayconfigError("the payload is not a JSON object")
    return payload


def _valid(key, value):
    rule = GENERAL_TYPES[key]
    if isinstance(rule, tuple) and rule and isinstance(rule[0], str):
        return value in rule
    if rule is bool:
        return isinstance(value, bool)
    if isinstance(value, bool):
        return False
    if rule is int:
        return isinstance(value, int)
    return isinstance(value, (int, float))


def general_settings(payload):
    settings = payload.get("settings")
    general = settings.get("general") if isinstance(settings, dict) else None
    if not isinstance(general, dict):
        return {}
    return {k: v for k, v in general.items() if k in GENERAL_TYPES and _valid(k, v)}


def skipped(payload):
    out = {}
    for category, value in payload.items():
        if category == "settings":
            continue
        if isinstance(value, dict):
            counts = [len(v) for v in value.values() if isinstance(v, list)]
            out[category] = sum(counts) if counts else 1
        elif isinstance(value, list):
            out[category] = len(value)
    return out


def summarize(path):
    with open(path, "rb") as f:
        payload = load(f.read())
    return {"general": general_settings(payload), "skipped": skipped(payload)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: rayconfig.py FILE")
    try:
        print(json.dumps(summarize(sys.argv[1])))
    except (OSError, RayconfigError) as e:
        sys.exit("x-cast: %s" % e)

"""Short hex ID generation and collision avoidance."""
import re
import secrets

_ID_RE = re.compile(r"^[0-9a-f]{4,}$")
_PREFIX_COUNTER = -1


def normalize_id(value: str) -> str:
    """Return a 5-character canonical form for supported IDs.

    Legacy 4-character IDs are treated as if prefixed with ``0``.
    """
    if len(value) == 4:
        return f"0{value}"
    return value


def _next_prefix(taken: set[str] | None = None) -> str:
    """Return the next 2-hex prefix for 5-character IDs."""
    global _PREFIX_COUNTER

    if taken:
        highest = max(int(normalize_id(node_id)[:2], 16) for node_id in taken)
        _PREFIX_COUNTER = max(_PREFIX_COUNTER, highest)

    _PREFIX_COUNTER = (_PREFIX_COUNTER + 1) % 256
    return f"{_PREFIX_COUNTER:02x}"


def new_id(length: int = 5, *, taken: set[str] | None = None) -> str:
    """Return a cryptographically random lowercase hex string of the given length.

    Uses ``secrets.token_hex`` which is backed by the OS CSPRNG — safer and
    more uniform than ``os.urandom(...).hex()[:n]``.
    """
    if length == 5:
        prefix = _next_prefix(taken)
        suffix = f"{secrets.randbelow(16**3):03x}"
        return f"{prefix}{suffix}"
    # token_hex(n) produces 2n hex chars; take exactly *length* of them.
    return secrets.token_hex((length + 1) // 2)[:length]


def is_valid_id(value: str) -> bool:
    """Return True if *value* looks like a valid zhar node ID."""
    return bool(_ID_RE.match(value))


def make_id_unique(candidate: str, taken: set[str], length: int = 5) -> str:
    """Return *candidate* unchanged if not in *taken*, otherwise generate a
    fresh ID that is not in *taken*."""
    if candidate not in taken:
        return candidate
    for _ in range(1000):
        fresh = new_id(length=length, taken=taken)
        if fresh not in taken:
            return fresh
    raise RuntimeError("Could not generate a unique ID after 1000 attempts")

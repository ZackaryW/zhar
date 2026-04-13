"""Short hex ID generation and collision avoidance."""
import re
import secrets

_ID_RE = re.compile(r"^[0-9a-f]{4,}$")


def new_id(length: int = 4) -> str:
    """Return a cryptographically random lowercase hex string of the given length.

    Uses ``secrets.token_hex`` which is backed by the OS CSPRNG — safer and
    more uniform than ``os.urandom(...).hex()[:n]``.
    """
    # token_hex(n) produces 2n hex chars; take exactly *length* of them.
    return secrets.token_hex((length + 1) // 2)[:length]


def is_valid_id(value: str) -> bool:
    """Return True if *value* looks like a valid zhar node ID."""
    return bool(_ID_RE.match(value))


def make_id_unique(candidate: str, taken: set[str], length: int = 4) -> str:
    """Return *candidate* unchanged if not in *taken*, otherwise generate a
    fresh ID that is not in *taken*."""
    if candidate not in taken:
        return candidate
    for _ in range(1000):
        fresh = new_id(length=length)
        if fresh not in taken:
            return fresh
    raise RuntimeError("Could not generate a unique ID after 1000 attempts")

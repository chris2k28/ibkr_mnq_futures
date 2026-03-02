from enum import Enum

class OrderType(int, Enum):
    """Enum for Order Types: LIMIT (0) or MARKET (1)."""
    LIMIT = 0
    MARKET = 1


class Exchange(str, Enum):
    """Enum for Supported Exchanges."""
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    CRYPTO = "CRYPTO"
    EMPTY = ""
    UNKNOWN = "UNKNOWN"


class PositionDirection(str, Enum):
    """Enum for Position Directions: LONG or SHORT."""
    SHORT = "short"
    LONG = "long"

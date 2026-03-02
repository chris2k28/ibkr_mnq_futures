from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class Position:
    """
    Represents a trading position in the portfolio.

    Attributes:
        id (int): Unique identifier for the position.
        ticker (str): Ticker symbol (e.g., MNQ).
        security (str): Security type (e.g., FUT).
        currency (str): Currency (e.g., USD).
        expiry (str): Expiry date for futures.
        quantity (float): Quantity of the position (positive for long, negative for short).
        avg_price (float): Average entry price.
        created_timestamp (pd.Timestamp): When the position was opened.
        closed_timestamp (Optional[pd.Timestamp]): When the position was closed.
        realized_pnl (float): Realized profit and loss for this position.
    """
    id: int
    ticker: str
    security: str
    currency: str
    expiry: str
    quantity: float
    avg_price: float
    created_timestamp: pd.Timestamp
    closed_timestamp: Optional[pd.Timestamp] = None
    realized_pnl: float = 0.0

    @property
    def direction(self) -> str:
        """Returns 'long' or 'short' based on quantity."""
        return "long" if self.quantity > 0 else "short"

    @property
    def is_closed(self) -> bool:
        """Checks if the position is closed."""
        return self.closed_timestamp is not None

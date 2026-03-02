from abc import ABC, abstractmethod
import pandas as pd

class AbstractStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    def __init__(self, config):
        """
        Initialize the strategy with configuration.

        Args:
            config (Configuration): The configuration object.
        """
        self.config = config

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> int:
        """
        Generate a trading signal based on historical data.

        Args:
            data (pd.DataFrame): Historical market data.

        Returns:
            int: 1 for BUY, -1 for SELL, 0 for HOLD.
        """
        pass

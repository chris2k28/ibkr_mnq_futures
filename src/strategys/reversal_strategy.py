from src.strategys.abstract_strategy import AbstractStrategy
from src.utilities.technical_analysis import TechnicalAnalysis
from src.utilities.enums import Signal
import logging
import pandas as pd
from src.configuration import Configuration


class ReversalStrategy(AbstractStrategy):
    """
    A reversal trading strategy based on Bollinger Bands and RSI.
    - Buy (Long) when price is below the lower Bollinger Band and RSI is oversold.
    - Sell (Short) when price is above the upper Bollinger Band and RSI is overbought.
    """

    @staticmethod
    def _is_hammer(row):
        """
        Detects a Hammer candle pattern.
        A Hammer has a small body near the top of the candle and a long lower wick.
        """
        body_size = abs(row['close'] - row['open'])
        candle_range = row['high'] - row['low']
        if candle_range == 0:
            return False

        lower_wick = min(row['open'], row['close']) - row['low']
        upper_wick = row['high'] - max(row['open'], row['close'])

        # Lower wick should be at least 2x the body, and upper wick should be very small
        return (lower_wick >= 2 * body_size and
                upper_wick <= 0.1 * candle_range and
                body_size > 0)

    @staticmethod
    def _is_shooting_star(row):
        """
        Detects a Shooting Star candle pattern.
        A Shooting Star has a small body near the bottom and a long upper wick.
        """
        body_size = abs(row['close'] - row['open'])
        candle_range = row['high'] - row['low']
        if candle_range == 0:
            return False

        upper_wick = row['high'] - max(row['open'], row['close'])
        lower_wick = min(row['open'], row['close']) - row['low']

        # Upper wick should be at least 2x the body, and lower wick should be very small
        return (upper_wick >= 2 * body_size and
                lower_wick <= 0.1 * candle_range and
                body_size > 0)

    @staticmethod
    def generate_signals(historical_data: pd.DataFrame, cfg: Configuration):
        logging.debug("Generating signals for Reversal strategy.")

        ta = TechnicalAnalysis(cfg)
        ta.calculate_indicators(historical_data)

        if len(historical_data) < 2:
            return Signal.HOLD

        last_row = historical_data.iloc[-1]

        # Reversal conditions (Bollinger Bands + RSI)
        is_oversold = (last_row['close'] < last_row['bb_lower'] and
                      last_row['rsi'] < cfg.rsi_oversold)

        is_overbought = (last_row['close'] > last_row['bb_upper'] and
                        last_row['rsi'] > cfg.rsi_overbought)

        # Candlestick patterns
        is_hammer = ReversalStrategy._is_hammer(last_row)
        is_shooting_star = ReversalStrategy._is_shooting_star(last_row)

        buy_signal = is_oversold and is_hammer
        sell_signal = is_overbought and is_shooting_star

        if buy_signal:
            logging.debug("ReversalStrategy: BUY signal generated.")
            return Signal.BUY
        elif sell_signal:
            logging.debug("ReversalStrategy: SELL signal generated.")
            return Signal.SELL
        else:
            logging.debug("ReversalStrategy: HOLD signal generated.")
            return Signal.HOLD

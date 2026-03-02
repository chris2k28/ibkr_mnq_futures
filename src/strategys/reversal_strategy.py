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
    def generate_signals(historical_data: pd.DataFrame, cfg: Configuration):
        logging.debug("Generating signals for Reversal strategy.")

        ta = TechnicalAnalysis(cfg)
        ta.calculate_indicators(historical_data)

        if len(historical_data) < 2:
            return Signal.HOLD

        last_row = historical_data.iloc[-1]

        # Reversal conditions
        buy_signal = (last_row['close'] < last_row['bb_lower'] and
                     last_row['rsi'] < cfg.rsi_oversold)

        sell_signal = (last_row['close'] > last_row['bb_upper'] and
                      last_row['rsi'] > cfg.rsi_overbought)

        if buy_signal:
            logging.debug("ReversalStrategy: BUY signal generated.")
            return Signal.BUY
        elif sell_signal:
            logging.debug("ReversalStrategy: SELL signal generated.")
            return Signal.SELL
        else:
            logging.debug("ReversalStrategy: HOLD signal generated.")
            return Signal.HOLD

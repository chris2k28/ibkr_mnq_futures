import pytest
import pandas as pd
from src.utilities.utils import trading_day_start_time_ts
from src.portfolio.portfolio_manager import PortfolioManager
import os
from src.configuration import Configuration
from unittest.mock import patch, MagicMock


class TestPortfolioManager:

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures before each test method."""
        self.cfg = Configuration(os.path.join(os.getcwd(), 
                                        "test", 
                                        "test_portfolio_manager", 
                                        "test_run.cfg"))
        self.mock_api = MagicMock()
        self.portfolio_manager = PortfolioManager(self.cfg, self.mock_api)

    def test_sync_with_api(self):
        """Test syncing state with the IBKR API"""

        # Mock open orders
        mock_order = MagicMock()
        mock_order.orderId = 123
        mock_order.parentId = 0

        self.mock_api.open_orders = {
            123: {'order': mock_order, 'contract': MagicMock()}
        }
        self.mock_api.position_data = {}
        
        self.portfolio_manager.sync_with_api()

        assert len(self.portfolio_manager.orders) == 1
        assert self.portfolio_manager.orders[0][0][0].orderId == 123
        self.mock_api.request_open_orders.assert_called_once()
        self.mock_api.get_positions.assert_called_once()

    def test_current_position_quantity(self):
        """Test getting current position quantity from API"""
        self.mock_api.position_data = {
            'MNQ': {'position': 5, 'avg_cost': 15000}
        }

        quantity = self.portfolio_manager.current_position_quantity()

        assert quantity == 5
        self.mock_api.get_positions.assert_called_once()



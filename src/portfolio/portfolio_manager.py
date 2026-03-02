import copy
from src.portfolio.position import Position
import pandas as pd
from typing import List, Dict, Optional
from ibapi.order import Order
from ibapi.contract import Contract
import os
from src.portfolio.position import Position
from src.api.ibkr_api import IBConnection
from src.configuration import Configuration
import logging
import time
from src.api.api_utils import get_current_contract, order_from_dict
from src.utilities.utils import trading_day_start_time_ts


class PortfolioManager:

    def __init__(self, config: Configuration, api: IBConnection):
        self.config = config
        self.api = api

        self.positions: List[Position] = []
        self.orders: List[List[(Order, bool)]] = []       #list of bracket orders (list of 3 orders). bool is for whether an order has been resubmitted when cancelled
        self.order_statuses: Dict[int, Dict] = {}          #order id -> order status

    def _get_order_status(self, order_id: int):
        """Get the order status for a given order id. Required to persist order
        statuses after the API or app disconnects. Check the API first, then check the local status. 
        Filled orders are not stored in the API after restart but unfilled are."""
        if order_id in self.api.order_statuses:
            return self.api.order_statuses[order_id]
        elif order_id in self.order_statuses:
            return self.order_statuses[order_id]
        else:
            logging.error(f"Order {order_id} not found in API or local order statuses")
            return None
        
    def update_positions(self):
        """Update the positions from the API."""
        logging.info(f"{self.__class__.__name__}: Updating positions from orders.")
        logging.debug(f"{self.__class__.__name__}: There are {self._total_orders()} orders")

        for bracket_order in self.orders:
            for order, _ in bracket_order:
                logging.info(f"Order: {str(order)}")
        
        self.api.request_open_orders()

        if len(self.orders) > 0:
            filled_count, cancelled_count, pending_count = self._get_order_status_count()
            logging.debug(f"Order statuses: {filled_count} filled, {cancelled_count} cancelled, {pending_count} pending")

        for bracket_idx, bracket_order in enumerate(self.orders):
            
            for order_idx, (order, already_handled) in enumerate(bracket_order):
                
                order_status = self._get_order_status(order.orderId)
                
                if order_status['status'] == 'Filled' and not already_handled:

                    order_details = self.api.get_open_order(order.orderId)
                    contract = order_details['contract']
                    
                    if order.orderType == 'MKT':

                        if len(self.positions) == 0:
                            logging.info(f"{order.action} order filled, creating new position.")

                            quantity = int(order.totalQuantity) if order.action == 'BUY' else -int(order.totalQuantity)

                            position = Position(
                            ticker=contract.symbol,
                            security=contract.secType,
                            currency=contract.currency,
                            expiry=contract.lastTradeDateOrContractMonth,
                            contract_id=contract.conId,
                            quantity=quantity,
                            avg_price=order_status['avg_fill_price'],
                            timezone=self.config.timezone,
                            )

                            self.positions.append(position)

                            self.orders[bracket_idx][order_idx] = (order, True)

                        else:
                            logging.info(f"{order.action} order filled, updating position.")

                            position = copy.deepcopy(self.positions[-1])

                            change_in_quantity = int(order.totalQuantity) if order.action == 'BUY' else -int(order.totalQuantity)
                            new_total_quantity = position.quantity + change_in_quantity

                            if new_total_quantity != 0:
                                avg_price = abs(position.quantity) * position.avg_price
                                avg_price += abs(change_in_quantity) * order_status['avg_fill_price']
                                avg_price /= (abs(position.quantity) + abs(change_in_quantity))
                            else:
                                avg_price = 0 # Position closed

                            position.quantity = new_total_quantity
                            position.avg_price = avg_price

                            self.orders[bracket_idx][order_idx] = (order, True)
                            
                            self.positions.append(position)
                    
                    elif order.orderType in ['STP', 'TRAIL', 'LMT']:

                        logging.info(f"{order.orderType} order filled, updating position.")

                        position = copy.deepcopy(self.positions[-1])

                        change_in_quantity = int(order.totalQuantity) if order.action == 'BUY' else -int(order.totalQuantity)
                        new_total_quantity = position.quantity + change_in_quantity

                        if new_total_quantity != 0:
                            avg_price = abs(position.quantity) * position.avg_price
                            avg_price += abs(change_in_quantity) * order_status['avg_fill_price']
                            avg_price /= (abs(position.quantity) + abs(change_in_quantity))
                        else:
                            avg_price = 0 # Position closed

                        position.quantity = new_total_quantity
                        position.avg_price = avg_price

                        self.orders[bracket_idx][order_idx] = (order, True)

                        self.positions.append(position)

                    else:

                        raise TypeError(f"Order type {order.orderType} with action {order.action} is not supported.")
        
        msg = f"{self.__class__.__name__}: Finished updating positions from orders."
        msg += f" Currently {len(self.positions)} position(s)."

        logging.info(msg)
        if len(self.positions) > 0:
            for position in self.positions:
                logging.info(str(position))

    def daily_pnl(self):
        """Get the daily PnL from the IBKR API."""
        pnl_data = self.api.get_account_pnl()
        if pnl_data:
            return pnl_data['realized_pnl']
        return 0

    def place_bracket_order(self, action: str = "BUY", contract: Contract = None):
        """Place a bracket order"""
        logging.debug(f"Placing {action} bracket order.")
        contract = self.get_current_contract() if contract is None else contract

        mid_price = self.api.get_latest_mid_price(contract)

        if mid_price is None:
            logging.error(f"No mid price found for contract {contract.symbol}. Cannot place bracket order.")
            return
        
        if action == "BUY":
            stop_loss_price = mid_price - (self.config.stop_loss_ticks * self.config.mnq_tick_size)
            take_profit_limit_price = mid_price + (self.config.take_profit_ticks * self.config.mnq_tick_size)
        else: # SELL
            stop_loss_price = mid_price + (self.config.stop_loss_ticks * self.config.mnq_tick_size)
            take_profit_limit_price = mid_price - (self.config.take_profit_ticks * self.config.mnq_tick_size)

        stop_loss_price = round(stop_loss_price/self.config.mnq_tick_size) * self.config.mnq_tick_size
        take_profit_limit_price = round(take_profit_limit_price/self.config.mnq_tick_size) * self.config.mnq_tick_size

        logging.debug(f"STP price: {stop_loss_price}, LMT price: {take_profit_limit_price}")

        bracket = self.api.create_bracket_order(
            action,
            self.config.number_of_contracts, 
            take_profit_limit_price, 
            stop_loss_price,
            trailing_stop_ticks=(self.config.trailing_stop_ticks * self.config.mnq_tick_size) if self.config.use_trailing_stop else None)
        
        self.api.place_orders(bracket, contract)

        if all(self._get_order_status(order.orderId) for order in bracket):
            # This means all orders were accepted by the API
            self._handle_successful_bracket_order(bracket)
        else:
            self._handle_failed_bracket_order(bracket)

    def _handle_successful_bracket_order(self, bracket: List[Order]):
        """Handle a successful bracket order. This is called when all orders were accepted by the API."""
        logging.info("All orders were accepted by the API.")
        self.orders.append(list(zip(bracket, [False] * len(bracket))))

        self.update_positions()

    def _handle_failed_bracket_order(self, bracket: List[Order]):
        """Handle a failed bracket order. This is called when the order is not in the order status dictionary."""
        logging.error("Order callbacks not received for all orders.")
        logging.warning(f"Pausing for {self.config.timeout} seconds before rechecking order statuses.")

        time.sleep(self.config.timeout)

        logging.warning("Checking order statuses again after pause.")

        for order in bracket:
            logging.info(f"Order {order.orderId} status - {self.api.order_statuses[order.orderId]}")

        # If order statuses are now received, then we can process positions
        if all(self._get_order_status(order.orderId) for order in bracket):

            self._handle_successful_bracket_order(bracket)

        else:

            logging.error("Order callbacks still not received for all orders. Handling cancellations")

            mkt_order, lmt_order, stop_order = bracket[0], bracket[1], bracket[2]
            if (mkt_order.orderType != 'MKT' or
                lmt_order.orderType != 'LMT' or
                stop_order.orderType not in ['STP', 'TRAIL']):
                logging.error(f"Bracket order not in expected order. Please check.")

            if not self.api.order_statuses[mkt_order.orderId]:
                logging.error(f"MKT order {mkt_order.orderId} is not in the order status dictionary.")
                logging.warning(f"Cancelling MKT order {mkt_order.orderId}")
                self.api.cancel_order(mkt_order.orderId)

                if self.api.order_statuses[mkt_order.orderId]['status'] == "Cancelled":
                    logging.info(f"MKT order {mkt_order.orderId} was cancelled successfully.")
                    logging.info(f"Now cancelling LMT and {stop_order.orderType} orders")

                    self.api.cancel_order(lmt_order.orderId)
                    self.api.cancel_order(stop_order.orderId)

                    logging.info(f"LMT order {lmt_order.orderId} status: {self.api.order_statuses[lmt_order.orderId]['status']}")
                    logging.info(f"{stop_order.orderType} order {stop_order.orderId} status: {self.api.order_statuses[stop_order.orderId]['status']}")

                    if (self.api.order_statuses[lmt_order.orderId]['status'] != "Cancelled" or
                        self.api.order_statuses[stop_order.orderId]['status'] != "Cancelled"):
                        logging.error(f"LMT or {stop_order.orderType} order was not cancelled. Please check.")
                        return

            else:
                logging.info(f"MKT order {mkt_order.orderId} status received: {self.api.order_statuses[mkt_order.orderId]['status']}")

            if not self.api.order_statuses[lmt_order.orderId] or not self.api.order_statuses[stop_order.orderId]:
                # If we're here it means that the MKT order was accepted by the API but not the brackets.
                logging.error(f"LMT order status: {self.api.order_statuses[lmt_order.orderId]}")
                logging.error(f"{stop_order.orderType} order status: {self.api.order_statuses[stop_order.orderId]}")
                
                #Try to cancel the brackets
                self.api.cancel_order(lmt_order.orderId)
                self.api.cancel_order(stop_order.orderId)

                if self.api.order_statuses[lmt_order.orderId]['status'] == "Cancelled":
                    logging.info(f"LMT order {lmt_order.orderId} was cancelled successfully.")
                else:
                    logging.error(f"Could not cancel LMT order. Status: {self.api.order_statuses[lmt_order.orderId]['status']}")

                if self.api.order_statuses[stop_order.orderId]['status'] == "Cancelled":
                    logging.info(f"{stop_order.orderType} order {stop_order.orderId} was cancelled successfully.")
                else:
                    logging.error(f"Could not cancel {stop_order.orderType} order. Status: {self.api.order_statuses[stop_order.orderId]['status']}")

                # Handle case where brackets are cancelled but the market order is filled
                if (self.api.order_statuses[mkt_order.orderId]['status'] == "Filled" and
                    self.api.order_statuses[lmt_order.orderId]['status'] == "Cancelled" and
                    self.api.order_statuses[stop_order.orderId]['status'] == "Cancelled"):

                    logging.warning(f"Market order {mkt_order.orderId} was filled while brackets were cancelled.")
                    logging.warning(f"Closing open position.")

                    #get order details for market order
                    self.api.request_open_orders()
                    
                    order_details = self.api.get_open_order(mkt_order.orderId)
                    contract = order_details['contract']

                    # Place the order
                    new_order_id, _ = self.api.place_market_order(contract, "SELL", mkt_order.totalQuantity)
                    new_order_details = self.api.get_open_order(new_order_id)
                    
                    self.orders.append([(new_order_details['order'], False)])

                    self.update_positions()

                else:
                    logging.error(f"Order statuses not received for all orders. Undefined behavior.")

            else:
                
                logging.error(f"Should not be here. Order statuses received for all orders but not handled.")
                for order in bracket:
                    logging.info(f"Order {order.orderId} status - {self.api.order_statuses[order.orderId]}")

    def has_pending_orders(self):
        """Check if there are any pending orders from the IBKR API."""
        self.api.request_open_orders()
        for order_id, order_info in self.api.open_orders.items():
            status = self.api.get_order_status(order_id)
            if status and status['status'] not in ['Filled', 'Cancelled', 'Inactive']:
                return True
        return False

    def current_position_quantity(self):
        """Get the current position quantity for the ticker from the IBKR API."""
        self.api.get_positions()
        if self.config.ticker in self.api.position_data:
            return self.api.position_data[self.config.ticker]['position']
        return 0

    def check_cancelled_market_order(self):
        """Check for cancelled market orders and resubmit them if required."""
        logging.debug("Checking for cancelled market orders.")

        found_cancelled_order = False

        for bracket_order in self.orders:

            for order, already_resubmitted in bracket_order:

                order_status = self._get_order_status(order.orderId)['status']

                if (not already_resubmitted and 
                    order.orderType == 'MKT' and
                    order_status == "Cancelled"):

                    logging.warning(f"Order type: {order.orderType}, id:{order.orderId}, was cancelled.")
                    found_cancelled_order = True

                    if self.config.resubmit_cancelled_order:

                        logging.info(f"Resubmitting order type: {order.orderType}, id:{order.orderId}.")
                        already_resubmitted = True

                        order_details = self.api.get_open_order(order.orderId)

                        self.place_bracket_order(order_details['contract'])

                    else:
                        logging.info(f"Not resubmitting cancelled order type: {order.orderType}, id:{order.orderId}.")

        if not found_cancelled_order:
            logging.debug("No cancelled orders found.")
        
    def get_current_contract(self): 
        """Get the current contract"""
        return get_current_contract(
            self.config.ticker,
            self.config.exchange,
            self.config.currency,
            self.config.roll_contract_days_before,
            self.config.timezone)
    
    def _get_order_status_count(self):
        filled_count = 0
        cancelled_count = 0
        total_orders = 0
        
        for bracket_order in self.orders:

            total_orders += len(bracket_order)

            for order, _ in bracket_order:

                status = self._get_order_status(order.orderId)['status']
                if status == 'Filled':
                    filled_count += 1
                elif status == 'Cancelled':
                    cancelled_count += 1

        pending_count = total_orders - filled_count - cancelled_count
        return filled_count, cancelled_count, pending_count

    def cancel_all_orders(self):
        """Cancel all unfilled and non-cancelled orders."""
        logging.info("Cancelling all active orders.")
        
        for bracket_order in self.orders:

            for order, _ in bracket_order:
            
                order_status = self._get_order_status(order.orderId)
                
                if order_status['status'] not in ['Filled', 'Cancelled']:
                    logging.info(f"Cancelling order {order.orderId} of type {order.orderType}")
                    self.api.cancel_order(order.orderId)

    def close_all_positions(self):
        """Close all open positions by issuing market orders."""
        logging.info("Closing all open positions.")

        if len(self.positions) == 0:
            logging.info("No positions to close.")
            return
        
        # The last position entry is the current position
        position = self.positions[-1]

        if position.quantity != 0:
            logging.info(f"Closing position for {position.ticker} with quantity {position.quantity}")
            matching_position = self.api.get_matching_position(position)

            if matching_position is None:
                msg = f"Position {position.ticker} with quantity {position.quantity} not found in IBKR. Cannot close."
                logging.error(msg)
                return

            native_contract_quantity = int(matching_position['position'])
            if abs(position.quantity) > abs(native_contract_quantity):
                msg = f"Trying to close position {position.ticker} with quantity {position.quantity}."
                msg += f" Only {native_contract_quantity} contracts are found on IBKR. Cannot close local position."
                logging.error(msg)
                return
            
            contract = Contract()
            contract.symbol = position.ticker
            contract.secType = position.security
            contract.currency = position.currency
            contract.exchange = self.config.exchange
            contract.lastTradeDateOrContractMonth = position.expiry

            # Place the order
            action = "SELL" if position.quantity > 0 else "BUY"
            order_id, _ = self.api.place_market_order(contract, action, abs(position.quantity))
            order_details = self.api.get_open_order(order_id)
            self.orders.append([(order_details['order'], False)])

            self.update_positions()

        else:
            msg = f"Position {position.ticker} with quantity {position.quantity}. No positions to close"
            logging.info(msg)
    
    def _total_orders(self):
        return sum(len(bracket_order) for bracket_order in self.orders)
    
    def clear_orders_statuses_positions(self):
        """Clear all orders and positions. This is called when the trading day
        has ended and we need to clear the orders and positions for the next day.
        """
        logging.debug("Clearing orders, order statuses and positions.")
        self.orders = []
        self.positions = []
        self.order_statuses = {}

    def sync_with_api(self):
        """Sync the internal state with the IBKR API."""
        logging.info("PortfolioManager: Syncing state with IBKR API.")

        # Initialize account PnL subscription
        self.api.subscribe_account_pnl()

        # Request all open orders
        self.api.request_open_orders()

        # Group open orders into brackets if they share a parent ID
        # Note: This is a simplified reconstruction as we don't have the full original bracket structure
        open_orders_by_parent = {}
        for order_id, order_info in self.api.open_orders.items():
            order = order_info['order']
            parent_id = order.parentId if order.parentId != 0 else order.orderId

            if parent_id not in open_orders_by_parent:
                open_orders_by_parent[parent_id] = []
            open_orders_by_parent[parent_id].append((order, False))

        self.orders = list(open_orders_by_parent.values())

        # Request current positions
        self.api.get_positions()

        logging.info(f"PortfolioManager: Synced {len(self.orders)} bracket(s) and {len(self.api.position_data)} position(s) from IBKR.")




import logging
from ibapi.contract import Contract
from src.configuration import Configuration

def create_contract(config: Configuration) -> Contract:
    """
    Create an IBKR Contract object based on the provided configuration.

    Args:
        config (Configuration): The configuration object containing ticker, security type, exchange, etc.

    Returns:
        Contract: A populated IBKR Contract object.
    """
    contract = Contract()
    contract.symbol = config.ticker
    contract.secType = config.security
    contract.exchange = config.exchange
    contract.currency = config.currency
    
    if config.security == "FUT":
        contract.lastTradeDateOrContractMonth = config.expiry

    return contract

def log_order_status(order_id, status, filled, remaining, avg_fill_price, last_fill_price, parent_id, why_held, mkt_cap_price):
    """
    Log the status of an order.

    Args:
        order_id (int): The ID of the order.
        status (str): The current status of the order.
        filled (float): The number of shares filled.
        remaining (float): The number of shares remaining.
        avg_fill_price (float): The average fill price.
        last_fill_price (float): The last fill price.
        parent_id (int): The parent order ID.
        why_held (str): The reason why the order is held.
        mkt_cap_price (float): The market cap price.
    """
    logging.info(f"Order {order_id} status: {status}, filled: {filled}, remaining: {remaining}, avg price: {avg_fill_price}")

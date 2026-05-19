import logging
from typing import Dict, Any, Optional
from kiteconnect import KiteConnect
from app.services.kite_data import kite_data

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """
    Handles real-time order execution via Zerodha Kite API.
    """
    def __init__(self):
        pass

    @property
    def kite(self) -> Optional[KiteConnect]:
        if kite_data.is_ready and kite_data._kite:
            return kite_data._kite
        return None

    def place_order(self, symbol: str, transaction_type: str, quantity: int, order_type: str = "MARKET", price: float = 0.0, product: str = "MIS") -> Dict[str, Any]:
        """
        Places an order on Kite.
        transaction_type: "BUY" or "SELL"
        order_type: "MARKET", "LIMIT", "SL", "SL-M"
        product: "MIS" (Intraday) or "CNC" (Delivery)
        """
        if not self.kite:
            logger.error("❌ ExecutionEngine: Kite is not connected.")
            return {"status": "error", "message": "Kite not connected"}

        # Format symbol for Kite (remove .NS, etc.)
        tradingsymbol = symbol.replace(".NS", "").replace(".BO", "").upper()

        try:
            logger.info(f"🚀 Placing {transaction_type} order for {quantity} {tradingsymbol} ({order_type})")
            
            # Translate to Kite constants
            t_type = self.kite.TRANSACTION_TYPE_BUY if transaction_type.upper() == "BUY" else self.kite.TRANSACTION_TYPE_SELL
            o_type = getattr(self.kite, f"ORDER_TYPE_{order_type.replace('-', '').upper()}", self.kite.ORDER_TYPE_MARKET)
            p_type = self.kite.PRODUCT_MIS if product.upper() == "MIS" else self.kite.PRODUCT_CNC

            order_params = {
                "tradingsymbol": tradingsymbol,
                "exchange": self.kite.EXCHANGE_NSE,
                "transaction_type": t_type,
                "quantity": quantity,
                "order_type": o_type,
                "product": p_type,
                "validity": self.kite.VALIDITY_DAY
            }

            if order_type in ["LIMIT", "SL"]:
                order_params["price"] = price

            if order_type in ["SL", "SL-M"]:
                order_params["trigger_price"] = price

            order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **order_params)
            
            logger.info(f"✅ Order placed successfully! ID: {order_id}")
            return {"status": "success", "order_id": order_id}

        except Exception as e:
            logger.error(f"❌ Failed to place order for {tradingsymbol}: {e}")
            return {"status": "error", "message": str(e)}

    def modify_order(self, order_id: str, new_price: float = 0.0, new_trigger_price: float = 0.0) -> Dict[str, Any]:
        """Modifies an existing pending order (e.g., trailing stop loss)."""
        if not self.kite:
            return {"status": "error", "message": "Kite not connected"}

        try:
            params = {}
            if new_price > 0:
                params["price"] = new_price
            if new_trigger_price > 0:
                params["trigger_price"] = new_trigger_price

            self.kite.modify_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id,
                **params
            )
            logger.info(f"✅ Order {order_id} modified.")
            return {"status": "success", "order_id": order_id}
        except Exception as e:
            logger.error(f"❌ Failed to modify order {order_id}: {e}")
            return {"status": "error", "message": str(e)}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancels a pending order."""
        if not self.kite:
            return {"status": "error", "message": "Kite not connected"}

        try:
            self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id
            )
            logger.info(f"✅ Order {order_id} cancelled.")
            return {"status": "success", "order_id": order_id}
        except Exception as e:
            logger.error(f"❌ Failed to cancel order {order_id}: {e}")
            return {"status": "error", "message": str(e)}

execution_engine = ExecutionEngine()

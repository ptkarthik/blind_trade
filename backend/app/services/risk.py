class RiskManager:
    def __init__(self, max_risk_per_trade: float = 0.01):
        self.max_risk_per_trade = max_risk_per_trade  # 1% of capital

    def validate_trade(self, signal: dict, account_balance: float) -> dict:
        """
        Validate a trade signal and calculate position size.
        """
        entry = signal.get("entry")
        stop_loss = signal.get("stop_loss")
        
        if not entry or not stop_loss:
            return {"valid": False, "reason": "Missing price levels"}

        risk_per_share = abs(entry - stop_loss)
        
        # Rule: Stop Loss shouldn't be too tight (< 0.5%) or too wide (> 5%) for intraday
        sl_pct = (risk_per_share / entry) * 100
        if sl_pct < 0.5 or sl_pct > 5.0:
             return {"valid": False, "reason": f"Stop Loss {sl_pct:.2f}% is outside allowed range"}

        # Calculate Quantity
        risk_amount = account_balance * self.max_risk_per_trade
        quantity = int(risk_amount // risk_per_share)

        if quantity == 0:
             return {"valid": False, "reason": "Risk too high for account size"}

        return {
            "valid": True,
            "quantity": quantity,
            "risk_amount": risk_amount,
            "stop_loss_pct": sl_pct
        }

risk_manager = RiskManager()

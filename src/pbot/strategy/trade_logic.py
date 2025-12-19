# /root/pbot/src/pbot/strategy/trade_logic.py
import pandas as pd

def get_pbot_signal(analysis_result: dict, params: dict):
    """
    Entscheidet basierend auf dem Predictor-Score, ob getradet wird.
    Ersetzt die alte SMC-Logik.
    """
    if not analysis_result:
        return None, None

    score = analysis_result.get("score", 0)
    is_choppy = analysis_result.get("is_choppy", False)
    current_price = analysis_result.get("close")
    
    # Filter-Einstellungen laden
    strategy_params = params.get('strategy', {})
    min_score_strength = strategy_params.get('min_score', 0.5) 
    allow_choppy = strategy_params.get('allow_choppy', False)

    # 1. Choppy Filter (Seitwärtsphase)
    if is_choppy and not allow_choppy:
        return None, None

    # 2. Signal Bestimmung
    signal_side = None
    
    # LONG
    if score > min_score_strength:
        signal_side = "buy"
        
    # SHORT
    elif score < -min_score_strength:
        signal_side = "sell"

    if signal_side:
        return signal_side, current_price

    return None, None

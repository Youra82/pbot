# /root/pbot/src/pbot/analysis/backtester.py
# VERSION: SYNCHRONIZED-V7 (Structure Protection Added)
import os
import pandas as pd
import numpy as np
import json
import sys
import math
import ta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.utils.exchange import Exchange
from pbot.strategy.predictor_engine import PredictorEngine
from pbot.strategy.trade_logic import get_pbot_signal

secrets_cache = None

def load_data(symbol, timeframe, start_date_str, end_date_str):
    """Lädt Daten aus dem Cache oder von der API."""
    global secrets_cache
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    cache_dir = os.path.join(data_dir, 'cache')
    symbol_filename = symbol.replace('/', '-').replace(':', '-')
    cache_file = os.path.join(cache_dir, f"{symbol_filename}_{timeframe}.csv")

    try:
        if not os.path.exists(data_dir): os.makedirs(data_dir)
        os.makedirs(cache_dir, exist_ok=True)
    except OSError: pass

    if os.path.exists(cache_file):
        try:
            data = pd.read_csv(cache_file, index_col='timestamp', parse_dates=True)
            data.index = pd.to_datetime(data.index, utc=True)
            data_start = data.index.min(); data_end = data.index.max()
            req_start = pd.to_datetime(start_date_str, utc=True); req_end = pd.to_datetime(end_date_str, utc=True)
            if data_start <= req_start and data_end >= req_end:
                return data.loc[req_start:req_end]
        except Exception:
            try: os.remove(cache_file)
            except: pass

    print(f"⬇️ Lade {symbol} ({timeframe}) von Bitget API...")
    try:
        if secrets_cache is None:
            sec_path = os.path.join(PROJECT_ROOT, 'secret.json')
            if not os.path.exists(sec_path): return pd.DataFrame()
            with open(sec_path, "r") as f: secrets_cache = json.load(f)

        acc_key = 'pbot' if 'pbot' in secrets_cache else 'titanbot'
        if acc_key not in secrets_cache: return pd.DataFrame()

        api_setup = secrets_cache[acc_key][0]
        exchange = Exchange(api_setup)
        if not exchange.markets: return pd.DataFrame()

        full_data = exchange.fetch_historical_ohlcv(symbol, timeframe, start_date_str, end_date_str)
        if not full_data.empty:
            full_data.to_csv(cache_file)
            req_start_dt = pd.to_datetime(start_date_str, utc=True)
            req_end_dt = pd.to_datetime(end_date_str, utc=True)
            return full_data.loc[req_start_dt:req_end_dt]
        return pd.DataFrame()
    except Exception as e:
        print(f"Fehler: {e}")
        return pd.DataFrame()

def run_pbot_backtest(data, strategy_params, risk_params, start_capital=1000, verbose=False):
    """
    Backtest Logik - EXAKT wie Portfolio Simulator.
    """
    if data.empty or len(data) < 50:
        return {"total_pnl_pct": -100, "trades_count": 0, "win_rate": 0, "max_drawdown_pct": 1.0, "end_capital": start_capital}

    # 1. Indikatoren
    engine = PredictorEngine(strategy_params)
    data = engine.calculate_indicators(data.copy())
    
    # NEU: Vorherige Hochs/Tiefs für Structure Protection berechnen
    data['prev_high'] = data['high'].shift(1)
    data['prev_low'] = data['low'].shift(1)

    # 2. Setup
    equity = start_capital
    peak_equity = start_capital
    max_drawdown_pct = 0.0
    trades_count = 0
    wins_count = 0

    position = None
    pending_order = None # {side, atr}

    # Risk Parameter
    risk_reward_ratio = float(risk_params.get('risk_reward_ratio', 2.0))
    
    # --- SICHERHEITS-BREMSE BACKTESTER ---
    raw_risk = float(risk_params.get('risk_per_trade_pct', 1.0))
    risk_per_trade_pct = min(raw_risk, 2.0) / 100.0 # Max 2%
    # -------------------------------------
    
    leverage = int(risk_params.get('leverage', 10))
    atr_multiplier_sl = float(risk_params.get('atr_multiplier_sl', 2.0))
    min_sl_pct = float(risk_params.get('min_sl_pct', 0.5)) / 100.0

    # Trailing
    act_rr = float(risk_params.get('trailing_stop_activation_rr', 1.5))
    cb_rate = float(risk_params.get('trailing_stop_callback_rate_pct', 0.5)) / 100.0

    fee_pct = 0.06 / 100
    min_notional = 5.0
    absolute_max_notional_value = 1000000

    records = data.to_dict('records')

    for i, current_candle in enumerate(records):
        if equity <= 0: break

        # --- A) PENDING ORDER (Entry @ Open) ---
        if not position and pending_order:
            entry_price = current_candle['open']

            # ATR vom Signal-Zeitpunkt (gestern)
            atr_val = pending_order['atr']
            signal_side = pending_order['side']

            sl_dist = max(atr_val * atr_multiplier_sl, entry_price * min_sl_pct)
            
            # NEU: Structure Check (gegen vorherige Kerze)
            # pending_order wurde in Kerze i-1 erstellt. 
            # Die "letzte geschlossene Kerze" zum Zeitpunkt des Entrys (Open von i) ist also i-1.
            # Wir haben prev_high/prev_low bereits in current_candle (durch shift)
            
            # current_candle['prev_low'] entspricht dem Low von Kerze i-1
            if signal_side == 'buy' and not pd.isna(current_candle['prev_low']):
                struct_dist = entry_price - current_candle['prev_low']
                sl_dist = max(sl_dist, struct_dist)
            elif signal_side == 'sell' and not pd.isna(current_candle['prev_high']):
                struct_dist = current_candle['prev_high'] - entry_price
                sl_dist = max(sl_dist, struct_dist)

            if sl_dist > 0:
                risk_usd = equity * risk_per_trade_pct
                sl_dist_pct = sl_dist / entry_price

                if sl_dist_pct > 0:
                    raw_notional = risk_usd / sl_dist_pct
                    max_lev_notional = equity * 10
                    final_notional = min(raw_notional, max_lev_notional, absolute_max_notional_value)

                    margin_req = math.ceil((final_notional / leverage) * 100) / 100

                    if final_notional >= min_notional and margin_req <= equity:
                        sl_price = entry_price - sl_dist if signal_side == 'buy' else entry_price + sl_dist
                        tp_price = entry_price + (sl_dist * risk_reward_ratio) if signal_side == 'buy' else entry_price - (sl_dist * risk_reward_ratio)

                        act_price = entry_price + (sl_dist * act_rr) if signal_side == 'buy' else entry_price - (sl_dist * act_rr)

                        position = {
                            'side': signal_side, 'entry_price': entry_price,
                            'stop_loss': sl_price, 'take_profit': tp_price,
                            'notional': final_notional,
                            'trailing_active': False, 'activation_price': act_price,
                            'peak_price': entry_price, 'callback_rate': cb_rate
                        }

            pending_order = None

        # --- B) EXIT (High/Low) ---
        if position:
            exit_price = None

            # Trailing Logic Update
            if position['side'] == 'long':
                if not position['trailing_active'] and current_candle['high'] >= position['activation_price']:
                    position['trailing_active'] = True
                if position['trailing_active']:
                    position['peak_price'] = max(position['peak_price'], current_candle['high'])
                    new_sl = position['peak_price'] * (1 - position['callback_rate'])
                    position['stop_loss'] = max(position['stop_loss'], new_sl)

                # Check Hits (Conservative: Check SL first)
                if current_candle['low'] <= position['stop_loss']:
                    exit_price = position['stop_loss']
                elif not position['trailing_active'] and current_candle['high'] >= position['take_profit']:
                    exit_price = position['take_profit']

            else: # Short
                if not position['trailing_active'] and current_candle['low'] <= position['activation_price']:
                    position['trailing_active'] = True
                if position['trailing_active']:
                    position['peak_price'] = min(position['peak_price'], current_candle['low'])
                    new_sl = position['peak_price'] * (1 + position['callback_rate'])
                    position['stop_loss'] = min(position['stop_loss'], new_sl)

                # Check Hits
                if current_candle['high'] >= position['stop_loss']:
                    exit_price = position['stop_loss']
                elif not position['trailing_active'] and current_candle['low'] <= position['take_profit']:
                    exit_price = position['take_profit']

            if exit_price:
                pnl_pct = (exit_price / position['entry_price'] - 1) if position['side'] == 'long' else (1 - exit_price / position['entry_price'])
                pnl_usd = position['notional'] * pnl_pct
                costs = position['notional'] * fee_pct * 2

                equity += (pnl_usd - costs)

                if (pnl_usd - costs) > 0: wins_count += 1
                trades_count += 1
                position = None

                # Drawdown Check
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                max_drawdown_pct = max(max_drawdown_pct, dd)

        # --- C) SIGNAL (Close) ---
        if not position and not pending_order:
            # Engine Logic
            score = engine.get_score(current_candle, None)

            is_choppy = False
            if engine.use_adx:
                if current_candle.get('adx', 0) < engine.adx_threshold: is_choppy = True

            analysis_result = {
                'score': score,
                'is_choppy': is_choppy,
                'close': current_candle['close'],
                'atr': current_candle.get('atr', current_candle['close']*0.01)
            }

            # WICHTIG: Wrapper für params, damit trade_logic 'strategy' findet
            signal_side, _ = get_pbot_signal(analysis_result, {'strategy': strategy_params})

            if signal_side:
                pending_order = {
                    'side': signal_side,
                    'atr': analysis_result['atr']
                }

    final_pnl = ((equity - start_capital) / start_capital) * 100 if start_capital > 0 else 0
    win_rate = (wins_count / trades_count * 100) if trades_count > 0 else 0

    return {
        "total_pnl_pct": final_pnl,
        "trades_count": trades_count,
        "win_rate": win_rate,
        "max_drawdown_pct": max_drawdown_pct,
        "end_capital": equity
    }

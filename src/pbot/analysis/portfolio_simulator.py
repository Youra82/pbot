# /root/pbot/src/pbot/analysis/portfolio_simulator.py
# VERSION: SYNCHRONIZED-V4 (Structure Protection Added)
import pandas as pd
import numpy as np
from tqdm import tqdm
import sys
import os
import ta
import math
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.strategy.predictor_engine import PredictorEngine
from pbot.strategy.trade_logic import get_pbot_signal
from pbot.analysis.backtester import load_data
from pbot.utils.timeframe_utils import determine_htf

def run_portfolio_simulation(start_capital, strategies_data, start_date, end_date):
    """
    Führt eine chronologische Portfolio-Simulation durch.
    LOGIK: 1:1 Synchronisiert mit Backtester (Realistic-V1).
    """
    print("\n--- Starte Portfolio-Simulation (PBot)... ---")

    # --- 1. Vorbereitung ---
    print("1/3: Berechne Indikatoren...")
    valid_strategies = {}
    all_timestamps = set()
    htf_cache = {}

    for key, strat in tqdm(strategies_data.items(), desc="Vorbereitung"):
        if 'data' not in strat or strat['data'].empty: continue
        try:
            strat_params = strat.get('smc_params', {})
            risk_params = strat.get('risk_params', {})
            strat_params.setdefault('length', 14)
            strat_params.setdefault('rsi_weight', 1.5)

            engine = PredictorEngine(strat_params)
            df = strat['data'].copy()
            df = engine.calculate_indicators(df)
            
            # NEU: Vorherige Hochs/Tiefs für Structure Protection
            df['prev_high'] = df['high'].shift(1)
            df['prev_low'] = df['low'].shift(1)

            # HTF
            symbol = strat['symbol']
            htf = strat.get('htf') or determine_htf(strat['timeframe'])
            htf_df = pd.DataFrame()
            if htf and htf != strat['timeframe']:
                cache_key = f"{symbol}_{htf}"
                if cache_key in htf_cache: htf_df = htf_cache[cache_key]
                else:
                    try:
                        htf_raw = load_data(symbol, htf, start_date, end_date)
                        if not htf_raw.empty:
                            htf_raw['ema_mtf'] = ta.trend.ema_indicator(htf_raw['close'], window=strat_params['length'] * 2)
                            htf_df = htf_raw
                            htf_cache[cache_key] = htf_df
                    except: pass

            valid_strategies[key] = {
                'data': df, 'htf_data': htf_df, 'engine': engine,
                'params': {'strategy': strat_params, 'risk': risk_params},
                'symbol': symbol
            }
            all_timestamps.update(df.index)
        except Exception as e: print(f"Fehler bei {key}: {e}")

    if not valid_strategies: return None
    sorted_timestamps = sorted(list(all_timestamps))
    print(f"-> {len(sorted_timestamps)} Zeitstempel.")

    # --- 2. Simulation ---
    print("2/3: Simuliere Handelsverlauf...")

    equity = start_capital
    peak_equity = start_capital
    max_drawdown_pct = 0.0
    max_drawdown_date = None
    min_equity_ever = start_capital
    liquidation_date = None

    open_positions = {}
    pending_orders = {} # Key: Strategy_Key -> {side, atr_from_signal}
    trade_history = []
    equity_curve = []

    # Konstanten
    fee_pct = 0.06 / 100
    max_allowed_effective_leverage = 10
    absolute_max_notional_value = 1000000
    min_notional = 5.0

    for ts in tqdm(sorted_timestamps, desc="Simuliere"):
        if liquidation_date: break

        used_margin = sum(p['margin_used'] for p in open_positions.values())
        free_equity_at_start = equity - used_margin

        # --- A) PENDING ORDERS (Entry @ Open) ---
        keys_to_delete_pending = []
        for key, order_info in pending_orders.items():
            strat_pack = valid_strategies.get(key)
            if not strat_pack or ts not in strat_pack['data'].index: continue

            current_candle = strat_pack['data'].loc[ts]
            entry_price = current_candle['open'] # STRICTLY OPEN

            risk = strat_pack['params']['risk']
            leverage = int(risk.get('leverage', 10))

            # WICHTIG: ATR kommt aus dem SIGNAL (gestern), nicht von heute!
            atr = order_info['atr']

            atr_mult = risk.get('atr_multiplier_sl', 2.0)
            min_sl = risk.get('min_sl_pct', 0.5) / 100.0
            sl_dist = max(atr * atr_mult, entry_price * min_sl)
            
            # NEU: Structure Check
            signal_side = order_info['side']
            if signal_side == 'buy' and not pd.isna(current_candle['prev_low']):
                struct_dist = entry_price - current_candle['prev_low']
                sl_dist = max(sl_dist, struct_dist)
            elif signal_side == 'sell' and not pd.isna(current_candle['prev_high']):
                struct_dist = current_candle['prev_high'] - entry_price
                sl_dist = max(sl_dist, struct_dist)

            if sl_dist <= 0:
                keys_to_delete_pending.append(key); continue

            # Sizing
            # --- SICHERHEITS-BREMSE SIMULATION ---
            raw_risk = float(risk.get('risk_per_trade_pct', 1.0))
            # Hard Cap auf 2%
            effective_risk = min(raw_risk, 2.0) 
            risk_pct = effective_risk / 100.0
            # -------------------------------------
            
            risk_usd = equity * risk_pct

            sl_dist_pct = sl_dist / entry_price
            if sl_dist_pct == 0:
                keys_to_delete_pending.append(key); continue

            raw_notional = risk_usd / sl_dist_pct
            max_lev_notional = equity * max_allowed_effective_leverage
            final_notional = min(raw_notional, max_lev_notional, absolute_max_notional_value)

            if final_notional < min_notional:
                keys_to_delete_pending.append(key); continue

            margin_req = math.ceil((final_notional / leverage) * 100) / 100

            if margin_req > free_equity_at_start:
                keys_to_delete_pending.append(key); continue

            # Setup Position
            rr = risk.get('risk_reward_ratio', 2.0)
            sl_price = entry_price - sl_dist if signal_side == 'buy' else entry_price + sl_dist
            tp_price = entry_price + (sl_dist * rr) if signal_side == 'buy' else entry_price - (sl_dist * rr)

            act_rr = risk.get('trailing_stop_activation_rr', 1.5)
            act_price = entry_price + (sl_dist * act_rr) if signal_side == 'buy' else entry_price - (sl_dist * act_rr)
            cb_rate = risk.get('trailing_stop_callback_rate_pct', 0.5) / 100.0

            open_positions[key] = {
                'side': signal_side,
                'entry_price': entry_price,
                'stop_loss': sl_price,
                'take_profit': tp_price,
                'notional_value': final_notional,
                'margin_used': margin_req,
                'trailing_active': False,
                'activation_price': act_price,
                'peak_price': entry_price,
                'callback_rate': cb_rate,
                'last_known_price': entry_price
            }

            free_equity_at_start -= margin_req
            keys_to_delete_pending.append(key)

        for k in keys_to_delete_pending:
            if k in pending_orders: del pending_orders[k]


        # --- B) EXIT (High/Low) ---
        current_total_equity = equity
        unrealized_pnl = 0
        positions_to_close = []

        for key, pos in open_positions.items():
            strat_pack = valid_strategies.get(key)
            if ts not in strat_pack['data'].index:
                if pos.get('last_known_price'):
                    pnl_mult = 1 if pos['side'] == 'long' else -1
                    unrealized_pnl += pos['notional_value'] * (pos['last_known_price'] / pos['entry_price'] - 1) * pnl_mult
                continue

            current_candle = strat_pack['data'].loc[ts]
            pos['last_known_price'] = current_candle['close']

            exit_price = None

            # Trailing Logic
            if pos['side'] == 'long':
                if not pos['trailing_active'] and current_candle['high'] >= pos['activation_price']:
                    pos['trailing_active'] = True
                if pos['trailing_active']:
                    pos['peak_price'] = max(pos['peak_price'], current_candle['high'])
                    new_sl = pos['peak_price'] * (1 - pos['callback_rate'])
                    pos['stop_loss'] = max(pos['stop_loss'], new_sl)
            else:
                if not pos['trailing_active'] and current_candle['low'] <= pos['activation_price']:
                    pos['trailing_active'] = True
                if pos['trailing_active']:
                    pos['peak_price'] = min(pos['peak_price'], current_candle['low'])
                    new_sl = pos['peak_price'] * (1 + pos['callback_rate'])
                    pos['stop_loss'] = min(pos['stop_loss'], new_sl)

            # Hit Check (Conservative order: SL first)
            if pos['side'] == 'long':
                if current_candle['low'] <= pos['stop_loss']: exit_price = pos['stop_loss']
                elif not pos['trailing_active'] and current_candle['high'] >= pos['take_profit']: exit_price = pos['take_profit']
            else:
                if current_candle['high'] >= pos['stop_loss']: exit_price = pos['stop_loss']
                elif not pos['trailing_active'] and current_candle['low'] <= pos['take_profit']: exit_price = pos['take_profit']

            if exit_price:
                pnl_pct = (exit_price / pos['entry_price'] - 1) if pos['side'] == 'long' else (1 - exit_price / pos['entry_price'])
                pnl_usd = pos['notional_value'] * pnl_pct
                total_fees = pos['notional_value'] * fee_pct * 2
                equity += (pnl_usd - total_fees)

                trade_history.append({'strategy_key': key, 'symbol': strat_pack['symbol'], 'pnl': (pnl_usd - total_fees), 'timestamp': ts})
                positions_to_close.append(key)
            else:
                pnl_mult = 1 if pos['side'] == 'long' else -1
                unrealized_pnl += pos['notional_value'] * (current_candle['close'] / pos['entry_price'] - 1) * pnl_mult

        for key in positions_to_close:
            del open_positions[key]


        # --- C) SIGNAL GENERATION (Close) ---
        for key, strat_pack in valid_strategies.items():
            if key in open_positions or key in pending_orders: continue
            if ts not in strat_pack['data'].index: continue

            current_candle = strat_pack['data'].loc[ts]
            engine = strat_pack['engine']
            params = strat_pack['params']

            # Simple MTF Check
            mtf_bullish = None
            
            score = engine.get_score(current_candle, mtf_bullish)

            is_choppy = False
            if engine.use_adx:
                if current_candle.get('adx', 0) < engine.adx_threshold: is_choppy = True

            # Helper dict for signal logic
            analysis_result = {
                "score": score,
                "is_choppy": is_choppy,
                "close": current_candle['close'],
                # ATR hier ist für den Signal-Zeitpunkt (Close)
                "atr": current_candle.get('atr', current_candle['close']*0.01)
            }
            signal_side, _ = get_pbot_signal(analysis_result, params)

            if signal_side:
                # WICHTIG: Wir speichern die ATR vom Signal-Zeitpunkt!
                pending_orders[key] = {
                    'side': signal_side,
                    'timestamp_signal': ts,
                    'atr': analysis_result['atr'] 
                }

        # --- D) Stats ---
        current_total_equity = equity + unrealized_pnl
        equity_curve.append({'timestamp': ts, 'equity': current_total_equity})

        peak_equity = max(peak_equity, current_total_equity)
        if peak_equity > 0:
            dd = (peak_equity - current_total_equity) / peak_equity
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd
                max_drawdown_date = ts

        min_equity_ever = min(min_equity_ever, current_total_equity)
        if current_total_equity <= 0 and not liquidation_date: liquidation_date = ts

    # --- 3. Report ---
    print("3/3: Analyse abgeschlossen.")
    final_equity = equity_curve[-1]['equity'] if equity_curve else start_capital
    total_pnl_pct = ((final_equity / start_capital) - 1) * 100
    wins = sum(1 for t in trade_history if t['pnl'] > 0)
    win_rate = (wins / len(trade_history) * 100) if trade_history else 0

    trade_df = pd.DataFrame(trade_history)
    pnl_per_strategy = pd.DataFrame()
    trades_per_strategy = pd.DataFrame()
    if not trade_df.empty:
        pnl_per_strategy = trade_df.groupby('strategy_key')['pnl'].sum().reset_index()
        trades_per_strategy = trade_df.groupby('strategy_key').size().reset_index(name='trades')

    equity_df = pd.DataFrame(equity_curve)
    if not equity_df.empty:
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown_pct'] = ((equity_df['peak'] - equity_df['equity']) / equity_df['peak'].replace(0, np.nan)).fillna(0)
        equity_df.set_index('timestamp', inplace=True, drop=False)

    return {
        "start_capital": start_capital, "end_capital": final_equity, "total_pnl_pct": total_pnl_pct,
        "trade_count": len(trade_history), "win_rate": win_rate, "max_drawdown_pct": max_drawdown_pct * 100,
        "max_drawdown_date": max_drawdown_date, "min_equity": min_equity_ever, "liquidation_date": liquidation_date,
        "pnl_per_strategy": pnl_per_strategy, "trades_per_strategy": trades_per_strategy, "equity_curve": equity_df
    }

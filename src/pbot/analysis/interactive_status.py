#!/usr/bin/env python3
"""
Interactive Charts fuer PBot - Predictor-Strategie
Zeigt Candlestick-Chart mit Trade-Signalen (Entry/Exit Long/Short) + Equity Curve
"""

import os
import sys
import json
import logging
import warnings
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.analysis.backtester import load_data
from pbot.strategy.predictor_engine import PredictorEngine
from pbot.strategy.trade_logic import get_pbot_signal

logger = logging.getLogger('interactive_status')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Config-Auswahl
# ---------------------------------------------------------------------------

def get_config_files():
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy', 'configs')
    if not os.path.exists(configs_dir):
        return []
    return sorted(
        [(f, os.path.join(configs_dir, f))
         for f in os.listdir(configs_dir)
         if f.startswith('config_') and f.endswith('.json')]
    )


def select_configs():
    configs = get_config_files()
    if not configs:
        logger.error("Keine Konfigurationsdateien gefunden!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Verfuegbare Konfigurationen:")
    print("=" * 60)
    for idx, (filename, _) in enumerate(configs, 1):
        clean = filename.replace('config_', '').replace('.json', '')
        print(f"{idx:2d}) {clean}")
    print("=" * 60)
    print("\nWaehle Konfiguration(en) zum Anzeigen:")
    print("  Einzeln:  z.B. '1' oder '5'")
    print("  Mehrfach: z.B. '1,3,5' oder '1 3 5'")

    selection = input("\nAuswahl: ").strip()
    selected = []
    for part in selection.replace(',', ' ').split():
        try:
            idx = int(part)
            if 1 <= idx <= len(configs):
                selected.append(configs[idx - 1])
            else:
                logger.warning(f"Index {idx} ausserhalb des Bereichs")
        except ValueError:
            logger.warning(f"Ungueltige Eingabe: {part}")

    if not selected:
        logger.error("Keine gueltigen Konfigurationen gewaehlt!")
        sys.exit(1)

    return selected


# ---------------------------------------------------------------------------
# Trades aus Backtest extrahieren (fuer Chart-Markierungen)
# ---------------------------------------------------------------------------

def extract_trades(df: pd.DataFrame, strategy_params: dict, risk_params: dict,
                   start_capital: float = 1000) -> list:
    """
    Fuehrt einen simulierten Backtest durch und gibt Trades als Liste zurueck.
    Jeder Trade: {side, entry_time, entry_price, exit_time, exit_price, pnl_usd}
    """
    trades = []
    try:
        engine = PredictorEngine(strategy_params)
        data = engine.calculate_indicators(df.copy())
        data['prev_high'] = data['high'].shift(1)
        data['prev_low'] = data['low'].shift(1)

        equity = start_capital
        position = None
        pending_order = None

        risk_reward_ratio = float(risk_params.get('risk_reward_ratio', 2.0))
        raw_risk = float(risk_params.get('risk_per_trade_pct', 1.0))
        risk_per_trade_pct = min(raw_risk, 2.0) / 100.0
        leverage = int(risk_params.get('leverage', 10))
        atr_multiplier_sl = float(risk_params.get('atr_multiplier_sl', 2.0))
        min_sl_pct = float(risk_params.get('min_sl_pct', 0.5)) / 100.0
        act_rr = float(risk_params.get('trailing_stop_activation_rr', 1.5))
        cb_rate = float(risk_params.get('trailing_stop_callback_rate_pct', 0.5)) / 100.0
        fee_pct = 0.06 / 100
        base_slippage_pct = 0.05 / 100
        min_notional = 5.0
        absolute_max_notional_value = 1_000_000

        timestamps = list(data.index)
        records = data.to_dict('records')

        for i, current_candle in enumerate(records):
            if equity <= 0:
                break
            ts = timestamps[i]

            # A) PENDING ORDER (Entry @ Open)
            if not position and pending_order:
                raw_entry = current_candle['open']
                if pending_order['side'] == 'buy':
                    entry_price = raw_entry * (1 + base_slippage_pct)
                else:
                    entry_price = raw_entry * (1 - base_slippage_pct)

                atr_val = pending_order['atr']
                signal_side = pending_order['side']
                sl_dist = max(atr_val * atr_multiplier_sl, entry_price * min_sl_pct)

                prev_low = current_candle.get('prev_low', float('nan'))
                prev_high = current_candle.get('prev_high', float('nan'))

                if signal_side == 'buy' and not pd.isna(prev_low):
                    sl_dist = max(sl_dist, entry_price - prev_low)
                elif signal_side == 'sell' and not pd.isna(prev_high):
                    sl_dist = max(sl_dist, prev_high - entry_price)

                if sl_dist > 0:
                    sl_dist_pct = sl_dist / entry_price
                    if sl_dist_pct > 0:
                        risk_usd = equity * risk_per_trade_pct
                        raw_notional = risk_usd / sl_dist_pct
                        max_lev_notional = equity * 10
                        final_notional = min(raw_notional, max_lev_notional, absolute_max_notional_value)
                        margin_req = math.ceil((final_notional / leverage) * 100) / 100

                        if final_notional >= min_notional and margin_req <= equity:
                            sl_price = entry_price - sl_dist if signal_side == 'buy' else entry_price + sl_dist
                            tp_price = entry_price + (sl_dist * risk_reward_ratio) if signal_side == 'buy' else entry_price - (sl_dist * risk_reward_ratio)
                            act_price = entry_price + (sl_dist * act_rr) if signal_side == 'buy' else entry_price - (sl_dist * act_rr)
                            side = 'long' if signal_side == 'buy' else 'short'
                            position = {
                                'side': side,
                                'entry_price': entry_price,
                                'stop_loss': sl_price,
                                'take_profit': tp_price,
                                'notional': final_notional,
                                'trailing_active': False,
                                'activation_price': act_price,
                                'peak_price': entry_price,
                                'callback_rate': cb_rate,
                                'entry_time': ts,
                            }
                pending_order = None

            # B) EXIT (High/Low)
            if position:
                exit_price = None
                if position['side'] == 'long':
                    if not position['trailing_active'] and current_candle['high'] >= position['activation_price']:
                        position['trailing_active'] = True
                    if position['trailing_active']:
                        position['peak_price'] = max(position['peak_price'], current_candle['high'])
                        new_sl = position['peak_price'] * (1 - position['callback_rate'])
                        position['stop_loss'] = max(position['stop_loss'], new_sl)
                    if current_candle['low'] <= position['stop_loss']:
                        exit_price = position['stop_loss']
                    elif not position['trailing_active'] and current_candle['high'] >= position['take_profit']:
                        exit_price = position['take_profit']
                else:
                    if not position['trailing_active'] and current_candle['low'] <= position['activation_price']:
                        position['trailing_active'] = True
                    if position['trailing_active']:
                        position['peak_price'] = min(position['peak_price'], current_candle['low'])
                        new_sl = position['peak_price'] * (1 + position['callback_rate'])
                        position['stop_loss'] = min(position['stop_loss'], new_sl)
                    if current_candle['high'] >= position['stop_loss']:
                        exit_price = position['stop_loss']
                    elif not position['trailing_active'] and current_candle['low'] <= position['take_profit']:
                        exit_price = position['take_profit']

                if exit_price:
                    if position['side'] == 'long':
                        exit_price = exit_price * (1 - base_slippage_pct)
                    else:
                        exit_price = exit_price * (1 + base_slippage_pct)

                    pnl_pct = (exit_price / position['entry_price'] - 1) if position['side'] == 'long' \
                        else (1 - exit_price / position['entry_price'])
                    pnl_usd = position['notional'] * pnl_pct - position['notional'] * fee_pct * 2
                    equity += pnl_usd

                    trades.append({
                        'side': position['side'],
                        'entry_time': position['entry_time'],
                        'entry_price': position['entry_price'],
                        'exit_time': ts,
                        'exit_price': exit_price,
                        'pnl_usd': pnl_usd,
                    })
                    position = None

            # C) SIGNAL (Close)
            if not position and not pending_order:
                score, _ = engine.get_score(current_candle, None)
                is_choppy = False
                if engine.use_adx:
                    if current_candle.get('adx', 0) < engine.adx_threshold:
                        is_choppy = True
                analysis_result = {
                    'score': score,
                    'is_choppy': is_choppy,
                    'close': current_candle['close'],
                    'atr': current_candle.get('atr', current_candle['close'] * 0.01),
                }
                signal_side, _ = get_pbot_signal(analysis_result, {'strategy': strategy_params})
                if signal_side:
                    pending_order = {
                        'side': signal_side,
                        'atr': analysis_result['atr'],
                    }

    except Exception as e:
        logger.warning(f"Fehler bei Trade-Extraktion: {e}")
        import traceback
        traceback.print_exc()

    return trades


# ---------------------------------------------------------------------------
# Equity Curve aus Trades aufbauen
# ---------------------------------------------------------------------------

def build_equity_curve(df: pd.DataFrame, trades: list, start_capital: float) -> pd.DataFrame:
    equity = start_capital
    trade_events = sorted(
        [{'time': pd.to_datetime(t['exit_time']), 'pnl_usd': t['pnl_usd']}
         for t in trades],
        key=lambda x: x['time']
    )

    equity_data = []
    t_idx = 0
    for ts, _ in df.iterrows():
        while t_idx < len(trade_events) and trade_events[t_idx]['time'] <= ts:
            equity += trade_events[t_idx]['pnl_usd']
            t_idx += 1
        equity_data.append({'timestamp': ts, 'equity': equity})

    eq_df = pd.DataFrame(equity_data).set_index('timestamp')
    return eq_df


# ---------------------------------------------------------------------------
# Interaktiver Chart (Plotly)
# ---------------------------------------------------------------------------

def create_interactive_chart(symbol, timeframe, df, trades, equity_df,
                              start_date, end_date, window=None,
                              start_capital=1000):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        logger.error("plotly nicht installiert. Bitte: pip install plotly")
        return None

    # Zeitraum-Filter
    if window:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window)
        df = df[df.index >= cutoff].copy()
    if start_date:
        df = df[df.index >= pd.to_datetime(start_date, utc=True)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date, utc=True)]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # ===== CANDLESTICKS =====
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        name='OHLC',
        increasing_line_color='#16a34a',
        decreasing_line_color='#dc2626',
        showlegend=True,
    ), secondary_y=False)

    # ===== TRADE-SIGNALE =====
    entry_long_x, entry_long_y = [], []
    exit_long_x,  exit_long_y  = [], []
    entry_short_x, entry_short_y = [], []
    exit_short_x,  exit_short_y  = [], []

    for t in trades:
        et = pd.to_datetime(t['entry_time'])
        xt = pd.to_datetime(t['exit_time'])
        if t['side'] == 'long':
            entry_long_x.append(et);  entry_long_y.append(t['entry_price'])
            exit_long_x.append(xt);   exit_long_y.append(t['exit_price'])
        else:
            entry_short_x.append(et); entry_short_y.append(t['entry_price'])
            exit_short_x.append(xt);  exit_short_y.append(t['exit_price'])

    if entry_long_x:
        fig.add_trace(go.Scatter(
            x=entry_long_x, y=entry_long_y, mode='markers',
            marker=dict(color='#16a34a', symbol='triangle-up', size=14,
                        line=dict(width=1.2, color='#0f5132')),
            name='Entry Long', showlegend=True,
        ), secondary_y=False)

    if exit_long_x:
        fig.add_trace(go.Scatter(
            x=exit_long_x, y=exit_long_y, mode='markers',
            marker=dict(color='#22d3ee', symbol='circle', size=12,
                        line=dict(width=1.1, color='#0e7490')),
            name='Exit Long', showlegend=True,
        ), secondary_y=False)

    if entry_short_x:
        fig.add_trace(go.Scatter(
            x=entry_short_x, y=entry_short_y, mode='markers',
            marker=dict(color='#f59e0b', symbol='triangle-down', size=14,
                        line=dict(width=1.2, color='#92400e')),
            name='Entry Short', showlegend=True,
        ), secondary_y=False)

    if exit_short_x:
        fig.add_trace(go.Scatter(
            x=exit_short_x, y=exit_short_y, mode='markers',
            marker=dict(color='#ef4444', symbol='diamond', size=12,
                        line=dict(width=1.1, color='#7f1d1d')),
            name='Exit Short', showlegend=True,
        ), secondary_y=False)

    # ===== EQUITY CURVE (rechte Y-Achse) =====
    if not equity_df.empty and 'equity' in equity_df.columns:
        fig.add_trace(go.Scatter(
            x=equity_df.index, y=equity_df['equity'],
            name='Kontostand',
            line=dict(color='#2563eb', width=2),
            opacity=0.75,
            showlegend=True,
        ), secondary_y=True)

    # ===== TITEL (alle Stats aus extract_trades + equity_df) =====
    end_cap = equity_df['equity'].iloc[-1] if not equity_df.empty else start_capital
    pnl_pct = ((end_cap - start_capital) / start_capital * 100) if start_capital > 0 else 0

    trades_count = len(trades)
    wins = sum(1 for t in trades if t['pnl_usd'] > 0)
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0.0

    max_dd_pct = 0.0
    if not equity_df.empty and 'equity' in equity_df.columns:
        peak = equity_df['equity'].cummax()
        dd = (equity_df['equity'] - peak) / peak
        max_dd_pct = abs(dd.min()) * 100

    title_text = (
        f"{symbol} {timeframe} - PBot Predictor | "
        f"Start: ${start_capital:.0f} | "
        f"End: ${end_cap:.0f} | "
        f"PnL: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}% | "
        f"Max DD: {max_dd_pct:.2f}% | "
        f"Trades: {trades_count} | "
        f"Win Rate: {win_rate:.1f}%"
    )

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=13), x=0.5, xanchor='center'),
        height=720,
        hovermode='x unified',
        template='plotly_white',
        dragmode='zoom',
        xaxis=dict(rangeslider=dict(visible=True), fixedrange=False),
        yaxis=dict(fixedrange=False),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
        showlegend=True,
    )
    fig.update_yaxes(title_text='Preis (USDT)', secondary_y=False)
    fig.update_yaxes(title_text='Kontostand (USDT)', secondary_y=True)

    return fig


# ---------------------------------------------------------------------------
# Haupt-Funktion
# ---------------------------------------------------------------------------

def main():
    selected_configs = select_configs()

    print("\n" + "=" * 60)
    print("Chart-Optionen:")
    print("=" * 60)
    start_date = input("Startdatum (YYYY-MM-DD) [leer=beliebig]:  ").strip() or None
    end_date   = input("Enddatum   (YYYY-MM-DD) [leer=heute]:     ").strip() or None
    cap_input  = input("Startkapital (USDT)     [Standard: 1000]: ").strip()
    start_capital = int(cap_input) if cap_input.isdigit() else 1000
    win_input  = input("Letzten N Tage anzeigen [leer=alle]:      ").strip()
    window     = int(win_input) if win_input.isdigit() else None
    tg_input   = input("Telegram versenden? (j/n) [Standard: n]:  ").strip().lower()
    send_telegram = tg_input in ['j', 'y', 'yes']

    try:
        with open(os.path.join(PROJECT_ROOT, 'secret.json'), 'r') as f:
            secrets = json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Laden von secret.json: {e}")
        sys.exit(1)

    telegram_config = secrets.get('telegram', {})

    end_date_load = end_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    start_date_load = start_date or (
        datetime.now(timezone.utc) - timedelta(days=365)
    ).strftime('%Y-%m-%d')

    for filename, filepath in selected_configs:
        try:
            logger.info(f"\nVerarbeite {filename}...")

            with open(filepath, 'r') as f:
                config = json.load(f)

            symbol    = config['market']['symbol']
            timeframe = config['market']['timeframe']

            strategy_params = {**config.get('strategy', {}),
                               'symbol': symbol, 'timeframe': timeframe,
                               'htf': config['market'].get('htf')}
            risk_params = config.get('risk', {})

            logger.info(f"Lade OHLCV-Daten fuer {symbol} {timeframe}...")
            df = load_data(symbol, timeframe, start_date_load, end_date_load)
            if df is None or df.empty:
                logger.warning(f"Keine Daten fuer {symbol} {timeframe}")
                continue

            # Trades extrahieren
            logger.info("Extrahiere Trades fuer Chart-Markierungen...")
            trades = extract_trades(df.copy(), strategy_params, risk_params, start_capital)
            logger.info(f"  {len(trades)} Trades gefunden")

            # Equity Curve
            equity_df = build_equity_curve(df, trades, start_capital)

            # Chart erstellen
            logger.info("Erstelle interaktiven Chart...")
            fig = create_interactive_chart(
                symbol, timeframe, df,
                trades, equity_df,
                start_date, end_date,
                window, start_capital,
            )

            if fig is None:
                continue

            safe_name = f"{symbol.replace('/', '_').replace(':', '_')}_{timeframe}"
            output_file = f"/tmp/pbot_{safe_name}.html"
            fig.write_html(output_file)
            logger.info(f"\u2705 Chart gespeichert: {output_file}")

            if send_telegram and telegram_config.get('bot_token'):
                try:
                    from pbot.utils.telegram import send_document
                    send_document(
                        telegram_config['bot_token'],
                        telegram_config['chat_id'],
                        output_file,
                        caption=f"PBot Chart: {symbol} {timeframe}",
                    )
                    logger.info("\u2705 Chart via Telegram versendet")
                except Exception as e:
                    logger.warning(f"Telegram-Versand fehlgeschlagen: {e}")

        except Exception as e:
            logger.error(f"Fehler bei {filename}: {e}", exc_info=True)
            continue

    logger.info("\n\u2705 Alle Charts generiert!")


if __name__ == '__main__':
    main()

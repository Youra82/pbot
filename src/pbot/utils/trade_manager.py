# /root/pbot/src/pbot/utils/trade_manager.py
import json
import logging
import os
import time
from datetime import datetime, timedelta

import ccxt
import numpy as np
import pandas as pd
import ta
import math

from pbot.strategy.predictor_engine import PredictorEngine
from pbot.strategy.trade_logic import get_pbot_signal
from pbot.utils.exchange import Exchange
from pbot.utils.telegram import send_message
from pbot.utils.timeframe_utils import determine_htf

# --------------------------------------------------------------------------- #
# Pfade
# --------------------------------------------------------------------------- #
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
ARTIFACTS_PATH = os.path.join(PROJECT_ROOT, 'artifacts')
DB_PATH = os.path.join(ARTIFACTS_PATH, 'db')
TRADE_LOCK_FILE = os.path.join(DB_PATH, 'trade_lock.json')


# --------------------------------------------------------------------------- #
# Trade-Lock-Hilfsfunktionen
# --------------------------------------------------------------------------- #
def load_or_create_trade_lock():
    os.makedirs(DB_PATH, exist_ok=True)
    if os.path.exists(TRADE_LOCK_FILE):
        with open(TRADE_LOCK_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_trade_lock(trade_lock):
    with open(TRADE_LOCK_FILE, 'w') as f:
        json.dump(trade_lock, f, indent=4)

def is_trade_locked(symbol_timeframe):
    trade_lock = load_or_create_trade_lock()
    lock_time_str = trade_lock.get(symbol_timeframe)
    if lock_time_str:
        lock_time = datetime.strptime(lock_time_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < lock_time:
            return True
    return False

def set_trade_lock(symbol_timeframe, lock_duration_minutes=60):
    lock_time = datetime.now() + timedelta(minutes=lock_duration_minutes)
    trade_lock = load_or_create_trade_lock()
    trade_lock[symbol_timeframe] = lock_time.strftime("%Y-%m-%d %H:%M:%S")
    save_trade_lock(trade_lock)

# --------------------------------------------------------------------------- #
# Housekeeper
# --------------------------------------------------------------------------- #
def housekeeper_routine(exchange, symbol, logger):
    try:
        logger.info(f"Housekeeper: Starte Aufräumroutine für {symbol}...")
        exchange.cancel_all_orders_for_symbol(symbol)
        time.sleep(2)

        position = exchange.fetch_open_positions(symbol)
        if position:
            pos_info = position[0]
            close_side = 'sell' if pos_info['side'] == 'long' else 'buy'
            logger.warning(f"Housekeeper: Schließe verwaiste Position ({pos_info['side']} {pos_info['contracts']})...")
            exchange.create_market_order(symbol, close_side, float(pos_info['contracts']), {'reduceOnly': True})
            time.sleep(3)

        if exchange.fetch_open_positions(symbol):
            logger.error("Housekeeper: Position konnte nicht geschlossen werden!")
        else:
            logger.info(f"Housekeeper: {symbol} ist jetzt sauber.")
        return True
    except Exception as e:
        logger.error(f"Housekeeper-Fehler: {e}", exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Hauptfunktion: Trade öffnen + SL/TP/TSL setzen (PBot Version)
# --------------------------------------------------------------------------- #
def check_and_open_new_position(exchange, model, scaler, params, telegram_config, logger):
    symbol = params['market']['symbol']
    timeframe = params['market']['timeframe']
    htf = params['market']['htf']
    symbol_timeframe = f"{symbol.replace('/', '-')}_{timeframe}"

    if is_trade_locked(symbol_timeframe):
        logger.info(f"Trade für {symbol_timeframe} gesperrt – überspringe.")
        return

    try:
        # --------------------------------------------------- #
        # 1. Daten holen + Predictor Engine ausführen
        # --------------------------------------------------- #
        logger.info(f"Prüfe PBot-Signal für {symbol} ({timeframe})...")

        # Aktuelle Daten holen
        recent_data = exchange.fetch_recent_ohlcv(symbol, timeframe, limit=300)
        if recent_data.empty or len(recent_data) < 100:
            logger.warning("Nicht genügend OHLCV-Daten für Predictor – überspringe.")
            return

        # HTF Daten holen (nur wenn nötig)
        htf_data = pd.DataFrame()
        if htf and htf != timeframe:
            # Wir brauchen genug Daten für den EMA auf dem HTF
            htf_data = exchange.fetch_recent_ohlcv(symbol, htf, limit=100)
            if htf_data.empty:
                logger.warning(f"Konnte HTF Daten ({htf}) nicht laden. MTF Filter wird ignoriert.")

        # Engine initialisieren
        strategy_params = params.get('strategy', {})
        # Stelle sicher, dass Defaults gesetzt sind, falls in Config vergessen
        strategy_params.setdefault('length', 14)
        strategy_params.setdefault('rsi_weight', 1.5)
        strategy_params.setdefault('wick_weight', 1.0)

        predictor = PredictorEngine(strategy_params)

        # Analyse durchführen
        # Die Engine berechnet intern ATR, RSI, Score, etc.
        analysis_result = predictor.analyze(recent_data, htf_data)

        # Supertrend-Filter Logging (zeigt, ob veto erfolgte)
        st_trend = analysis_result.get('st_trend') if analysis_result else None
        st_veto = analysis_result.get('supertrend_veto') if analysis_result else None
        if st_veto:
            trend_txt = 'LONG' if st_trend == 1 else 'SHORT' if st_trend == -1 else 'N/A'
            logger.info(f"Supertrend-Filter aktiv: {st_veto} (Trend: {trend_txt})")

        # Signal abrufen
        signal_side, signal_price = get_pbot_signal(analysis_result, params)

        if not signal_side:
            score = analysis_result.get('score', 0) if analysis_result else 0
            logger.info(f"Kein Signal (Score: {score:.2f}) – überspringe.")
            return

        if exchange.fetch_open_positions(symbol):
            logger.info("Position bereits offen – überspringe.")
            return

        # --------------------------------------------------- #
        # 1b. Risiko nur lokal deckeln (kein Portfolio-Blocker)
        # --------------------------------------------------- #
        risk_params = params.get('risk', {})
        raw_risk_pct = risk_params.get('risk_per_trade_pct', 1.0)
        effective_risk_pct = min(raw_risk_pct, 2.0)  # Hard Cap bleibt bei 2%

        # --------------------------------------------------- #
        # 2. Margin & Leverage setzen
        # --------------------------------------------------- #
        risk_params = params.get('risk', {})
        leverage = risk_params.get('leverage', 10)
        margin_mode = risk_params.get('margin_mode', 'isolated')

        if not exchange.set_margin_mode(symbol, margin_mode):
            logger.error("Margin-Modus konnte nicht gesetzt werden.")
            return
        if not exchange.set_leverage(symbol, leverage):
            logger.error("Leverage konnte nicht gesetzt werden.")
            return

        # --------------------------------------------------- #
        # 3. Balance & Risiko berechnen
        # --------------------------------------------------- #
        balance = exchange.fetch_balance_usdt()
        if balance <= 0:
            logger.error("Kein USDT-Guthaben.")
            return

        ticker = exchange.fetch_ticker(symbol)
        # Entry Preis aus Signal oder Ticker nehmen
        entry_price = signal_price or ticker['last']
        if not entry_price:
            logger.error("Kein Entry-Preis.")
            return

        rr = risk_params.get('risk_reward_ratio', 2.0)
        
        # --------------------------------------------------- #
        # SICHERHEITS-BREMSE (Hard Cap 2%)
        # --------------------------------------------------- #
        raw_risk_pct = risk_params.get('risk_per_trade_pct', 1.0)
        MAX_RISK = 2.0

        if raw_risk_pct > MAX_RISK:
            logger.warning(f"⚠️ Config-Risiko {raw_risk_pct}% ist zu hoch! Deckle HART auf {MAX_RISK}%.")

        # Endgueltiges Risiko ist das Minimum aus Config-Cap und Risk-Manager-Kappung
        effective_risk_pct = min(effective_risk_pct, MAX_RISK)

        risk_pct = effective_risk_pct / 100.0
        risk_usdt = balance * risk_pct
        # --------------------------------------------------- #

        atr_multiplier_sl = risk_params.get('atr_multiplier_sl', 2.0)
        min_sl_pct = risk_params.get('min_sl_pct', 0.5) / 100.0

        # --- WICHTIG: ATR kommt jetzt aus dem Engine Result ---
        current_atr = analysis_result.get('atr')

        if pd.isna(current_atr) or current_atr <= 0:
            logger.warning("ATR-Daten ungültig, verwende Hebel-basierte SL-Distanz.")
            sl_distance_pct = 1.0 / leverage
            sl_distance = entry_price * sl_distance_pct
        else:
            sl_distance_atr = current_atr * atr_multiplier_sl
            sl_distance_min = entry_price * min_sl_pct
            sl_distance = max(sl_distance_atr, sl_distance_min)

        # NEU: Check gegen letzte Kerze (Structure Protection)
        # Wir nehmen die vorletzte Kerze im DataFrame (iloc[-2]), da iloc[-1] die aktuelle Live-Kerze ist
        if len(recent_data) >= 2:
            last_closed_candle = recent_data.iloc[-2]
            
            if signal_side == 'buy':
                # Bei Long muss SL unter dem Low der letzten Kerze sein
                dist_to_low = entry_price - last_closed_candle['low']
                # Wenn das Low tiefer liegt als der aktuelle SL-Abstand, erweitern wir den Abstand
                if dist_to_low > sl_distance:
                    logger.info(f"SL erweitert auf Struktur-Low (Distanz: {dist_to_low:.2f})")
                    sl_distance = dist_to_low
            else:
                # Bei Short muss SL über dem High der letzten Kerze sein
                dist_to_high = last_closed_candle['high'] - entry_price
                if dist_to_high > sl_distance:
                    logger.info(f"SL erweitert auf Struktur-High (Distanz: {dist_to_high:.2f})")
                    sl_distance = dist_to_high

        if sl_distance <= 0: return

        # SL/TP Preise berechnen
        if signal_side == 'buy':
            # LONG
            sl_price = entry_price - sl_distance
            tp_price = entry_price + sl_distance * rr
            pos_side = 'buy'
            tsl_side = 'sell'
        else:
            # SHORT
            sl_price = entry_price + sl_distance
            tp_price = entry_price - sl_distance * rr
            pos_side = 'sell'
            tsl_side = 'buy'

        sl_distance_pct_equivalent = sl_distance / entry_price

        # Positionsgröße berechnen
        calculated_notional_value = risk_usdt / sl_distance_pct_equivalent
        amount = calculated_notional_value / entry_price

        min_amount = exchange.markets[symbol].get('limits', {}).get('amount', {}).get('min', 0.0)
        if amount < min_amount:
            logger.error(f"Ordergröße {amount} < Mindestbetrag {min_amount}.")
            return

        # --------------------------------------------------- #
        # 4. Market-Order eröffnen
        # --------------------------------------------------- #
        logger.info(f"Eröffne {pos_side.upper()}-Position: {amount:.6f} Contracts @ ${entry_price:.6f} | Risk: {risk_usdt:.2f} USDT")

        entry_order = exchange.create_market_order(
            symbol, pos_side, amount,
            {
                'leverage': leverage,
                'marginMode': margin_mode
            }
        )

        if not entry_order:
            logger.error("Market-Order fehlgeschlagen.")
            return

        time.sleep(2)
        position = exchange.fetch_open_positions(symbol)
        if not position:
            logger.error("Position wurde nicht eröffnet.")
            return

        pos_info = position[0]
        entry_price = float(pos_info.get('entryPrice', entry_price))
        contracts = float(pos_info['contracts'])

        # --------------------------------------------------- #
        # 5. SL & TP (Trigger-Market-Orders)
        # --------------------------------------------------- #
        sl_rounded = float(exchange.exchange.price_to_precision(symbol, sl_price))

        # Sende Hard Stop Loss
        exchange.place_trigger_market_order(symbol, tsl_side, contracts, sl_rounded, {'reduceOnly': True})

        # --------------------------------------------------- #
        # 6. Trailing-Stop-Loss (Optional, falls konfiguriert)
        # --------------------------------------------------- #
        # Wenn TSL konfiguriert ist, übernimmt er die Rolle des TP und zieht den SL nach
        act_rr = risk_params.get('trailing_stop_activation_rr', 1.5)
        callback_pct = risk_params.get('trailing_stop_callback_rate_pct', 0.5) / 100.0

        if pos_side == 'buy':
            act_price = entry_price + sl_distance * act_rr
        else:
            act_price = entry_price - sl_distance * act_rr

        act_price_rounded = float(exchange.exchange.price_to_precision(symbol, act_price))

        tsl = exchange.place_trailing_stop_order(
            symbol, tsl_side, contracts, act_price, callback_pct, {'reduceOnly': True}
        )

        if tsl:
            logger.info("Trailing-Stop platziert.")
        else:
            # Fallback auf Hard Take Profit, wenn TSL fehlschlägt oder nicht gewollt
            tp_rounded = float(exchange.exchange.price_to_precision(symbol, tp_price))
            logger.warning("Trailing-Stop nicht gesetzt. Setze festen Take Profit.")
            exchange.place_trigger_market_order(symbol, tsl_side, contracts, tp_rounded, {'reduceOnly': True})

        set_trade_lock(symbol_timeframe)

        # --------------------------------------------------- #
        # 7. Telegram-Benachrichtigung (NEU: HTML Format)
        # --------------------------------------------------- #
        if telegram_config and telegram_config.get('bot_token') and telegram_config.get('chat_id'):
            sl_r = float(exchange.exchange.price_to_precision(symbol, sl_price))

            sl_dist_usd = abs(entry_price - sl_price)
            sl_dist_pct = (sl_dist_usd / entry_price) * 100

            score = analysis_result.get('score', 0)
            is_choppy = analysis_result.get('is_choppy', False)
            choppy_txt = "⚠️ Choppy" if is_choppy else "✅ Stable"
            
            # HTML Formatierung (Kein MarkdownV2 mehr!)
            msg = (
                f"🚀 <b>PBOT SIGNAL</b>: {symbol} ({timeframe})\n"
                f"Score: <b>{score:.2f}</b> ({choppy_txt})\n"
                f"--------------------------------\n"
                f"➡️ Richtung: <b>{pos_side.upper()}</b>\n"
                f"💰 Entry: ${entry_price:.6f}\n"
                f"🛑 SL: ${sl_r:.6f} (-{sl_dist_pct:.2f}%)\n"
                f"📈 TSL Aktivierung: ${act_price_rounded:.6f} (RR: {act_rr})\n"
                f"⚙️ Hebel: {leverage}x\n"
                f"🛡️ Risiko: {risk_pct*100:.1f}% ({risk_usdt:.2f} USDT)"
            )
            send_message(telegram_config['bot_token'], telegram_config['chat_id'], msg)


        logger.info("Trade-Eröffnung erfolgreich abgeschlossen.")

    except ccxt.InsufficientFunds as e:
        logger.error(f"InsufficientFunds: {e}")
    except ccxt.ExchangeError as e:
        logger.error(f"Börsenfehler: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        housekeeper_routine(exchange, symbol, logger)


# --------------------------------------------------------------------------- #
# Vollständiger Handelszyklus (Unverändert übernommen)
# --------------------------------------------------------------------------- #
def full_trade_cycle(exchange, model, scaler, params, telegram_config, logger):
    symbol = params['market']['symbol']
    try:
        pos = exchange.fetch_open_positions(symbol)
        if pos:
            logger.info(f"Position offen – Management via SL/TP/TSL.")
        else:
            housekeeper_routine(exchange, symbol, logger)
            check_and_open_new_position(exchange, model, scaler, params, telegram_config, logger)
    except ccxt.DDoSProtection:
        logger.warning("Rate-Limit – warte 10s.")
        time.sleep(10)
    except ccxt.RequestTimeout:
        logger.warning("Timeout – warte 5s.")
        time.sleep(5)
    except ccxt.NetworkError:
        logger.warning("Netzwerkfehler – warte 10s.")
        time.sleep(10)
    except ccxt.AuthenticationError as e:
        logger.critical(f"Authentifizierungsfehler: {e}")
    except Exception as e:
        logger.error(f"Fehler im Zyklus: {e}", exc_info=True)
        time.sleep(5)

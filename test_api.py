# test_api.py
import os
import sys
import json
import logging
from unittest.mock import patch

# Pfad-Setup
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
# Füge den src-Ordner zum Pfad hinzu
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

# Importiere die PBot-Module (Aktualisiert)
from pbot.utils.exchange import Exchange
from pbot.utils.trade_manager import check_and_open_new_position, housekeeper_routine
from pbot.utils.timeframe_utils import determine_htf
# WICHTIG: Kein SMC Import mehr!
from pbot.strategy.trade_logic import get_pbot_signal 

# Logging Setup (minimal)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(name)s: %(message)s')
logger = logging.getLogger("test_api_runner")

def run_test():
    try:
        # 1. Konfiguration laden
        secret_path = os.path.join(PROJECT_ROOT, 'secret.json')
        if not os.path.exists(secret_path):
            logger.error("secret.json nicht gefunden!")
            return

        with open(secret_path, "r") as f:
            secrets = json.load(f)

        # Flexibler Account-Check (pbot oder titanbot)
        acc_key = 'pbot' if 'pbot' in secrets else 'titanbot'
        if acc_key not in secrets:
            logger.error("Kein Account in secret.json gefunden.")
            return

        test_account = secrets[acc_key][0]
        telegram_config = secrets.get('telegram', {})
        exchange = Exchange(test_account)

        # 2. Mock-Parameter (PBot Style)
        symbol = 'XRP/USDT:USDT'
        timeframe = '5m'
        htf = determine_htf(timeframe)

        params = {
            'market': {'symbol': symbol, 'timeframe': timeframe, 'htf': htf},
            'strategy': { 
                'length': 14, 
                'rsi_weight': 1.5,
                'wick_weight': 1.0,
                'use_adx_filter': False 
            },
            'risk': {
                'margin_mode': 'isolated',
                'risk_per_trade_pct': 0.5, # Konservativ für Test
                'risk_reward_ratio': 2.0,
                'leverage': 5,
                'trailing_stop_activation_rr': 1.5,
                'trailing_stop_callback_rate_pct': 0.5,
                'atr_multiplier_sl': 2.0,
                'min_sl_pct': 0.5
            },
            'behavior': { 'use_longs': True, 'use_shorts': True }
        }

        # 3. Führe die kritische Funktion aus
        logger.info(f"Führe API-Test für {symbol} aus...")

        # HOUSEKEEPER vor dem Test
        housekeeper_routine(exchange, symbol, logger)

        # WICHTIG: Wir mocken jetzt 'get_pbot_signal' und die Engine-Analyse
        # Wir simulieren ein KAUF-Signal
        with patch('pbot.utils.trade_manager.get_pbot_signal', return_value=('buy', 1.0)):
            # Wir müssen auch die Analyse mocken, da trade_manager darauf zugreift um ATR zu holen
            dummy_analysis = {
                'score': 2.0, 
                'atr': 0.01, 
                'is_choppy': False, 
                'close': 1.0
            }
            # Mocke die analyze Methode der PredictorEngine Instanz
            with patch('pbot.utils.trade_manager.PredictorEngine.analyze', return_value=dummy_analysis):
                check_and_open_new_position(exchange, None, None, params, telegram_config, logger)

        logger.info("Test beendet. Prüfen Sie die Logs auf API-Fehler.")

    except Exception as e:
        logger.error(f"Kritischer Fehler während der API-Ausführung: {e}")

if __name__ == "__main__":
    run_test()

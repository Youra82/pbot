# tests/test_workflow.py
import pytest
import os
import sys
import json
import logging
import time
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# IMPORTS AUF PBOT GEÄNDERT
from pbot.utils.exchange import Exchange
from pbot.utils.trade_manager import check_and_open_new_position, housekeeper_routine
from pbot.utils.trade_manager import set_trade_lock, is_trade_locked
from pbot.utils.timeframe_utils import determine_htf

@pytest.fixture(scope="module")
def test_setup():
    print("\n--- PBot Workflow Test ---")
    secret_path = os.path.join(PROJECT_ROOT, 'secret.json')
    if not os.path.exists(secret_path):
        pytest.skip("secret.json fehlt.")

    with open(secret_path, 'r') as f: secrets = json.load(f)
    
    # Schlüsselsuche (titanbot oder jaegerbot kompatibel)
    acc_key = 'pbot' if 'pbot' in secrets else 'jaegerbot'
    if not secrets.get(acc_key): pytest.skip("Kein Account in secret.json")

    exchange = Exchange(secrets[acc_key][0])
    symbol = 'PEPE/USDT:USDT'
    
    # Housekeeping
    logger = logging.getLogger("test")
    housekeeper_routine(exchange, symbol, logger)
    
    # Params
    params = {
        'market': {'symbol': symbol, 'timeframe': '15m', 'htf': '1h'},
        'strategy': {'length': 14, 'rsi_weight': 1.5},
        'risk': {'margin_mode': 'isolated', 'risk_per_trade_pct': 5.0, 'leverage': 5, 'atr_multiplier_sl': 2.0, 'min_sl_pct': 1.0},
        'behavior': {'use_longs': True, 'use_shorts': True}
    }
    
    yield exchange, params, secrets.get('telegram', {}), symbol, logger
    
    # Teardown
    housekeeper_routine(exchange, symbol, logger)

def test_pbot_execution(test_setup):
    exchange, params, telegram, symbol, logger = test_setup
    
    # Mocking der neuen PBot Logik
    with patch('pbot.utils.trade_manager.set_trade_lock'), \
         patch('pbot.utils.trade_manager.is_trade_locked', return_value=False), \
         patch('pbot.utils.trade_manager.get_pbot_signal', return_value=('buy', None)):
         
         check_and_open_new_position(exchange, None, None, params, telegram, logger)
         
    time.sleep(2)
    pos = exchange.fetch_open_positions(symbol)
    assert len(pos) > 0, "Position sollte offen sein"

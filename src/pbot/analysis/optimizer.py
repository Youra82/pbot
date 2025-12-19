# /root/pbot/src/pbot/analysis/optimizer.py
import os
import sys
import json
import optuna
import argparse
import logging
import warnings

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.analysis.backtester import load_data, run_pbot_backtest
from pbot.utils.timeframe_utils import determine_htf

# Verbosity auf INFO setzen, falls du auch Textausgaben willst (sonst WARNING lassen)
optuna.logging.set_verbosity(optuna.logging.WARNING)

HISTORICAL_DATA = None
CURRENT_SYMBOL = None
CURRENT_TIMEFRAME = None
CURRENT_HTF = None
CONFIG_SUFFIX = ""
START_CAPITAL = 1000

def create_safe_filename(symbol, timeframe):
    return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"

def objective(trial):
    # --- PBot Parameter-Raum ---
    strategy_params = {
        # Strategie-Werte (Predictor Logik)
        'length': trial.suggest_int('length', 5, 40),
        'rsi_weight': trial.suggest_float('rsi_weight', 0.5, 3.0, step=0.1),
        'wick_weight': trial.suggest_float('wick_weight', 0.5, 3.0, step=0.1),
        'use_adx_filter': trial.suggest_categorical('use_adx_filter', [True, False]),
        'adx_threshold': trial.suggest_int('adx_threshold', 15, 35),
        'use_mtf': True,
        'min_score': trial.suggest_float('min_score', 0.5, 2.0, step=0.1),

        # Kontext
        'symbol': CURRENT_SYMBOL,
        'timeframe': CURRENT_TIMEFRAME,
        'htf': CURRENT_HTF
    }

    risk_params = {
        'risk_reward_ratio': trial.suggest_float('risk_reward_ratio', 1.5, 5.0),
        
        # --- HARD CAP: Maximal 2% Risiko erlaubt ---
        'risk_per_trade_pct': trial.suggest_float('risk_per_trade_pct', 0.5, 2.0),
        # -------------------------------------------
        
        'leverage': trial.suggest_int('leverage', 5, 25),
        'atr_multiplier_sl': trial.suggest_float('atr_multiplier_sl', 1.0, 4.0),
        'min_sl_pct': trial.suggest_float('min_sl_pct', 0.3, 2.0),

        # Trailing Stop Parameter (werden gespeichert für Live-Betrieb)
        'trailing_stop_activation_rr': trial.suggest_float('trailing_stop_activation_rr', 1.0, 3.0),
        'trailing_stop_callback_rate_pct': trial.suggest_float('trailing_stop_callback_rate_pct', 0.5, 3.0)
    }

    # Simulation starten
    result = run_pbot_backtest(HISTORICAL_DATA.copy(), strategy_params, risk_params, START_CAPITAL)

    pnl = result.get('total_pnl_pct', -1000)
    drawdown = result.get('max_drawdown_pct', 1.0)
    trades = result.get('trades_count', 0)

    # Pruning Bedingungen (Abbruch wenn schlecht)
    # Wenn Drawdown > 40% oder weniger als 10 Trades oder Verlust -> Rauswerfen
    if drawdown > 0.40 or trades < 10 or pnl < 0:
        raise optuna.exceptions.TrialPruned()

    return pnl

def main():
    global HISTORICAL_DATA, CURRENT_SYMBOL, CURRENT_TIMEFRAME, CURRENT_HTF, CONFIG_SUFFIX, START_CAPITAL
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', required=True)
    parser.add_argument('--timeframes', required=True)
    parser.add_argument('--start_date', required=True)
    parser.add_argument('--end_date', required=True)
    parser.add_argument('--jobs', default=1, type=int)
    parser.add_argument('--trials', default=100, type=int)
    parser.add_argument('--start_capital', default=1000, type=float)

    # Dummy args für Pipeline-Kompatibilität
    parser.add_argument('--max_drawdown', default=30, type=float)
    parser.add_argument('--min_win_rate', default=0, type=float)
    parser.add_argument('--min_pnl', default=0, type=float)
    parser.add_argument('--mode', default='strict', type=str)
    parser.add_argument('--config_suffix', type=str, default="")

    args = parser.parse_args()
    START_CAPITAL = args.start_capital
    CONFIG_SUFFIX = args.config_suffix

    symbols, timeframes = args.symbols.split(), args.timeframes.split()
    tasks = [{'symbol': f"{s}/USDT:USDT", 'timeframe': tf} for s in symbols for tf in timeframes]

    for task in tasks:
        CURRENT_SYMBOL, CURRENT_TIMEFRAME = task['symbol'], task['timeframe']
        CURRENT_HTF = determine_htf(CURRENT_TIMEFRAME)

        print(f"\n===== Optimiere PBot: {CURRENT_SYMBOL} ({CURRENT_TIMEFRAME}) =====")
        HISTORICAL_DATA = load_data(CURRENT_SYMBOL, CURRENT_TIMEFRAME, args.start_date, args.end_date)

        if HISTORICAL_DATA.empty:
            print(f"❌ Keine Daten für {CURRENT_SYMBOL}. Überspringe.")
            continue

        study_name = f"pbot_{create_safe_filename(CURRENT_SYMBOL, CURRENT_TIMEFRAME)}{CONFIG_SUFFIX}"
        db_path = os.path.join(PROJECT_ROOT, 'artifacts', 'db', 'optuna_pbot.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        storage = f"sqlite:///{db_path}"

        study = optuna.create_study(storage=storage, study_name=study_name, direction="maximize", load_if_exists=True)

        print(f"🚀 Starte {args.trials} Trials...")
        try:
            study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs, show_progress_bar=True)
        except KeyboardInterrupt:
            print("\n🛑 Optimierung durch Benutzer abgebrochen.")
            break

        if len(study.trials) == 0:
            print("⚠️ Keine Trials abgeschlossen.")
            continue

        best = study.best_trial
        print(f"\n🏆 Bestes Ergebnis: PnL {best.value:.2f}%")
        print(f"   Parameter: {best.params}")

        # Config speichern
        config_dir = os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy', 'configs')
        os.makedirs(config_dir, exist_ok=True)

        best_params = best.params
        config = {
            "market": {"symbol": CURRENT_SYMBOL, "timeframe": CURRENT_TIMEFRAME, "htf": CURRENT_HTF},
            "strategy": {k: v for k, v in best_params.items() if k in ['length', 'rsi_weight', 'wick_weight', 'use_adx_filter', 'adx_threshold', 'use_mtf', 'min_score']},
            "risk": {k: v for k, v in best_params.items() if k not in ['length', 'rsi_weight', 'wick_weight', 'use_adx_filter', 'adx_threshold', 'use_mtf', 'min_score']},
            "behavior": {"use_longs": True, "use_shorts": True}
        }
        config['risk']['margin_mode'] = 'isolated'

        fname = f"config_{create_safe_filename(CURRENT_SYMBOL, CURRENT_TIMEFRAME)}{CONFIG_SUFFIX}.json"
        with open(os.path.join(config_dir, fname), 'w') as f:
            json.dump(config, f, indent=4)
        print(f"💾 Config gespeichert: {fname}")

if __name__ == "__main__":
    main()

# /root/pbot/src/pbot/analysis/optimizer.py
import os
import sys
import json
import optuna
import argparse
import logging
import warnings
from datetime import datetime as _dt

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.analysis.backtester import load_data, run_pbot_backtest
from pbot.utils.timeframe_utils import determine_htf

optuna.logging.set_verbosity(optuna.logging.WARNING)

HISTORICAL_DATA = None
CURRENT_SYMBOL = None
CURRENT_TIMEFRAME = None
CURRENT_HTF = None
CONFIG_SUFFIX = ""
START_CAPITAL = 1000
MAX_DRAWDOWN_CONSTRAINT = 0.30
MIN_WIN_RATE_CONSTRAINT = 40.0
MIN_PNL_CONSTRAINT = 5.0
OPTIM_MODE = "strict"

# Ergebnisdatei fuer den Scheduler (Telegram-Benachrichtigung)
RESULTS_FILE = os.path.join(PROJECT_ROOT, 'artifacts', 'results', 'last_optimizer_run.json')


def create_safe_filename(symbol, timeframe):
    return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"


def objective(trial):
    # --- PBot Parameter-Raum ---
    strategy_params = {
        'length': trial.suggest_int('length', 5, 40),
        'rsi_weight': trial.suggest_float('rsi_weight', 0.5, 3.0, step=0.1),
        'wick_weight': trial.suggest_float('wick_weight', 0.5, 3.0, step=0.1),
        'use_adx_filter': trial.suggest_categorical('use_adx_filter', [True, False]),
        'adx_threshold': trial.suggest_int('adx_threshold', 15, 35),
        'use_mtf': True,
        'min_score': trial.suggest_float('min_score', 0.5, 2.0, step=0.1),
        'symbol': CURRENT_SYMBOL,
        'timeframe': CURRENT_TIMEFRAME,
        'htf': CURRENT_HTF
    }

    risk_params = {
        'risk_reward_ratio': trial.suggest_float('risk_reward_ratio', 1.5, 5.0),
        'risk_per_trade_pct': trial.suggest_float('risk_per_trade_pct', 0.5, 1.5),
        'leverage': trial.suggest_int('leverage', 5, 15),
        'atr_multiplier_sl': trial.suggest_float('atr_multiplier_sl', 1.0, 4.0),
        'min_sl_pct': trial.suggest_float('min_sl_pct', 0.3, 2.0),
        'trailing_stop_activation_rr': trial.suggest_float('trailing_stop_activation_rr', 1.0, 3.0),
        'trailing_stop_callback_rate_pct': trial.suggest_float('trailing_stop_callback_rate_pct', 0.5, 3.0)
    }

    result = run_pbot_backtest(HISTORICAL_DATA.copy(), strategy_params, risk_params, START_CAPITAL)

    pnl      = result.get('total_pnl_pct', -1000)
    drawdown = result.get('max_drawdown_pct', 1.0)
    trades   = result.get('trades_count', 0)
    win_rate = result.get('win_rate', 0)

    if drawdown > MAX_DRAWDOWN_CONSTRAINT or trades < 15 or pnl < MIN_PNL_CONSTRAINT:
        raise optuna.exceptions.TrialPruned()

    if win_rate < MIN_WIN_RATE_CONSTRAINT:
        raise optuna.exceptions.TrialPruned()

    return pnl


def main():
    global HISTORICAL_DATA, CURRENT_SYMBOL, CURRENT_TIMEFRAME, CURRENT_HTF, CONFIG_SUFFIX
    global MAX_DRAWDOWN_CONSTRAINT, MIN_WIN_RATE_CONSTRAINT, MIN_PNL_CONSTRAINT, START_CAPITAL, OPTIM_MODE

    parser = argparse.ArgumentParser(description="Parameter-Optimierung fuer PBot")
    parser.add_argument('--symbols',    type=str, default="",
                        help='Space-getrennte Symbole, z.B. "BTC ETH"')
    parser.add_argument('--timeframes', type=str, default="",
                        help='Space-getrennte Timeframes, z.B. "1h 4h"')
    parser.add_argument('--pairs',      type=str, default="",
                        help='Explizite Paare: "BTC/USDT:USDT|1h ETH/USDT:USDT|4h" '
                             '(ueberschreibt --symbols/--timeframes)')
    parser.add_argument('--start_date',    required=True, type=str)
    parser.add_argument('--end_date',      required=True, type=str)
    parser.add_argument('--jobs',          default=1, type=int)
    parser.add_argument('--trials',        default=100, type=int)
    parser.add_argument('--start_capital', default=1000, type=float)
    parser.add_argument('--max_drawdown',  default=30, type=float)
    parser.add_argument('--min_win_rate',  default=40, type=float)
    parser.add_argument('--min_pnl',       default=5, type=float)
    parser.add_argument('--mode',          default='strict', type=str)
    parser.add_argument('--config_suffix', type=str, default="")

    args = parser.parse_args()

    CONFIG_SUFFIX           = args.config_suffix
    MAX_DRAWDOWN_CONSTRAINT = args.max_drawdown / 100.0
    MIN_WIN_RATE_CONSTRAINT = args.min_win_rate
    MIN_PNL_CONSTRAINT      = args.min_pnl
    START_CAPITAL           = args.start_capital
    N_TRIALS                = args.trials
    OPTIM_MODE              = args.mode

    # TASKS aufbauen: --pairs hat Vorrang vor --symbols/--timeframes
    if args.pairs.strip():
        TASKS = []
        for p in args.pairs.strip().split():
            sym, tf = p.rsplit('|', 1)
            TASKS.append({'symbol': sym, 'timeframe': tf})
    elif args.symbols and args.timeframes:
        symbols    = args.symbols.split()
        timeframes = args.timeframes.split()
        TASKS = [{'symbol': f"{s}/USDT:USDT", 'timeframe': tf}
                 for s in symbols for tf in timeframes]
    else:
        print("Fehler: --pairs oder --symbols + --timeframes muss angegeben werden.")
        return

    run_results = {
        'run_start': _dt.now().isoformat(timespec='seconds'),
        'run_end':   None,
        'saved':     [],
        'failed':    [],
    }

    for task in TASKS:
        symbol, timeframe = task['symbol'], task['timeframe']
        CURRENT_SYMBOL    = symbol
        CURRENT_TIMEFRAME = timeframe
        CURRENT_HTF       = determine_htf(timeframe)

        print(f"\n===== Optimiere PBot: {symbol} ({timeframe}) =====")

        HISTORICAL_DATA = load_data(symbol, timeframe, args.start_date, args.end_date)
        if HISTORICAL_DATA.empty:
            print("  Keine Daten verfuegbar.")
            run_results['failed'].append(
                {'symbol': symbol, 'timeframe': timeframe, 'reason': 'no_data'})
            continue

        DB_FILE     = os.path.join(PROJECT_ROOT, 'artifacts', 'db', 'optuna_pbot.db')
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        STORAGE_URL = f"sqlite:///{DB_FILE}?timeout=60"
        study_name  = f"pbot_{create_safe_filename(symbol, timeframe)}{CONFIG_SUFFIX}"

        study = optuna.create_study(
            storage=STORAGE_URL, study_name=study_name,
            direction="maximize", load_if_exists=True)

        print(f"Starte {N_TRIALS} Trials...")
        try:
            study.optimize(objective, n_trials=N_TRIALS, n_jobs=args.jobs, show_progress_bar=True)
        except KeyboardInterrupt:
            print("\nOptimierung durch Benutzer abgebrochen.")
            break
        except Exception as e:
            print(f"FEHLER: {e}")
            run_results['failed'].append(
                {'symbol': symbol, 'timeframe': timeframe, 'reason': str(e)[:80]})
            continue

        valid_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        if not valid_trials:
            print("  Keine gueltigen Trials abgeschlossen.")
            run_results['failed'].append(
                {'symbol': symbol, 'timeframe': timeframe, 'reason': 'no_valid_trials'})
            continue

        best_trial  = max(valid_trials, key=lambda t: t.value)
        best_params = best_trial.params
        new_pnl     = best_trial.value

        print(f"  Bestes Ergebnis: PnL {new_pnl:.2f}%")

        config_dir         = os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy', 'configs')
        os.makedirs(config_dir, exist_ok=True)
        config_filename    = f"config_{create_safe_filename(symbol, timeframe)}{CONFIG_SUFFIX}.json"
        config_output_path = os.path.join(config_dir, config_filename)

        # Nur speichern wenn besser als bestehende Config
        existing_pnl = None
        if os.path.exists(config_output_path):
            try:
                with open(config_output_path) as cf:
                    existing_cfg = json.load(cf)
                existing_pnl = existing_cfg.get('_meta', {}).get('pnl_pct')
            except Exception:
                pass

        if existing_pnl is not None and new_pnl <= existing_pnl:
            print(f"  Bestehende Config besser ({existing_pnl:.2f}% vs {new_pnl:.2f}%) — wird nicht ueberschrieben.")
            run_results['failed'].append({
                'symbol': symbol, 'timeframe': timeframe,
                'reason': f'existing_better_{existing_pnl:.2f}pct',
            })
            continue

        config = {
            "market":   {"symbol": symbol, "timeframe": timeframe, "htf": CURRENT_HTF},
            "strategy": {k: v for k, v in best_params.items()
                         if k in ['length', 'rsi_weight', 'wick_weight',
                                  'use_adx_filter', 'adx_threshold', 'use_mtf', 'min_score']},
            "risk":     {k: v for k, v in best_params.items()
                         if k not in ['length', 'rsi_weight', 'wick_weight',
                                      'use_adx_filter', 'adx_threshold', 'use_mtf', 'min_score']},
            "behavior": {"use_longs": True, "use_shorts": True},
            "_meta": {
                "pnl_pct":      round(new_pnl, 2),
                "optimized_at": _dt.now().isoformat(timespec='seconds'),
            },
        }
        config['risk']['margin_mode'] = 'isolated'

        with open(config_output_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"  Config gespeichert: {config_filename}")

        run_results['saved'].append({
            'symbol':      symbol,
            'timeframe':   timeframe,
            'pnl_pct':     round(new_pnl, 2),
            'config_file': config_filename,
        })

    # Lauf-Ergebnisse fuer Scheduler speichern
    run_results['run_end'] = _dt.now().isoformat(timespec='seconds')
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(run_results, f, indent=2, ensure_ascii=False)
    print(f"\nErgebnisse gespeichert: {RESULTS_FILE}")


if __name__ == "__main__":
    main()

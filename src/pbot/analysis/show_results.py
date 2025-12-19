# /root/pbot/src/pbot/analysis/show_results.py
import os
import sys
import json
import pandas as pd
from datetime import date
import logging
import argparse
import warnings

logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.analysis.backtester import load_data, run_pbot_backtest
from pbot.analysis.portfolio_simulator import run_portfolio_simulation
from pbot.analysis.portfolio_optimizer import run_portfolio_optimizer
from pbot.utils.telegram import send_document

# --- Einzel-Analyse ---
def run_single_analysis(start_date, end_date, start_capital):
    print("--- PBot Ergebnis-Analyse (Einzel-Modus) ---")
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy', 'configs')

    all_results = []
    if not os.path.exists(configs_dir):
        print(f"Verzeichnis nicht gefunden: {configs_dir}")
        return

    config_files = sorted([f for f in os.listdir(configs_dir) if f.startswith('config_') and f.endswith('.json')])

    if not config_files:
        print("\nKeine gültigen Konfigurationen zum Analysieren gefunden.")
        return

    print(f"Zeitraum: {start_date} bis {end_date} | Startkapital: {start_capital} USDT")

    for filename in config_files:
        config_path = os.path.join(configs_dir, filename)
        try:
            with open(config_path, 'r') as f: config = json.load(f)

            symbol = config['market']['symbol']
            timeframe = config['market']['timeframe']
            strategy_name = f"{symbol} ({timeframe})"

            print(f"\nAnalysiere Ergebnisse für: {filename}...")

            # Daten laden
            data = load_data(symbol, timeframe, start_date, end_date)
            if data.empty:
                print(f"--> WARNUNG: Konnte keine Daten laden für {strategy_name}. Überspringe.")
                continue

            # Parameter laden
            strategy_params = config.get('strategy', {})
            risk_params = config.get('risk', {})

            # Wichtig: Kontext hinzufügen für den Backtester
            strategy_params['symbol'] = symbol
            strategy_params['timeframe'] = timeframe
            strategy_params['htf'] = config['market'].get('htf')

            result = run_pbot_backtest(data.copy(), strategy_params, risk_params, start_capital, verbose=False)

            all_results.append({
                "Strategie": strategy_name,
                "Trades": result.get('trades_count', 0),
                "Win Rate %": result.get('win_rate', 0),
                "PnL %": result.get('total_pnl_pct', -100),
                "Max DD %": result.get('max_drawdown_pct', 1.0) * 100,
                "Endkapital": result.get('end_capital', start_capital)
            })

        except Exception as e:
            print(f"--> FEHLER bei der Analyse von {filename}: {e}")
            continue

    if not all_results:
        print("\nKeine gültigen Ergebnisse zum Anzeigen gefunden.")
        return

    results_df = pd.DataFrame(all_results)
    results_df = results_df.sort_values(by="PnL %", ascending=False)

    pd.set_option('display.width', 1000)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.float_format', '{:.2f}'.format)

    print("\n\n=========================================================================================")
    print(f"                        Zusammenfassung aller Einzelstrategien")
    print("=========================================================================================")
    print(results_df.to_string(index=False))
    print("=========================================================================================")


# --- Geteilter Modus (Manuell / Auto) ---
def run_shared_mode(is_auto: bool, start_date, end_date, start_capital, target_max_dd: float):
    mode_name = "Automatische Portfolio-Optimierung" if is_auto else "Manuelle Portfolio-Simulation"
    print(f"--- PBot {mode_name} ---")
    if is_auto:
        print(f"Ziel: Maximaler Profit bei maximal {target_max_dd:.2f}% Drawdown.")

    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'pbot', 'strategy', 'configs')
    available_strategies = []
    if os.path.isdir(configs_dir):
        for filename in sorted(os.listdir(configs_dir)):
            if filename.startswith('config_') and filename.endswith('.json'):
                available_strategies.append(filename)

    if not available_strategies:
        print("Keine optimierten Strategien (Configs) gefunden."); return

    selected_files = []
    if not is_auto:
        print("\nVerfügbare Strategien:")
        for i, name in enumerate(available_strategies): print(f"  {i+1}) {name}")
        selection = input("\nWelche Strategien sollen simuliert werden? (Zahlen mit Komma, z.B. 1,3,4 oder 'alle'): ")
        try:
            if selection.lower() == 'alle': selected_files = available_strategies
            else: selected_files = [available_strategies[int(i.strip()) - 1] for i in selection.split(',')]
        except (ValueError, IndexError): print("Ungültige Auswahl. Breche ab."); return
    else:
        selected_files = available_strategies

    strategies_data = {}
    print("\nLade Daten für gewählte Strategien...")
    for filename in selected_files:
        try:
            with open(os.path.join(configs_dir, filename), 'r') as f: config = json.load(f)
            symbol = config['market']['symbol']
            timeframe = config['market']['timeframe']
            htf = config['market'].get('htf')

            data = load_data(symbol, timeframe, start_date, end_date)
            if not data.empty:
                strategies_data[filename] = {
                    'symbol': symbol, 'timeframe': timeframe, 'data': data,
                    'smc_params': config.get('strategy', {}), 
                    'risk_params': config.get('risk', {}),
                    'htf': htf
                }
            else:
                print(f"WARNUNG: Konnte Daten für {filename} nicht laden. Wird ignoriert.")
        except Exception as e:
            print(f"FEHLER beim Laden der Config/Daten für {filename}: {e}")

    if not strategies_data:
        print("Konnte für keine der gewählten Strategien Daten laden. Breche ab."); return

    equity_df = pd.DataFrame()
    csv_path = ""
    caption = ""

    try:
        if is_auto:
            results = run_portfolio_optimizer(start_capital, strategies_data, start_date, end_date, target_max_dd)
            if results and 'final_result' in results and results['final_result'] is not None:
                final_report = results['final_result']
                optimal_files = results.get('optimal_portfolio', [])

                # --- ANZEIGE DES PORTFOLIOS ---
                print("\n==================================================")
                print("           GEWÄHLTES OPTIMALES PORTFOLIO")
                print("==================================================")
                if not optimal_files:
                    print(" (Leer)")
                else:
                    for filename in optimal_files:
                        try:
                            clean_name = filename.replace('config_', '').replace('.json', '')
                            parts = clean_name.split('_')
                            sym = parts[0].replace('USDTUSDT', '/USDT')
                            tf = parts[-1]
                            print(f"  ✅ {sym} ({tf})")
                        except:
                            print(f"  ✅ {filename}")
                print("==================================================\n")
                
                print(f"Endkapital:         {final_report['end_capital']:.2f} USDT")

                # --- INTERAKTIVES UPDATE DER SETTINGS.JSON (BEREINIGT) ---
                print("\n" + "-"*60)
                print("ACHTUNG: Wenn du 'j' wählst, wird settings.json BEREINIGT.")
                print("Nur die oben angezeigten Strategien bleiben erhalten.")
                print("Alle anderen Einträge werden gelöscht.")
                print("-"*60)
                
                update_choice = input("Möchtest du settings.json mit diesem Portfolio überschreiben? (j/n): ")
                if update_choice.lower() in ['j', 'y', 'ja', 'yes']:
                    try:
                        settings_path = os.path.join(PROJECT_ROOT, 'settings.json')
                        # Lade existierende Settings, um andere Einstellungen (falls vorhanden) zu behalten
                        current_settings = {}
                        if os.path.exists(settings_path):
                            with open(settings_path, 'r') as f:
                                current_settings = json.load(f)
                        
                        # Stelle sicher, dass die Struktur existiert
                        if 'live_trading_settings' not in current_settings:
                            current_settings['live_trading_settings'] = {}
                        
                        # Erstelle die NEUE, saubere Liste
                        new_active_list = []
                        
                        for filename in optimal_files:
                            # Lese die Config-Datei ein, um saubere Daten zu haben
                            conf_path = os.path.join(configs_dir, filename)
                            if os.path.exists(conf_path):
                                with open(conf_path, 'r') as cf:
                                    c_data = json.load(cf)
                                    
                                new_entry = {
                                    "symbol": c_data['market']['symbol'],
                                    "timeframe": c_data['market']['timeframe'],
                                    "use_macd_filter": False, # Standard für PBot
                                    "active": True
                                }
                                new_active_list.append(new_entry)
                        
                        # Überschreibe die Liste hart
                        current_settings['live_trading_settings']['active_strategies'] = new_active_list
                        
                        # Speichern
                        with open(settings_path, 'w') as f:
                            json.dump(current_settings, f, indent=4)
                        
                        print(f"\n✔ settings.json wurde BEREINIGT und aktualisiert!")
                        print(f"  -> Es sind jetzt genau {len(new_active_list)} Strategien enthalten.")
                        
                    except Exception as e:
                        print(f"\n❌ Fehler beim Aktualisieren der Settings: {e}")
                else:
                    print("Keine Änderungen an settings.json vorgenommen.")
                print("-"*60 + "\n")
                # ---------------------------------------------

                csv_path = os.path.join(PROJECT_ROOT, 'optimal_portfolio_equity.csv')
                caption = f"PBot Portfolio-Optimierung (Max DD <= {target_max_dd:.1f}%)\nEndkapital: {final_report['end_capital']:.2f} USDT"
                equity_df = final_report.get('equity_curve')
            else:
                print(f"\nKein Portfolio gefunden, das die Bedingung erfüllt.")

        else: # Manuell
            sim_data = {v['symbol'] + "_" + v['timeframe']: v for k, v in strategies_data.items()}
            results = run_portfolio_simulation(start_capital, sim_data, start_date, end_date)
            if results:
                print(f"Endkapital:         {results['end_capital']:.2f} USDT")
                csv_path = os.path.join(PROJECT_ROOT, 'manual_portfolio_equity.csv')
                caption = f"PBot Portfolio-Simulation\nEndkapital: {results['end_capital']:.2f} USDT"
                equity_df = results.get('equity_curve')

    except Exception as e:
        print(f"\nFEHLER während der Portfolio-Analyse: {e}")
        import traceback; traceback.print_exc()

    # Export & Telegram
    if equity_df is not None and not equity_df.empty and csv_path:
        print("\n--- Export ---")
        try:
            # Save CSV
            if 'timestamp' in equity_df.columns and not isinstance(equity_df.index, pd.DatetimeIndex):
                 equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
                 equity_df.set_index('timestamp', inplace=True, drop=False)

            # Sauberes Speichern
            equity_df.to_csv(csv_path)
            print(f"✔ Equity-Kurve nach '{os.path.basename(csv_path)}' exportiert.")

            # Senden
            with open(os.path.join(PROJECT_ROOT, 'secret.json'), 'r') as f: secrets = json.load(f)
            telegram_config = secrets.get('telegram', {})
            if telegram_config.get('bot_token'):
                print("Sende Bericht an Telegram...")
                send_document(telegram_config.get('bot_token'), telegram_config.get('chat_id'), csv_path, caption)
                print("✔ Gesendet.")
        except Exception as e:
            print(f"Fehler beim Export/Senden: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='1', type=str)
    parser.add_argument('--target_max_drawdown', default=30.0, type=float)
    args = parser.parse_args()

    print("\n--- Bitte Konfiguration für den Backtest festlegen ---")
    start_date = input(f"Startdatum (JJJJ-MM-TT) [Standard: 2023-01-01]: ") or "2023-01-01"
    end_date = input(f"Enddatum (JJJJ-MM-TT) [Standard: Heute]: ") or date.today().strftime("%Y-%m-%d")
    start_capital = int(input(f"Startkapital in USDT eingeben [Standard: 1000]: ") or 1000)
    print("--------------------------------------------------")

    if args.mode == '2':
        run_shared_mode(False, start_date, end_date, start_capital, 999.0)
    elif args.mode == '3':
        run_shared_mode(True, start_date, end_date, start_capital, args.target_max_drawdown)
    else:
        run_single_analysis(start_date, end_date, start_capital)

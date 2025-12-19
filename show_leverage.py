import json
import os

def main():
    # --- PFADE FÜR TITANBOT ANPASSEN ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(base_dir, 'settings.json')
    # Hier lag der Unterschied: 'pbot' statt 'stbot'
    configs_dir = os.path.join(base_dir, 'src', 'pbot', 'strategy', 'configs')
    results_path = os.path.join(base_dir, 'artifacts', 'results', 'optimization_results.json')

    print(f"\n{'STRATEGIE / DATEI':<40} | {'HEBEL':<5} | {'RISIKO %':<8}")
    print("-" * 65)

    try:
        # Lese Modus aus settings.json
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        
        live_settings = settings.get('live_trading_settings', {})
        use_auto = live_settings.get('use_auto_optimizer_results', False)
        
        active_files = []

        if use_auto:
            # Autopilot Modus
            print(f"(Modus: Autopilot - Lese aus optimization_results.json)\n")
            if os.path.exists(results_path):
                with open(results_path, 'r') as f:
                    res = json.load(f)
                    active_files = res.get('optimal_portfolio', [])
            else:
                print("Fehler: optimization_results.json nicht gefunden.")
        else:
            # Manueller Modus
            print(f"(Modus: Manuell - Lese aus settings.json)\n")
            strats = live_settings.get('active_strategies', [])
            for s in strats:
                if isinstance(s, dict) and s.get('active'):
                    # Dateinamen rekonstruieren: config_SYMBOLTIMEFRAME.json
                    # Beispiel: ETH/USDT:USDT -> ETHUSDTUSDT
                    symbol_clean = s['symbol'].replace('/', '').replace(':', '')
                    tf = s['timeframe']
                    
                    # Versuche Dateinamen zu finden
                    candidates = [
                        f"config_{symbol_clean}_{tf}.json",
                        f"config_{symbol_clean}_{tf}_macd.json"
                    ]
                    found = False
                    for c in candidates:
                        if os.path.exists(os.path.join(configs_dir, c)):
                            active_files.append(c)
                            found = True
                            break
                    if not found:
                        print(f"WARNUNG: Config für {s['symbol']} {tf} nicht gefunden.")

        # Werte auslesen
        for filename in active_files:
            full_path = os.path.join(configs_dir, filename)
            try:
                with open(full_path, 'r') as f:
                    config_data = json.load(f)
                    risk_data = config_data.get('risk', {})
                    
                    leverage = risk_data.get('leverage', 'N/A')
                    risk_pct = risk_data.get('risk_per_trade_pct', 'N/A')
                    
                    # Strategie-Name schön formatieren (entfernt config_ und .json)
                    display_name = filename.replace('config_', '').replace('.json', '')
                    
                    print(f"{display_name:<40} | {str(leverage):<5} | {str(risk_pct):<8}")
            except Exception as e:
                print(f"Fehler bei {filename}: {e}")

    except Exception as e:
        print(f"Kritischer Fehler: {e}")
    
    print("-" * 65)

if __name__ == "__main__":
    main()

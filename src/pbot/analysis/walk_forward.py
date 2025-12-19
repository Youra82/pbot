# /root/pbot/src/pbot/analysis/walk_forward.py
"""
Walk-Forward Testing Framework
Verhindert Overfitting durch Out-of-Sample Validation
"""
import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.analysis.backtester import load_data, run_pbot_backtest
from pbot.analysis.optimizer import objective as run_single_optimization
import optuna


class WalkForwardTester:
    """
    Walk-Forward Testing Framework
    
    Methodik:
    1. Teile Daten in Fenster (z.B. 6 Monate Training + 2 Monate Testing)
    2. Optimiere auf Training-Window
    3. Teste auf Test-Window (Out-of-Sample)
    4. Rolle Window forward
    5. Aggregiere Ergebnisse
    """
    
    def __init__(self, 
                 training_months: int = 6,
                 testing_months: int = 2,
                 step_months: int = 2):
        """
        Args:
            training_months: Monate für Optimierung
            testing_months: Monate für Out-of-Sample Test
            step_months: Schrittweite für Rolling Window
        """
        self.training_months = training_months
        self.testing_months = testing_months
        self.step_months = step_months
    
    def create_windows(self, 
                       start_date: str, 
                       end_date: str) -> List[Tuple[str, str, str, str]]:
        """
        Erstellt Training/Test Windows
        
        Returns:
            List of (train_start, train_end, test_start, test_end)
        """
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        windows = []
        current_start = start
        
        while True:
            train_end = current_start + timedelta(days=30 * self.training_months)
            test_start = train_end
            test_end = test_start + timedelta(days=30 * self.testing_months)
            
            # Abbruch wenn Test-Window über End-Datum hinausgeht
            if test_end > end:
                break
            
            windows.append((
                current_start.strftime('%Y-%m-%d'),
                train_end.strftime('%Y-%m-%d'),
                test_start.strftime('%Y-%m-%d'),
                test_end.strftime('%Y-%m-%d')
            ))
            
            # Nächstes Window
            current_start += timedelta(days=30 * self.step_months)
        
        return windows
    
    def optimize_window(self, 
                       data: pd.DataFrame,
                       train_start: str,
                       train_end: str,
                       n_trials: int = 50) -> Dict:
        """
        Optimiert auf einem Training-Window
        
        Returns:
            best_params: Dict mit besten Parametern
        """
        # Filter Training Data
        train_data = data.loc[train_start:train_end]
        
        if train_data.empty or len(train_data) < 100:
            return None
        
        print(f"   Optimiere auf {len(train_data)} Candles ({train_start} bis {train_end})")
        
        # Erstelle temporäre Optuna Study
        study = optuna.create_study(direction="maximize")
        
        # Nutze die objective-Funktion aus optimizer.py
        # HINWEIS: Das erfordert globale Variablen zu setzen
        from pbot.analysis.optimizer import HISTORICAL_DATA, CURRENT_SYMBOL, CURRENT_TIMEFRAME
        # Temporär überschreiben
        import pbot.analysis.optimizer as opt_module
        opt_module.HISTORICAL_DATA = train_data
        
        study.optimize(opt_module.objective, n_trials=n_trials, show_progress_bar=False)
        
        if len(study.trials) == 0:
            return None
        
        return study.best_params
    
    def test_window(self,
                   data: pd.DataFrame,
                   test_start: str,
                   test_end: str,
                   strategy_params: Dict,
                   risk_params: Dict,
                   start_capital: float = 1000) -> Dict:
        """
        Testet Parameter auf Out-of-Sample Window
        
        Returns:
            result: Dict mit Performance-Metriken
        """
        test_data = data.loc[test_start:test_end]
        
        if test_data.empty or len(test_data) < 50:
            return None
        
        print(f"   Teste auf {len(test_data)} Candles ({test_start} bis {test_end})")
        
        # Backtest auf Test-Window
        result = run_pbot_backtest(test_data, strategy_params, risk_params, start_capital)
        
        return result
    
    def run_walk_forward(self,
                        symbol: str,
                        timeframe: str,
                        start_date: str,
                        end_date: str,
                        n_trials: int = 50,
                        start_capital: float = 1000) -> Dict:
        """
        Führt kompletten Walk-Forward Test durch
        
        Returns:
            results: Dict mit aggregierten Ergebnissen
        """
        print(f"\n{'='*60}")
        print(f"Walk-Forward Test: {symbol} ({timeframe})")
        print(f"{'='*60}")
        
        # Daten laden
        data = load_data(symbol, timeframe, start_date, end_date)
        if data.empty:
            print("❌ Keine Daten verfügbar")
            return None
        
        # Windows erstellen
        windows = self.create_windows(start_date, end_date)
        print(f"📊 {len(windows)} Walk-Forward Windows erstellt")
        print(f"   Training: {self.training_months} Monate")
        print(f"   Testing: {self.testing_months} Monate")
        print(f"   Step: {self.step_months} Monate\n")
        
        # Durchlaufe alle Windows
        window_results = []
        
        for i, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
            print(f"Window {i}/{len(windows)}:")
            
            # 1. Optimierung
            best_params = self.optimize_window(data, train_start, train_end, n_trials)
            
            if not best_params:
                print("   ⚠️ Optimierung fehlgeschlagen, überspringe Window\n")
                continue
            
            # Extrahiere Strategy & Risk Params
            strategy_params = {k: v for k, v in best_params.items() 
                             if k in ['length', 'rsi_weight', 'wick_weight', 'use_adx_filter', 
                                     'adx_threshold', 'use_mtf', 'min_score']}
            risk_params = {k: v for k, v in best_params.items() 
                          if k not in strategy_params.keys()}
            
            # 2. Out-of-Sample Test
            test_result = self.test_window(data, test_start, test_end, 
                                          strategy_params, risk_params, start_capital)
            
            if not test_result:
                print("   ⚠️ Test fehlgeschlagen, überspringe Window\n")
                continue
            
            # Ergebnisse speichern
            window_results.append({
                'window': i,
                'train_period': f"{train_start} bis {train_end}",
                'test_period': f"{test_start} bis {test_end}",
                'params': best_params,
                'oos_pnl': test_result['total_pnl_pct'],
                'oos_trades': test_result['trades_count'],
                'oos_winrate': test_result['win_rate'],
                'oos_drawdown': test_result['max_drawdown_pct']
            })
            
            print(f"   ✅ OOS Performance: {test_result['total_pnl_pct']:.2f}% "
                  f"({test_result['trades_count']} Trades, WR: {test_result['win_rate']:.1f}%)\n")
        
        # Aggregiere Ergebnisse
        if not window_results:
            print("❌ Keine erfolgreichen Windows")
            return None
        
        avg_oos_pnl = sum(r['oos_pnl'] for r in window_results) / len(window_results)
        avg_trades = sum(r['oos_trades'] for r in window_results) / len(window_results)
        avg_winrate = sum(r['oos_winrate'] for r in window_results) / len(window_results)
        max_drawdown = max(r['oos_drawdown'] for r in window_results)
        
        # Konsistenz-Score: Wie viele Windows waren profitabel?
        profitable_windows = sum(1 for r in window_results if r['oos_pnl'] > 0)
        consistency = (profitable_windows / len(window_results)) * 100
        
        summary = {
            'symbol': symbol,
            'timeframe': timeframe,
            'total_windows': len(window_results),
            'profitable_windows': profitable_windows,
            'consistency_pct': consistency,
            'avg_oos_pnl': avg_oos_pnl,
            'avg_oos_trades': avg_trades,
            'avg_oos_winrate': avg_winrate,
            'max_oos_drawdown': max_drawdown,
            'windows': window_results
        }
        
        print(f"\n{'='*60}")
        print(f"📊 WALK-FORWARD ERGEBNISSE")
        print(f"{'='*60}")
        print(f"Konsistenz: {consistency:.1f}% ({profitable_windows}/{len(window_results)} profitable Windows)")
        print(f"Ø OOS PnL: {avg_oos_pnl:.2f}%")
        print(f"Ø Trades: {avg_trades:.0f}")
        print(f"Ø Win-Rate: {avg_winrate:.1f}%")
        print(f"Max DD: {max_drawdown*100:.1f}%")
        print(f"{'='*60}\n")
        
        # Speichere Ergebnisse
        results_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'results', 'walk_forward')
        os.makedirs(results_dir, exist_ok=True)
        
        safe_filename = f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"
        results_file = os.path.join(results_dir, f"wf_{safe_filename}.json")
        
        with open(results_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"💾 Ergebnisse gespeichert: {results_file}")
        
        return summary


def main():
    """
    Beispiel-Nutzung des Walk-Forward Testers
    """
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--timeframe', required=True)
    parser.add_argument('--start_date', required=True)
    parser.add_argument('--end_date', required=True)
    parser.add_argument('--train_months', type=int, default=6)
    parser.add_argument('--test_months', type=int, default=2)
    parser.add_argument('--step_months', type=int, default=2)
    parser.add_argument('--trials', type=int, default=50)
    
    args = parser.parse_args()
    
    tester = WalkForwardTester(
        training_months=args.train_months,
        testing_months=args.test_months,
        step_months=args.step_months
    )
    
    symbol = f"{args.symbol}/USDT:USDT"
    
    tester.run_walk_forward(
        symbol=symbol,
        timeframe=args.timeframe,
        start_date=args.start_date,
        end_date=args.end_date,
        n_trials=args.trials
    )


if __name__ == '__main__':
    main()

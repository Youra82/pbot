#!/usr/bin/env python3
# show_risk_status.py
"""
Zeigt aktuellen Portfolio-Risk-Status an
"""
import os
import sys
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from pbot.utils.risk_manager import get_risk_manager
from pbot.utils.database import get_trade_db


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def main():
    print_header("📊 PBOT PORTFOLIO RISK STATUS")
    
    # 1. Risk Manager Status
    risk_manager = get_risk_manager()
    status = risk_manager.get_status()
    
    print("\n🛡️ RISK LIMITS:")
    print(f"  Max Concurrent Positions: {risk_manager.max_concurrent_positions}")
    print(f"  Max Daily Loss: {risk_manager.max_daily_loss_pct}%")
    print(f"  Max Total Risk: {risk_manager.max_total_risk_pct}%")
    
    print("\n📈 AKTUELLER STATUS:")
    print(f"  Active Positions: {status['active_positions_count']}/{risk_manager.max_concurrent_positions}")
    if status['active_symbols']:
        print(f"  Symbols: {', '.join(status['active_symbols'])}")
    else:
        print(f"  Symbols: Keine offenen Positionen")
    
    print(f"  Total Risk: {status['total_risk_pct']:.2f}% / {risk_manager.max_total_risk_pct}%")
    print(f"  Daily PnL: {status['daily_pnl_pct']:+.2f}%")
    
    if status['daily_loss_pct'] > 0:
        print(f"  Daily Loss: {status['daily_loss_pct']:.2f}% / {risk_manager.max_daily_loss_pct}%")
        print(f"  Loss Remaining: {status['daily_loss_remaining_pct']:.2f}%")
    
    # Trading Status
    if status['can_trade']:
        print("\n✅ STATUS: Trading AKTIV")
    else:
        print("\n🚫 STATUS: Trading GESTOPPT")
        if status['daily_loss_pct'] >= risk_manager.max_daily_loss_pct:
            print("   Grund: Daily Loss Limit erreicht")
        if status['active_positions_count'] >= risk_manager.max_concurrent_positions:
            print("   Grund: Max Positionen erreicht")
    
    # 2. Database Statistics (falls vorhanden)
    try:
        db = get_trade_db()
        
        # Offene Trades
        open_trades = db.get_open_trades()
        if open_trades:
            print(f"\n📋 OFFENE POSITIONEN ({len(open_trades)}):")
            for trade in open_trades:
                print(f"  • {trade['symbol']} ({trade['side'].upper()}) @ ${trade['entry_price']:.4f}")
                print(f"    Entry: {trade['entry_time']}")
                print(f"    Risk: {trade['risk_pct']:.2f}% (${trade['risk_usd']:.2f})")
        
        # 30-Tage Statistiken
        stats = db.get_trade_statistics(days=30)
        if stats['trades_count'] > 0:
            print(f"\n📊 PERFORMANCE (30 Tage):")
            print(f"  Trades: {stats['trades_count']} ({stats['wins_count']}W / {stats['losses_count']}L)")
            print(f"  Win Rate: {stats['win_rate']:.1f}%")
            print(f"  Total PnL: ${stats['total_pnl_usd']:,.2f}")
            print(f"  Avg per Trade: ${stats['avg_pnl_per_trade']:,.2f}")
            print(f"  Max Win: ${stats['max_win']:,.2f}")
            print(f"  Max Loss: ${stats['max_loss']:,.2f}")
            print(f"  Profit Factor: {stats['profit_factor']:.2f}")
    except Exception as e:
        print(f"\n⚠️ Keine Trade-Statistiken verfügbar: {e}")
    
    print("\n" + "="*60)


if __name__ == '__main__':
    main()

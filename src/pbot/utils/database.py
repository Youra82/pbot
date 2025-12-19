# /root/pbot/src/pbot/utils/database.py
"""
Database Integration für Trade-Logging und Performance-Analyse
Nutzt SQLite für lokale Speicherung, kann später auf PostgreSQL/TimescaleDB migriert werden
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'artifacts', 'db', 'pbot_trades.db')


class TradeDatabase:
    """
    Trade-Logging Database
    Speichert alle Trades persistent für spätere Analyse
    """
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Context Manager für DB-Connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Ermöglicht dict-like access
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """Erstellt die Datenbank-Struktur"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Trades Tabelle
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT UNIQUE,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL,
                    trailing_activation REAL,
                    position_size REAL NOT NULL,
                    notional_value REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    risk_pct REAL NOT NULL,
                    risk_usd REAL NOT NULL,
                    
                    -- Exit Info (NULL solange Position offen)
                    exit_time TIMESTAMP,
                    exit_price REAL,
                    exit_reason TEXT,
                    
                    -- Performance Metrics
                    pnl_usd REAL,
                    pnl_pct REAL,
                    pnl_r REAL,
                    fees_usd REAL,
                    slippage_usd REAL,
                    
                    -- Strategy Info
                    score REAL,
                    is_choppy BOOLEAN,
                    is_low_volume BOOLEAN,
                    atr REAL,
                    htf_bias TEXT,
                    
                    -- Metadata
                    config_file TEXT,
                    strategy_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    status TEXT DEFAULT 'open' -- 'open', 'closed', 'cancelled'
                )
            ''')
            
            # Performance Summary Tabelle (Tages/Wochen/Monats-Stats)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_type TEXT NOT NULL,  -- 'daily', 'weekly', 'monthly'
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    
                    trades_count INTEGER,
                    wins_count INTEGER,
                    losses_count INTEGER,
                    win_rate REAL,
                    
                    total_pnl_usd REAL,
                    total_pnl_pct REAL,
                    avg_pnl_per_trade REAL,
                    
                    max_win REAL,
                    max_loss REAL,
                    avg_win REAL,
                    avg_loss REAL,
                    
                    profit_factor REAL,
                    sharpe_ratio REAL,
                    
                    max_drawdown_pct REAL,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(period_type, period_start)
                )
            ''')
            
            # Indizes für schnellere Queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)')
    
    def log_trade_open(self, trade_info: Dict) -> str:
        """
        Loggt eine neu eröffnete Position
        
        Args:
            trade_info: Dict mit allen Trade-Details
            
        Returns:
            trade_id: Eindeutige Trade-ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            trade_id = f"{trade_info['symbol']}_{trade_info['entry_time'].strftime('%Y%m%d_%H%M%S')}"
            
            cursor.execute('''
                INSERT INTO trades (
                    trade_id, symbol, timeframe, side,
                    entry_time, entry_price, stop_loss, take_profit, trailing_activation,
                    position_size, notional_value, leverage, risk_pct, risk_usd,
                    score, is_choppy, is_low_volume, atr, htf_bias,
                    config_file, strategy_version, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id,
                trade_info['symbol'],
                trade_info['timeframe'],
                trade_info['side'],
                trade_info['entry_time'],
                trade_info['entry_price'],
                trade_info['stop_loss'],
                trade_info.get('take_profit'),
                trade_info.get('trailing_activation'),
                trade_info['position_size'],
                trade_info['notional_value'],
                trade_info['leverage'],
                trade_info['risk_pct'],
                trade_info['risk_usd'],
                trade_info.get('score'),
                trade_info.get('is_choppy', False),
                trade_info.get('is_low_volume', False),
                trade_info.get('atr'),
                trade_info.get('htf_bias'),
                trade_info.get('config_file'),
                trade_info.get('strategy_version', 'v1.0'),
                'open'
            ))
            
            return trade_id
    
    def log_trade_close(self, trade_id: str, close_info: Dict):
        """
        Loggt das Schließen einer Position
        
        Args:
            trade_id: Trade-ID der offenen Position
            close_info: Dict mit Exit-Details
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE trades SET
                    exit_time = ?,
                    exit_price = ?,
                    exit_reason = ?,
                    pnl_usd = ?,
                    pnl_pct = ?,
                    pnl_r = ?,
                    fees_usd = ?,
                    slippage_usd = ?,
                    status = 'closed'
                WHERE trade_id = ?
            ''', (
                close_info['exit_time'],
                close_info['exit_price'],
                close_info['exit_reason'],
                close_info['pnl_usd'],
                close_info['pnl_pct'],
                close_info.get('pnl_r'),
                close_info.get('fees_usd', 0),
                close_info.get('slippage_usd', 0),
                trade_id
            ))
    
    def get_open_trades(self, symbol: Optional[str] = None) -> List[Dict]:
        """Gibt alle offenen Trades zurück"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute('SELECT * FROM trades WHERE status = "open" AND symbol = ?', (symbol,))
            else:
                cursor.execute('SELECT * FROM trades WHERE status = "open"')
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_trade_statistics(self, days: int = 30) -> Dict:
        """
        Berechnet Performance-Statistiken
        
        Args:
            days: Anzahl Tage zurück
            
        Returns:
            Dict mit Performance-Metriken
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Alle geschlossenen Trades der letzten X Tage
            cursor.execute('''
                SELECT * FROM trades 
                WHERE status = 'closed' 
                AND exit_time >= datetime('now', '-' || ? || ' days')
                ORDER BY exit_time DESC
            ''', (days,))
            
            trades = [dict(row) for row in cursor.fetchall()]
            
            if not trades:
                return {
                    'trades_count': 0,
                    'win_rate': 0,
                    'total_pnl_usd': 0,
                    'avg_pnl_per_trade': 0
                }
            
            wins = [t for t in trades if t['pnl_usd'] > 0]
            losses = [t for t in trades if t['pnl_usd'] <= 0]
            
            total_pnl = sum(t['pnl_usd'] for t in trades)
            total_wins = sum(t['pnl_usd'] for t in wins) if wins else 0
            total_losses = abs(sum(t['pnl_usd'] for t in losses)) if losses else 1
            
            return {
                'trades_count': len(trades),
                'wins_count': len(wins),
                'losses_count': len(losses),
                'win_rate': (len(wins) / len(trades) * 100) if trades else 0,
                'total_pnl_usd': total_pnl,
                'avg_pnl_per_trade': total_pnl / len(trades) if trades else 0,
                'max_win': max((t['pnl_usd'] for t in wins), default=0),
                'max_loss': min((t['pnl_usd'] for t in losses), default=0),
                'avg_win': total_wins / len(wins) if wins else 0,
                'avg_loss': total_losses / len(losses) if losses else 0,
                'profit_factor': total_wins / total_losses if total_losses > 0 else 0,
            }


# Singleton-Instanz
_db_instance = None

def get_trade_db() -> TradeDatabase:
    """Gibt die globale Database-Instanz zurück"""
    global _db_instance
    if _db_instance is None:
        _db_instance = TradeDatabase()
    return _db_instance

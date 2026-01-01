# /root/pbot/src/pbot/utils/risk_manager.py
"""
Portfolio-Level Risk Manager
Verhindert Over-Exposure und kontrolliert Gesamt-Risiko
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
RISK_STATE_FILE = os.path.join(PROJECT_ROOT, 'artifacts', 'db', 'risk_state.json')


class PortfolioRiskManager:
    """
    Überwacht Portfolio-weites Risiko und verhindert Over-Exposure
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: Risk-Manager Konfiguration
        """
        self.config = config or {}
        
        # --- KRITISCHE LIMITS ---
        self.max_concurrent_positions = self.config.get('max_concurrent_positions', 3)
        self.max_daily_loss_pct = self.config.get('max_daily_loss_pct', 5.0)
        self.max_total_risk_pct = self.config.get('max_total_risk_pct', 4.0)  # Max 4% Gesamt-Exposure
        self.min_adjusted_risk_pct = self.config.get('min_adjusted_risk_pct', 0.1)  # Minimum sinnvolle Positionsgroesse nach Kappung
        
        # State laden
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Lädt den aktuellen Risk-State"""
        os.makedirs(os.path.dirname(RISK_STATE_FILE), exist_ok=True)
        
        if os.path.exists(RISK_STATE_FILE):
            try:
                with open(RISK_STATE_FILE, 'r') as f:
                    state = json.load(f)
                    
                # Reset Daily Loss zu Mitternacht
                last_reset = datetime.fromisoformat(state.get('last_reset', datetime.now().isoformat()))
                if last_reset.date() < datetime.now().date():
                    state['daily_pnl'] = 0.0
                    state['last_reset'] = datetime.now().isoformat()
                    
                return state
            except Exception:
                pass
        
        # Default State
        return {
            'daily_pnl': 0.0,
            'last_reset': datetime.now().isoformat(),
            'active_positions': {},  # {symbol: risk_pct}
            'total_trades_today': 0
        }
    
    def _save_state(self):
        """Speichert den Risk-State"""
        with open(RISK_STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def can_open_position(self, symbol: str, risk_pct: float, logger=None) -> tuple[bool, str, float]:
        """
        Prüft ob eine neue Position eröffnet werden darf
        
        Args:
            symbol: Trading-Symbol
            risk_pct: Risiko in % des Kontos
            logger: Optional logger
            
        Returns:
            (erlaubt: bool, grund: str, verwendetes_risk_pct: float)
        """
        # 1. Check: Max Concurrent Positions
        active_count = len(self.state['active_positions'])
        if active_count >= self.max_concurrent_positions:
            msg = f"🚫 Max Positionen erreicht ({active_count}/{self.max_concurrent_positions})"
            if logger: logger.warning(msg)
            return False, msg, risk_pct
        
        # 2. Check: Daily Loss Limit
        daily_loss_pct = abs(min(0, self.state['daily_pnl']))
        if daily_loss_pct >= self.max_daily_loss_pct:
            msg = f"🚫 Daily Loss Limit erreicht ({daily_loss_pct:.2f}% / {self.max_daily_loss_pct}%)"
            if logger: logger.warning(msg)
            return False, msg, risk_pct
        
        # 3. Check: Total Risk Exposure
        current_total_risk = sum(self.state['active_positions'].values())
        new_total_risk = current_total_risk + risk_pct
        
        if new_total_risk > self.max_total_risk_pct:
            available_risk = max(self.max_total_risk_pct - current_total_risk, 0.0)
            if available_risk < self.min_adjusted_risk_pct:
                msg = f"🚫 Max Total Risk erreicht ({new_total_risk:.2f}% / {self.max_total_risk_pct}%)"
                if logger: logger.warning(msg)
                return False, msg, risk_pct

            # Kappe die Positionsgroesse auf den noch freien Risiko-Bereich
            adjusted_risk = round(available_risk, 4)
            msg = (
                f"⚠️ Risiko gekappt auf {adjusted_risk:.2f}% wegen Portfolio-Limit "
                f"({current_total_risk:.2f}% / {self.max_total_risk_pct}%)"
            )
            if logger: logger.warning(msg)
            return True, msg, adjusted_risk
        
        # 4. Check: Position bereits offen für dieses Symbol?
        if symbol in self.state['active_positions']:
            msg = f"🚫 Position für {symbol} bereits aktiv"
            if logger: logger.warning(msg)
            return False, msg, risk_pct
        
        return True, "OK", risk_pct
    
    def register_position(self, symbol: str, risk_pct: float, logger=None):
        """
        Registriert eine neu eröffnete Position
        
        Args:
            symbol: Trading-Symbol
            risk_pct: Risiko in % des Kontos
        """
        self.state['active_positions'][symbol] = risk_pct
        self.state['total_trades_today'] += 1
        self._save_state()
        
        if logger:
            active_symbols = list(self.state['active_positions'].keys())
            total_risk = sum(self.state['active_positions'].values())
            logger.info(f"✅ Position registriert: {symbol} (Risiko: {risk_pct:.2f}%)")
            logger.info(f"📊 Portfolio: {len(active_symbols)} Positionen, Total Risk: {total_risk:.2f}%")
    
    def close_position(self, symbol: str, pnl_pct: float, logger=None):
        """
        Registriert eine geschlossene Position
        
        Args:
            symbol: Trading-Symbol
            pnl_pct: Profit/Loss in % des Kontos
        """
        if symbol in self.state['active_positions']:
            risk = self.state['active_positions'].pop(symbol)
            self.state['daily_pnl'] += pnl_pct
            self._save_state()
            
            if logger:
                logger.info(f"🔒 Position geschlossen: {symbol} (PnL: {pnl_pct:+.2f}%)")
                logger.info(f"📊 Daily PnL: {self.state['daily_pnl']:+.2f}%")
    
    def get_status(self) -> Dict:
        """Gibt aktuellen Risk-Status zurück"""
        total_risk = sum(self.state['active_positions'].values())
        daily_loss = abs(min(0, self.state['daily_pnl']))
        
        return {
            'active_positions_count': len(self.state['active_positions']),
            'active_symbols': list(self.state['active_positions'].keys()),
            'total_risk_pct': total_risk,
            'daily_pnl_pct': self.state['daily_pnl'],
            'daily_loss_pct': daily_loss,
            'daily_loss_remaining_pct': max(0, self.max_daily_loss_pct - daily_loss),
            'can_trade': daily_loss < self.max_daily_loss_pct and len(self.state['active_positions']) < self.max_concurrent_positions
        }
    
    def reset_daily_stats(self):
        """Manuelles Reset der Daily-Statistiken (für Testing)"""
        self.state['daily_pnl'] = 0.0
        self.state['last_reset'] = datetime.now().isoformat()
        self.state['total_trades_today'] = 0
        self._save_state()


# Singleton-Instanz für globalen Zugriff
_risk_manager_instance = None

def get_risk_manager(config: Optional[Dict] = None) -> PortfolioRiskManager:
    """
    Gibt die globale Risk-Manager Instanz zurück
    """
    global _risk_manager_instance
    if _risk_manager_instance is None:
        _risk_manager_instance = PortfolioRiskManager(config)
    return _risk_manager_instance

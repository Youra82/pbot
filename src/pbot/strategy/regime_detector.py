# /root/pbot/src/pbot/strategy/regime_detector.py
"""
Market-Regime Detection Module
Erkennt automatisch Marktphasen und passt Strategie-Verhalten an

Regime-Typen:
1. Trending (Bullish/Bearish)
2. Ranging (Sideways/Choppy)
3. Volatile (High-Volatility Breakout Phase)
4. Quiet (Low-Volatility Consolidation)
"""
import pandas as pd
import numpy as np
import ta
from typing import Dict, Literal
from enum import Enum


class MarketRegime(Enum):
    """Definiert verschiedene Marktphasen"""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"
    UNKNOWN = "unknown"


class RegimeDetector:
    """
    Erkennt aktuelle Marktphase basierend auf technischen Indikatoren
    """
    
    def __init__(self, settings: Dict = None):
        """
        Args:
            settings: Konfiguration für Regime-Detection
        """
        self.settings = settings or {}
        
        # Thresholds (können optimiert werden)
        self.adx_trending_threshold = self.settings.get('adx_trending', 25)
        self.adx_strong_trending = self.settings.get('adx_strong', 40)
        
        self.atr_high_threshold = self.settings.get('atr_high_percentile', 80)
        self.atr_low_threshold = self.settings.get('atr_low_percentile', 20)
        
        self.bb_squeeze_threshold = self.settings.get('bb_squeeze', 0.02)
        
    def calculate_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Berechnet alle Indikatoren für Regime-Detection
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            df mit zusätzlichen Regime-Indikatoren
        """
        if df.empty or len(df) < 50:
            return df
        
        # 1. Trend Indicators
        # ADX (Trend Strength)
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()
        df['di_plus'] = adx_ind.adx_pos()
        df['di_minus'] = adx_ind.adx_neg()
        
        # EMA Trend
        df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['ema_200'] = ta.trend.ema_indicator(df['close'], window=200)
        
        # Trend Direction Score
        df['trend_score'] = 0
        df.loc[df['close'] > df['ema_20'], 'trend_score'] += 1
        df.loc[df['close'] > df['ema_50'], 'trend_score'] += 1
        df.loc[df['close'] > df['ema_200'], 'trend_score'] += 1
        df.loc[df['ema_20'] > df['ema_50'], 'trend_score'] += 1
        df.loc[df['ema_50'] > df['ema_200'], 'trend_score'] += 1
        # Score: 0-5 (5 = strongest bull, 0 = strongest bear)
        
        # 2. Volatility Indicators
        # ATR
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # ATR Percentile (für Volatilitäts-Regime)
        df['atr_percentile'] = df['atr_pct'].rolling(100).apply(
            lambda x: (x.iloc[-1] / x.quantile(0.5) - 1) * 100 if len(x) > 0 else 0
        )
        
        # Bollinger Bands Width (Squeeze Detection)
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_width'] = bb.bollinger_wband()
        df['bb_squeeze'] = df['bb_width'] < self.bb_squeeze_threshold
        
        # 3. Volume Indicators
        if 'volume' in df.columns:
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
        else:
            df['volume_ratio'] = 1.0
        
        return df
    
    def detect_regime(self, df: pd.DataFrame) -> Dict:
        """
        Erkennt aktuelles Markt-Regime
        
        Args:
            df: OHLCV DataFrame mit berechneten Indikatoren
            
        Returns:
            Dict mit Regime-Info und Confidence
        """
        df = self.calculate_regime_indicators(df.copy())
        
        if df.empty:
            return {
                'regime': MarketRegime.UNKNOWN,
                'confidence': 0.0,
                'details': {}
            }
        
        # Aktuelle Werte
        current = df.iloc[-1]
        
        adx = current.get('adx', 0)
        di_plus = current.get('di_plus', 0)
        di_minus = current.get('di_minus', 0)
        trend_score = current.get('trend_score', 0)
        atr_percentile = current.get('atr_percentile', 0)
        bb_squeeze = current.get('bb_squeeze', False)
        
        # Regime Logic
        regime = MarketRegime.UNKNOWN
        confidence = 0.0
        
        # 1. VOLATILE - High ATR, oft vor/nach großen Moves
        if atr_percentile > self.atr_high_threshold:
            regime = MarketRegime.VOLATILE
            confidence = min(1.0, atr_percentile / 100)
        
        # 2. QUIET - Low ATR, Squeeze, oft vor Breakouts
        elif atr_percentile < -self.atr_low_threshold or bb_squeeze:
            regime = MarketRegime.QUIET
            confidence = 0.7 if bb_squeeze else 0.5
        
        # 3. TRENDING - High ADX
        elif adx > self.adx_trending_threshold:
            # Bullish Trend
            if di_plus > di_minus and trend_score >= 3:
                regime = MarketRegime.TRENDING_BULL
                confidence = min(1.0, adx / 50)
            # Bearish Trend
            elif di_minus > di_plus and trend_score <= 2:
                regime = MarketRegime.TRENDING_BEAR
                confidence = min(1.0, adx / 50)
            else:
                regime = MarketRegime.RANGING  # ADX hoch, aber keine klare Richtung
                confidence = 0.5
        
        # 4. RANGING - Low ADX
        else:
            regime = MarketRegime.RANGING
            confidence = 1.0 - (adx / self.adx_trending_threshold)
        
        # Details für Debugging/Logging
        details = {
            'adx': round(adx, 2),
            'di_plus': round(di_plus, 2),
            'di_minus': round(di_minus, 2),
            'trend_score': int(trend_score),
            'atr_percentile': round(atr_percentile, 2),
            'bb_squeeze': bool(bb_squeeze)
        }
        
        return {
            'regime': regime,
            'confidence': round(confidence, 2),
            'details': details
        }
    
    def get_strategy_adjustments(self, regime_info: Dict) -> Dict:
        """
        Gibt empfohlene Strategy-Anpassungen für das erkannte Regime zurück
        
        Args:
            regime_info: Output von detect_regime()
            
        Returns:
            Dict mit empfohlenen Parameter-Anpassungen
        """
        regime = regime_info['regime']
        confidence = regime_info['confidence']
        
        # Default: Keine Anpassungen
        adjustments = {
            'risk_multiplier': 1.0,
            'min_score_adjustment': 0.0,
            'allow_trades': True,
            'notes': ''
        }
        
        # Regime-spezifische Anpassungen
        if regime == MarketRegime.TRENDING_BULL or regime == MarketRegime.TRENDING_BEAR:
            # Trending: Höheres Risiko, niedrigere Min-Score Requirement
            adjustments['risk_multiplier'] = 1.0 + (0.3 * confidence)  # Bis +30%
            adjustments['min_score_adjustment'] = -0.2 * confidence  # Niedrigere Hürde
            adjustments['notes'] = 'Trending Market: Erhöhe Risiko, senke Score-Threshold'
        
        elif regime == MarketRegime.RANGING:
            # Ranging: Niedrigeres Risiko, höhere Min-Score Requirement
            adjustments['risk_multiplier'] = 1.0 - (0.3 * confidence)  # Bis -30%
            adjustments['min_score_adjustment'] = 0.3 * confidence  # Höhere Hürde
            adjustments['notes'] = 'Ranging Market: Reduziere Risiko, erhöhe Score-Threshold'
        
        elif regime == MarketRegime.VOLATILE:
            # Volatile: Deutlich niedrigeres Risiko
            adjustments['risk_multiplier'] = 0.5  # 50% Risiko
            adjustments['min_score_adjustment'] = 0.5  # Viel höhere Hürde
            adjustments['notes'] = 'High Volatility: Stark reduziertes Risiko'
        
        elif regime == MarketRegime.QUIET:
            # Quiet: Warte auf Breakout, keine Trades
            adjustments['risk_multiplier'] = 0.7
            adjustments['min_score_adjustment'] = 0.3
            adjustments['notes'] = 'Low Volatility: Reduziertes Risiko, Breakout abwarten'
        
        return adjustments


# Helper Function für einfache Nutzung
def analyze_market_regime(df: pd.DataFrame, settings: Dict = None) -> Dict:
    """
    Convenience-Funktion für schnelle Regime-Analyse
    
    Args:
        df: OHLCV DataFrame
        settings: Optional settings
        
    Returns:
        Dict mit Regime-Info und Adjustments
    """
    detector = RegimeDetector(settings)
    regime_info = detector.detect_regime(df)
    adjustments = detector.get_strategy_adjustments(regime_info)
    
    return {
        **regime_info,
        'adjustments': adjustments
    }


# Beispiel-Nutzung
if __name__ == '__main__':
    """
    Test der Regime Detection
    """
    import sys
    sys.path.append('..')
    
    from pbot.utils.exchange import Exchange
    
    # Lade Test-Daten
    print("Teste Regime Detection...")
    
    # Beispiel-Config (würde normalerweise aus secret.json kommen)
    # detector = RegimeDetector()
    
    print("✅ Regime Detector Module erfolgreich geladen")
    print("\nVerfügbare Regime-Typen:")
    for regime in MarketRegime:
        print(f"  - {regime.value}")

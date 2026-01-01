# /root/pbot/src/pbot/strategy/predictor_engine.py
import pandas as pd
import numpy as np
import ta

class PredictorEngine:
    """
    Python-Implementierung des 'Next Candle Predictor PRO' Pine Scripts.
    Nutzt übergeordneten HTF-Supertrend-Filter als primärer Trend-Filter.
    """
    def __init__(self, settings: dict):
        self.length = settings.get('length', 14)
        self.rsi_weight = settings.get('rsi_weight', 1.5)
        self.wick_weight = settings.get('wick_weight', 1.0)
        self.use_adx = settings.get('use_adx_filter', True)
        self.adx_threshold = settings.get('adx_threshold', 20)
        self.use_mtf = settings.get('use_mtf', True)
        
        # --- Volumen Filter Einstellungen ---
        self.use_volume_filter = settings.get('use_volume_filter', True)
        self.min_volume_ratio = settings.get('min_volume_ratio', 0.5)  # 50% des Durchschnitts
        self.volume_lookback = settings.get('volume_lookback', 20)
        # -----------------------------------
        
        # --- Supertrend Einstellungen (HTF-basiert - IMMER aktiv) ---
        self.st_factor = settings.get('supertrend_factor', 3.0)
        self.st_period = settings.get('supertrend_period', 10)

    def _calculate_supertrend(self, df: pd.DataFrame):
        """
        Berechnet Supertrend Trend für ein DataFrame.
        Gibt ein Array mit 1 (Grün/Long) oder -1 (Rot/Short) zurück.
        """
        if df.empty or len(df) < self.st_period:
            return None
        
        st_atr = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.st_period)
        hl2 = (df['high'] + df['low']) / 2
        basic_upper = hl2 + (self.st_factor * st_atr)
        basic_lower = hl2 - (self.st_factor * st_atr)
        
        close = df['close'].values
        final_upper = np.zeros(len(df))
        final_lower = np.zeros(len(df))
        trend = np.zeros(len(df))
        
        final_upper[0] = basic_upper.iloc[0]
        final_lower[0] = basic_lower.iloc[0]
        trend[0] = 1
        
        for i in range(1, len(df)):
            curr_basic_upper = basic_upper.iloc[i]
            curr_basic_lower = basic_lower.iloc[i]
            prev_final_upper = final_upper[i-1]
            prev_final_lower = final_lower[i-1]
            prev_close = close[i-1]
            curr_close = close[i]
            prev_trend = trend[i-1]
            
            if (curr_basic_upper < prev_final_upper) or (prev_close > prev_final_upper):
                final_upper[i] = curr_basic_upper
            else:
                final_upper[i] = prev_final_upper
            
            if (curr_basic_lower > prev_final_lower) or (prev_close < prev_final_lower):
                final_lower[i] = curr_basic_lower
            else:
                final_lower[i] = prev_final_lower
            
            if prev_trend == 1:
                if curr_close <= final_lower[i]:
                    trend[i] = -1
                else:
                    trend[i] = 1
            else:
                if curr_close >= final_upper[i]:
                    trend[i] = 1
                else:
                    trend[i] = -1
        
        return trend

    def calculate_indicators(self, df: pd.DataFrame):
        """Berechnet alle benötigten Indikatoren (ohne Supertrend - wird vom HTF gemanagt)."""
        # 1. EMAs
        df['ema_fast'] = ta.trend.ema_indicator(df['close'], window=self.length)
        df['ema_slow'] = ta.trend.ema_indicator(df['close'], window=self.length * 2)

        # 2. RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.length)

        # 3. ADX (DMI)
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()

        # 4. ATR (für Volatilität)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.length)

        # 5. Bollinger Bands (für Squeeze Detection)
        bb_ind = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2.0)
        df['bb_width'] = bb_ind.bollinger_wband()
        df['avg_bb_width'] = df['bb_width'].rolling(window=50).mean()
        
        # 6. Volumen-Analyse
        if 'volume' in df.columns:
            df['avg_volume'] = df['volume'].rolling(window=self.volume_lookback).mean()
            df['volume_ratio'] = df['volume'] / df['avg_volume']
        else:
            df['avg_volume'] = 0
            df['volume_ratio'] = 1.0

        return df

    def get_score(self, row, mtf_bullish=None, htf_st_trend=None):
        """
        Berechnet den Score für eine einzelne Kerze.
        HTF-Supertrend ist der primäre Trend-Filter (IMMER aktiv wenn verfügbar).
        """
        # 1. Trend Score (EMA Cross)
        bullish_ema = row['ema_fast'] > row['ema_slow']
        trend_score = 1.0 if bullish_ema else -1.0

        # 2. RSI Bias (Momentum)
        rsi_val = row['rsi'] if not pd.isna(row['rsi']) else 50.0
        rsi_bias = 0.0
        if rsi_val > 70:
            rsi_bias = -1.0 * self.rsi_weight
        elif rsi_val < 30:
            rsi_bias = 1.0 * self.rsi_weight

        # 3. Wick Rejection Bias (Price Action)
        open_p, close_p = row['open'], row['close']
        high_p, low_p = row['high'], row['low']

        body_size = abs(close_p - open_p)
        wick_top = high_p - max(open_p, close_p)
        wick_bot = min(open_p, close_p) - low_p

        rej_bias = 0.0
        # Bearish Rejection (langer Docht oben)
        if wick_top > body_size and wick_top > wick_bot:
            rej_bias = -1.5 * self.wick_weight
        # Bullish Rejection (langer Docht unten)
        elif wick_bot > body_size and wick_bot > wick_top:
            rej_bias = 1.5 * self.wick_weight

        # 4. MTF Penalty (Übergeordneter Trend)
        mtf_penalty = 0.0
        if self.use_mtf and mtf_bullish is not None:
            if bullish_ema and not mtf_bullish:
                mtf_penalty = -1.5 # Strafe für Long gegen MTF
            elif not bullish_ema and mtf_bullish:
                mtf_penalty = 1.5  # Strafe für Short gegen MTF (macht es positiver)

        # Berechne den vorläufigen Score
        raw_score = trend_score + rsi_bias + rej_bias + mtf_penalty
        veto_reason = None
        
        # 5. HTF-Supertrend Veto (Der primäre "Boss"-Filter - IMMER aktiv)
        if htf_st_trend is not None:
            # Fall A: HTF-Supertrend Grün (Nur Longs erlaubt)
            if htf_st_trend == 1:
                if raw_score < 0: 
                    # Signal ist Short (negativ), aber HTF-Trend ist Grün
                    veto_reason = "HTF-ST gruen: blockiert Short-Bias"
                    return 0.0, veto_reason
                
            # Fall B: HTF-Supertrend Rot (Nur Shorts erlaubt)
            elif htf_st_trend == -1:
                if raw_score > 0:
                    # Signal ist Long (positiv), aber HTF-Trend ist Rot
                    veto_reason = "HTF-ST rot: blockiert Long-Bias"
                    return 0.0, veto_reason

        return raw_score, veto_reason

    def analyze(self, df: pd.DataFrame, htf_df: pd.DataFrame = None):
        """
        Hauptfunktion: Verarbeitet die Daten und gibt die letzte Vorhersage zurück.
        HTF-Supertrend ist IMMER der primäre Trend-Filter (keine lokale ST mehr).
        """
        if df.empty: return None

        df = self.calculate_indicators(df.copy())
        current_candle = df.iloc[-1]

        # MTF Logik
        mtf_bullish = None
        if self.use_mtf and htf_df is not None and not htf_df.empty:
            htf_copy = htf_df.copy()
            htf_copy['ema_mtf'] = ta.trend.ema_indicator(htf_copy['close'], window=self.length * 2)
            last_htf = htf_copy.iloc[-1]
            if not pd.isna(last_htf['ema_mtf']):
                mtf_bullish = last_htf['close'] > last_htf['ema_mtf']
        
        # HTF-Supertrend Berechnung (IMMER - primärer Trend-Filter)
        htf_st_trend = None
        if htf_df is not None and not htf_df.empty:
            htf_trend = self._calculate_supertrend(htf_df.copy())
            if htf_trend is not None and len(htf_trend) > 0:
                htf_st_trend = htf_trend[-1]  # Letzter Wert des HTF-Trends

        # Score berechnen (inkl. HTF-Supertrend Check)
        score, veto_reason = self.get_score(current_candle, mtf_bullish, htf_st_trend)

        # Choppy Check (ADX)
        is_choppy = False
        if self.use_adx:
            adx_val = current_candle['adx'] if not pd.isna(current_candle['adx']) else 0
            if adx_val < self.adx_threshold:
                is_choppy = True

        # Squeeze Check (Bollinger)
        is_squeeze = False
        if not pd.isna(current_candle['bb_width']) and not pd.isna(current_candle['avg_bb_width']):
            if current_candle['bb_width'] < (current_candle['avg_bb_width'] * 0.8):
                is_squeeze = True
        
        # Volumen Check (Low-Liquidity vermeiden)
        is_low_volume = False
        if self.use_volume_filter:
            volume_ratio = current_candle.get('volume_ratio', 1.0)
            if not pd.isna(volume_ratio) and volume_ratio < self.min_volume_ratio:
                is_low_volume = True

        return {
            "score": score,
            "supertrend_veto": veto_reason,
            "is_choppy": is_choppy,
            "is_squeeze": is_squeeze,
            "is_low_volume": is_low_volume,
            "atr": current_candle['atr'],
            "close": current_candle['close'],
            "mtf_bullish": mtf_bullish,
            "htf_st_trend": htf_st_trend,
            "volume_ratio": current_candle.get('volume_ratio', 1.0)
        }

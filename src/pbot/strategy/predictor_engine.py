# /root/pbot/src/pbot/strategy/predictor_engine.py
import pandas as pd
import numpy as np
import ta

class PredictorEngine:
    """
    Python-Implementierung des 'Next Candle Predictor PRO' Pine Scripts.
    UPDATE: Mit integriertem Supertrend-Filter (Veto-Logik).
    """
    def __init__(self, settings: dict):
        self.length = settings.get('length', 14)
        self.rsi_weight = settings.get('rsi_weight', 1.5)
        self.wick_weight = settings.get('wick_weight', 1.0)
        self.use_adx = settings.get('use_adx_filter', True)
        self.adx_threshold = settings.get('adx_threshold', 20)
        self.use_mtf = settings.get('use_mtf', True)
        
        # --- Supertrend Einstellungen ---
        # Wir aktivieren den Filter standardmäßig
        self.use_supertrend_filter = settings.get('use_supertrend_filter', True) 
        self.st_factor = 3.0
        self.st_period = 10

    def calculate_indicators(self, df: pd.DataFrame):
        """Berechnet alle benötigten Indikatoren inkl. Supertrend."""
        # 1. EMAs
        df['ema_fast'] = ta.trend.ema_indicator(df['close'], window=self.length)
        df['ema_slow'] = ta.trend.ema_indicator(df['close'], window=self.length * 2)

        # 2. RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.length)

        # 3. ADX (DMI)
        adx_ind = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()

        # 4. ATR (für Volatilität & Supertrend)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.length)

        # 5. --- Supertrend Berechnung (Manuell & Robust) ---
        # Wir nutzen eine numpy-basierte Berechnung für Geschwindigkeit
        
        # Basis-ATR für Supertrend (meist Period 10, Factor 3)
        st_atr = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.st_period)
        
        # HL2 (High+Low)/2
        hl2 = (df['high'] + df['low']) / 2
        
        # Basic Bands
        basic_upper = hl2 + (self.st_factor * st_atr)
        basic_lower = hl2 - (self.st_factor * st_atr)
        
        # Initialisierung der Arrays für die iterative Berechnung
        close = df['close'].values
        final_upper = np.zeros(len(df))
        final_lower = np.zeros(len(df))
        supertrend = np.zeros(len(df))
        trend = np.zeros(len(df)) # 1 = Grün/Long, -1 = Rot/Short
        
        # Erster Wert Initialisierung
        final_upper[0] = basic_upper.iloc[0]
        final_lower[0] = basic_lower.iloc[0]
        trend[0] = 1

        # Iterative Berechnung (Numba-Style Logik)
        for i in range(1, len(df)):
            curr_basic_upper = basic_upper.iloc[i]
            curr_basic_lower = basic_lower.iloc[i]
            prev_final_upper = final_upper[i-1]
            prev_final_lower = final_lower[i-1]
            prev_close = close[i-1]
            curr_close = close[i]
            prev_trend = trend[i-1]

            # Final Upper Band Calculation
            if (curr_basic_upper < prev_final_upper) or (prev_close > prev_final_upper):
                final_upper[i] = curr_basic_upper
            else:
                final_upper[i] = prev_final_upper

            # Final Lower Band Calculation
            if (curr_basic_lower > prev_final_lower) or (prev_close < prev_final_lower):
                final_lower[i] = curr_basic_lower
            else:
                final_lower[i] = prev_final_lower

            # Trend Calculation
            if prev_trend == 1: # War Long (Grün)
                if curr_close <= final_lower[i]:
                    trend[i] = -1 # Wechsel zu Short (Rot)
                else:
                    trend[i] = 1
            else: # War Short (Rot)
                if curr_close >= final_upper[i]:
                    trend[i] = 1 # Wechsel zu Long (Grün)
                else:
                    trend[i] = -1
            
            # Supertrend Wert setzen (für Plotting, hier zweitrangig)
            if trend[i] == 1:
                supertrend[i] = final_lower[i]
            else:
                supertrend[i] = final_upper[i]

        df['st_trend'] = trend
        # ---------------------------------------------------

        # 6. Bollinger Bands (für Squeeze Detection)
        bb_ind = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2.0)
        df['bb_width'] = bb_ind.bollinger_wband()
        df['avg_bb_width'] = df['bb_width'].rolling(window=50).mean()

        return df

    def get_score(self, row, mtf_bullish=None):
        """
        Berechnet den Score für eine einzelne Kerze.
        Nutzt Indikatoren UND das Supertrend-Veto.
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
        
        # 5. Supertrend Veto (Der "Boss"-Filter)
        if self.use_supertrend_filter:
            st_trend = row['st_trend'] # 1.0 (Grün) oder -1.0 (Rot)
            
            # Fall A: Supertrend Grün (Nur Longs erlaubt)
            if st_trend == 1:
                if raw_score < 0: 
                    # Signal ist Short (negativ), aber Trend ist Grün
                    return 0.0 # VETO! Neutralisieren.
                
            # Fall B: Supertrend Rot (Nur Shorts erlaubt)
            elif st_trend == -1:
                if raw_score > 0:
                    # Signal ist Long (positiv), aber Trend ist Rot
                    return 0.0 # VETO! Neutralisieren.

        return raw_score

    def analyze(self, df: pd.DataFrame, htf_df: pd.DataFrame = None):
        """
        Hauptfunktion: Verarbeitet die Daten und gibt die letzte Vorhersage zurück.
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

        # Score berechnen (inkl. Supertrend Check)
        score = self.get_score(current_candle, mtf_bullish)

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

        return {
            "score": score,
            "is_choppy": is_choppy,
            "is_squeeze": is_squeeze,
            "atr": current_candle['atr'],
            "close": current_candle['close'],
            "mtf_bullish": mtf_bullish,
            "st_trend": current_candle.get('st_trend', 0)
        }

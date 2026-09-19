import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ==========================================
# 1. CSV FILE SE SYMBOLS LOAD KARO
# ==========================================
@st.cache_data
def load_symbols():
    try:
        df = pd.read_csv("nifty250.csv")
        # Column ke naam ke aage-peeche ki space hatao
        df.columns = df.columns.str.strip()
        
        if 'Symbol' not in df.columns:
            st.error("CSV file mein 'Symbol' column nahi mila. Kripya file check karein.")
            return []
            
        # Symbols nikalo, spaces hatao, aur .NS lagao
        symbols = df['Symbol'].dropna().astype(str).str.strip().tolist()
        # Dummy ya fake symbols ko hatao
        symbols = [s + ".NS" for s in symbols if s and s != "DUMMYHEG"]
        return symbols
    except Exception as e:
        st.error(f"CSV file load nahi hui: {e}")
        return []

NIFTY250 = load_symbols()

# ==========================================
# 2. YAHOO FINANCE SE DATA FETCH KARO (With Caching)
# ==========================================
@st.cache_data(ttl=3600)
def get_data(symbol, period="6mo", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         progress=False, auto_adjust=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

# ==========================================
# 3. TECHNICAL INDICATORS CALCULATE KARO
# ==========================================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def add_indicators(df):
    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["RSI"] = rsi(df["Close"], 14)
    df["ATR"] = atr(df, 14)
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    df["MACD"] = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return df

# ==========================================
# 4. SIGNAL LOGIC (Swing & Intraday)
# ==========================================
def swing_signal(df):
    last = df.iloc[-1]
    score = 0
    reasons = []

    if last["Close"] > last["EMA20"] > last["EMA50"]:
        score += 1
        reasons.append("EMA20 > EMA50")
    if last["RSI"] > 55:
        score += 1
        reasons.append("RSI > 55")
    if last["MACD"] > last["MACD_Signal"]:
        score += 1
        reasons.append("MACD bullish")
    if last["Close"] > df["High"].rolling(20).max().iloc[-2]:
        score += 1
        reasons.append("20-day breakout")
    if last["Volume"] > last["VolAvg20"] * 1.5:
        score += 1
        reasons.append("Volume spike")

    signal = "BUY" if score >= 4 else "WATCH" if score >= 3 else "AVOID"
    entry = round(float(last["Close"]), 2)
    sl = round(entry - 1.5 * float(last["ATR"]), 2)
    target = round(entry + 3.0 * float(last["ATR"]), 2)

    return {
        "Signal": signal, "Score": score, "Entry": entry,
        "StopLoss": sl, "Target": target, "Reasons": ", ".join(reasons)
    }

def intraday_signal(df):
    last = df.iloc[-1]
    score = 0
    reasons = []

    if last["Close"] > last["VWAP"]:
        score += 1
        reasons.append("Above VWAP")
    if last["EMA9"] > last["EMA21"]:
        score += 1
        reasons.append("EMA9 > EMA21")
    if last["RSI"] > 60:
        score += 1
        reasons.append("RSI > 60")
    if last["Volume"] > last["VolAvg20"] * 1.5:
        score += 1
        reasons.append("Volume spike")

    signal = "BUY" if score >= 3 else "WATCH" if score == 2 else "AVOID"
    entry = round(float(last["Close"]), 2)
    sl = round(entry - 1.0 * float(last["ATR"]), 2)
    target = round(entry + 1.5 * float(last["ATR"]), 2)

    return {
        "Signal": signal, "Score": score, "Entry": entry,
        "StopLoss": sl, "Target": target, "Reasons": ", ".join(reasons)
    }

# ==========================================
# 5. STREAMLIT APP UI
# ==========================================
st.set_page_config(page_title="Nifty 250 Screener", layout="wide")
st.title("📈 Nifty 250 Stock Screener")
st.caption("Swing + Intraday signals — Educational purpose only. Not SEBI registered advice.")

mode = st.sidebar.radio("Mode", ["Swing (Daily)", "Intraday (15m)"])

if mode.startswith("Swing"):
    period, interval = "6mo", "1d"
else:
    period, interval = "5d", "15m"

if st.button("Scan Nifty 250"):
    if not NIFTY250:
        st.error("Symbols load nahi hue. Pehle 'nifty250.csv' upload karo.")
    else:
        rows = []
        progress = st.progress(0)
        status = st.empty()
        total = len(NIFTY250)

        for i, sym in enumerate(NIFTY250):
            status.text(f"Scanning: {sym} ({i+1}/{total})")
            try:
                df = get_data(sym, period, interval)
                if df is None or len(df) < 50:
                    continue
                df = add_indicators(df)
                res = swing_signal(df) if mode.startswith("Swing") else intraday_signal(df)
                res["Symbol"] = sym.replace(".NS", "")
                rows.append(res)
            except Exception:
                pass
            progress.progress((i + 1) / total)

        status.text("Scan complete!")
        
        if rows:
            out = pd.DataFrame(rows)
            cols = ["Symbol", "Signal", "Score", "Entry", "StopLoss", "Target", "Reasons"]
            # Sirf BUY aur WATCH dikhao
            filtered = out[out["Signal"].isin(["BUY", "WATCH"])]
            
            if not filtered.empty:
                st.dataframe(
                    filtered[cols].sort_values(["Signal", "Score"], ascending=False),
                    use_container_width=True
                )
                st.success(f"Total {len(filtered)} stocks mile jinme BUY ya WATCH signal hai.")
            else:
                st.warning("Aaj koi stock BUY ya WATCH criteria pe khara nahi utra.")
        else:
            st.warning("Koi signal nahi mila ya data error aaya. Thodi der baad try karein.")

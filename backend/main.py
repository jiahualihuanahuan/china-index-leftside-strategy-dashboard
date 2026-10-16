from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime
import uvicorn

app = FastAPI(title="China Index Leftside Strategy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_MAP = {
    "沪深300 (CSI 300)": "sh000300",
    "中证500 (CSI 500)": "sh000905",
    "中证1000 (CSI 1000)": "sh000852",
    "上证50 (SSE 50)": "sh000016",
    "创业板指 (ChiNext)": "sz399006",
}

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - macd_signal
    return macd, macd_signal, hist

def compute_bb(series: pd.Series, period=20, std=2.0):
    mid = series.rolling(period).mean()
    stddev = series.rolling(period).std()
    upper = mid + std * stddev
    lower = mid - std * stddev
    return mid, upper, lower

def load_index_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = ak.stock_zh_index_daily(symbol=symbol)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    mask = (df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))
    return df[mask].copy()

def add_indicators(df: pd.DataFrame, rsi_period=14, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0):
    df = df.copy()
    df['rsi'] = compute_rsi(df['close'], rsi_period)
    df['macd'], df['macd_signal'], df['macd_hist'] = compute_macd(df['close'], macd_fast, macd_slow, macd_signal)
    df['bb_mid'], df['bb_upper'], df['bb_lower'] = compute_bb(df['close'], bb_period, bb_std)
    return df

def backtest_leftside(
    df: pd.DataFrame,
    entry_rsi: float,
    add_rsi: float,
    reduce_rsi: float,
    full_exit_rsi: float,
    max_layers: int = 4,
    layer_pct: float = 0.25,
    use_bb_filter: bool = False,
    use_macd_filter: bool = False,
    initial_capital: float = 100000.0,
    commission: float = 0.0003
) -> dict:
    if df.empty or 'rsi' not in df.columns:
        return {"total_return": 0, "win_rate": 0, "trades": 0, "max_dd": 0, "sharpe": 0, "equity": [], "dates": []}

    cash = initial_capital
    position = 0.0
    layers = 0
    equity_curve = []
    trades = []
    entry_prices = []
    current_trade_start = None

    prices = df['close'].values
    rsis = df['rsi'].values
    dates = df['date'].values
    bb_lower = df['bb_lower'].values if 'bb_lower' in df.columns else np.full(len(df), np.nan)
    macd_hist = df['macd_hist'].values if 'macd_hist' in df.columns else np.zeros(len(df))

    for i in range(len(df)):
        price = prices[i]
        rsi = rsis[i]
        if np.isnan(rsi) or price <= 0:
            equity_curve.append(cash + position * price)
            continue

        if layers < max_layers:
            target = entry_rsi if layers == 0 else add_rsi
            buy_ok = rsi < target
            if use_bb_filter:
                buy_ok = buy_ok and (not np.isnan(bb_lower[i])) and (price <= bb_lower[i] * 1.01)
            if use_macd_filter:
                buy_ok = buy_ok and (macd_hist[i] > 0 or (i > 0 and macd_hist[i] > macd_hist[i-1]))
            if buy_ok:
                invest = initial_capital * layer_pct
                if cash >= invest * (1 + commission):
                    shares = invest / price
                    cost = shares * price * (1 + commission)
                    cash -= cost
                    position += shares
                    layers += 1
                    entry_prices.append(price)
                    if current_trade_start is None:
                        current_trade_start = i

        if layers > 0:
            if rsi > full_exit_rsi:
                if position > 0:
                    proceeds = position * price * (1 - commission)
                    cash += proceeds
                    avg_entry = np.mean(entry_prices) if entry_prices else price
                    pnl_pct = (price / avg_entry - 1) * 100
                    trades.append({
                        "entry_date": str(dates[current_trade_start]) if current_trade_start is not None else str(dates[i]),
                        "exit_date": str(dates[i]),
                        "pnl_pct": pnl_pct,
                        "layers": layers
                    })
                    position = 0
                    layers = 0
                    entry_prices = []
                    current_trade_start = None
            elif rsi > reduce_rsi and layers > 0:
                sell_shares = position / layers if layers > 0 else 0
                if sell_shares > 0:
                    proceeds = sell_shares * price * (1 - commission)
                    cash += proceeds
                    position -= sell_shares
                    layers -= 1
                    if entry_prices:
                        entry_prices.pop()
                    if layers == 0 and current_trade_start is not None:
                        trades.append({
                            "entry_date": str(dates[current_trade_start]),
                            "exit_date": str(dates[i]),
                            "pnl_pct": (price / (entry_prices[0] if entry_prices else price) - 1) * 100 if entry_prices else 0,
                            "layers": 1
                        })
                        current_trade_start = None
                        entry_prices = []

        equity = cash + position * price
        equity_curve.append(equity)

    final_equity = cash + position * prices[-1] if len(prices) > 0 else initial_capital
    total_return = (final_equity / initial_capital - 1) * 100

    wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0.0

    eq = np.array(equity_curve)
    if len(eq) > 1:
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.where(peak > 0, peak, 1)
        max_dd = abs(dd.min()) * 100
        daily_ret = np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1)
        sharpe = (np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)) if np.std(daily_ret) > 0 else 0.0
    else:
        max_dd = 0.0
        sharpe = 0.0

    return {
        "total_return": round(float(total_return), 2),
        "win_rate": round(float(win_rate), 2),
        "trades": len(trades),
        "max_dd": round(float(max_dd), 2),
        "sharpe": round(float(sharpe), 2),
        "final_equity": round(float(final_equity), 2),
        "equity": [float(x) for x in equity_curve],
        "dates": [str(d)[:10] for d in dates],
    }

class BacktestRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    rsi_period: int = 14
    entry_rsi: float = 35
    add_rsi: float = 25
    reduce_rsi: float = 65
    full_exit_rsi: float = 75
    max_layers: int = 4
    use_bb_filter: bool = False
    use_macd_filter: bool = False
    bb_period: int = 20
    bb_std: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26

@app.get("/api/indices")
def get_indices():
    return {"indices": list(INDEX_MAP.keys()), "map": INDEX_MAP}

@app.post("/api/backtest")
def run_backtest(req: BacktestRequest):
    try:
        raw_df = load_index_data(req.symbol, req.start_date, req.end_date)
        if raw_df.empty:
            return {"error": "无数据"}
        df = add_indicators(
            raw_df,
            rsi_period=req.rsi_period,
            macd_fast=req.macd_fast,
            macd_slow=req.macd_slow,
            bb_period=req.bb_period,
            bb_std=req.bb_std,
        )
        result = backtest_leftside(
            df,
            entry_rsi=req.entry_rsi,
            add_rsi=req.add_rsi,
            reduce_rsi=req.reduce_rsi,
            full_exit_rsi=req.full_exit_rsi,
            max_layers=req.max_layers,
            use_bb_filter=req.use_bb_filter,
            use_macd_filter=req.use_macd_filter,
        )
        chart_data = {
            "dates": df['date'].dt.strftime('%Y-%m-%d').tolist(),
            "open": df['open'].tolist(),
            "high": df['high'].tolist(),
            "low": df['low'].tolist(),
            "close": df['close'].tolist(),
            "volume": df['volume'].tolist(),
            "rsi": df['rsi'].fillna(0).tolist(),
            "bb_upper": df['bb_upper'].fillna(0).tolist(),
            "bb_mid": df['bb_mid'].fillna(0).tolist(),
            "bb_lower": df['bb_lower'].fillna(0).tolist(),
            "macd": df['macd'].fillna(0).tolist(),
            "macd_signal": df['macd_signal'].fillna(0).tolist(),
            "macd_hist": df['macd_hist'].fillna(0).tolist(),
        }
        return {"metrics": result, "chart": chart_data}
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

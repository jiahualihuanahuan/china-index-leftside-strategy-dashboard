import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import akshare as ak
from datetime import datetime
import itertools

st.set_page_config(page_title="股指左侧交易策略回测仪表盘", layout="wide", page_icon="📈")

st.title("📈 中国股指左侧交易策略回测仪表盘")
st.markdown("越跌越买 + 分批卖出 | RSI / MACD / 布林带共振 | 参数实时调节")

# ---------- 指标计算 ----------
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

@st.cache_data(ttl=3600)
def load_index_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = ak.stock_zh_index_daily(symbol=symbol)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    mask = (df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))
    df = df[mask].copy()
    return df

def add_indicators(df: pd.DataFrame, rsi_period=14, macd_fast=12, macd_slow=26, macd_signal=9, bb_period=20, bb_std=2.0):
    df = df.copy()
    df['rsi'] = compute_rsi(df['close'], rsi_period)
    df['macd'], df['macd_signal'], df['macd_hist'] = compute_macd(df['close'], macd_fast, macd_slow, macd_signal)
    df['bb_mid'], df['bb_upper'], df['bb_lower'] = compute_bb(df['close'], bb_period, bb_std)
    return df

# ---------- 回测引擎（分批买卖） ----------
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

        # ---------- 买入 / 加仓（越跌越买） ----------
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

        # ---------- 分批卖出 ----------
        if layers > 0:
            if rsi > full_exit_rsi:
                if position > 0:
                    proceeds = position * price * (1 - commission)
                    cash += proceeds
                    avg_entry = np.mean(entry_prices) if entry_prices else price
                    pnl_pct = (price / avg_entry - 1) * 100
                    trades.append({
                        "entry_date": dates[current_trade_start] if current_trade_start is not None else dates[i],
                        "exit_date": dates[i],
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
                            "entry_date": dates[current_trade_start],
                            "exit_date": dates[i],
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
        "total_return": round(total_return, 2),
        "win_rate": round(win_rate, 2),
        "trades": len(trades),
        "max_dd": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "final_equity": round(final_equity, 2),
        "equity": equity_curve,
        "dates": dates.tolist(),
        "params": {
            "entry": entry_rsi, "add": add_rsi, "reduce": reduce_rsi, "full_exit": full_exit_rsi,
            "layers": max_layers, "bb": use_bb_filter, "macd": use_macd_filter
        }
    }

# ---------- UI ----------
INDEX_MAP = {
    "沪深300 (CSI 300)": "sh000300",
    "中证500 (CSI 500)": "sh000905",
    "中证1000 (CSI 1000)": "sh000852",
    "上证50 (SSE 50)": "sh000016",
    "创业板指 (ChiNext)": "sz399006",
}

with st.sidebar:
    st.header("基础设置")
    index_name = st.selectbox("选择股指", list(INDEX_MAP.keys()), index=0)
    symbol = INDEX_MAP[index_name]

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("开始日期", value=datetime(2020, 1, 1))
    with col2:
        end_date = st.date_input("结束日期", value=datetime.now().date())

    st.subheader("RSI 参数（实时生效）")
    rsi_period = st.slider("RSI 周期", 6, 30, 14)
    entry_rsi = st.slider("入场 RSI（首仓）", 20, 50, 35)
    add_rsi = st.slider("加仓 RSI（更低）", 10, 40, 25)
    reduce_rsi = st.slider("开始分批卖出 RSI", 50, 80, 65)
    full_exit_rsi = st.slider("全部清仓 RSI", 60, 90, 75)
    max_layers = st.slider("最大加仓层数", 2, 8, 4)

    st.subheader("共振指标")
    use_bb = st.checkbox("启用布林带下轨共振过滤", value=False)
    use_macd = st.checkbox("启用 MACD 共振过滤", value=False)
    bb_period = st.slider("布林带周期", 10, 40, 20) if use_bb else 20
    bb_std = st.slider("布林带标准差倍数", 1.0, 3.0, 2.0, 0.1) if use_bb else 2.0
    macd_fast = st.slider("MACD 快线", 6, 20, 12) if use_macd else 12
    macd_slow = st.slider("MACD 慢线", 20, 40, 26) if use_macd else 26

    st.caption("调整任意滑块后，图表与回测结果会立即更新。")

# 主区域 - 实时回测
with st.spinner("加载数据并计算指标..."):
    raw_df = load_index_data(symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    if raw_df.empty:
        st.error("该时间区间无数据，请调整日期。")
        st.stop()
    df = add_indicators(raw_df, rsi_period=rsi_period, macd_fast=macd_fast, macd_slow=macd_slow,
                        bb_period=bb_period, bb_std=bb_std)

result = backtest_leftside(
    df,
    entry_rsi=entry_rsi,
    add_rsi=add_rsi,
    reduce_rsi=reduce_rsi,
    full_exit_rsi=full_exit_rsi,
    max_layers=max_layers,
    use_bb_filter=use_bb,
    use_macd_filter=use_macd
)

# 指标摘要
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("总收益率", f"{result['total_return']:.2f}%")
c2.metric("胜率", f"{result['win_rate']:.1f}%")
c3.metric("交易次数", result['trades'])
c4.metric("最大回撤", f"{result['max_dd']:.2f}%")
c5.metric("Sharpe", f"{result['sharpe']:.2f}")

# 图表
st.subheader(f"📊 {index_name} 核心图表")
fig = make_subplots(
    rows=4, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=[0.40, 0.20, 0.20, 0.20],
    subplot_titles=("K线 + 布林带", "RSI", "MACD", "策略权益 vs 买入持有"),
    specs=[[{"secondary_y": True}], [{}], [{}], [{}]]
)

fig.add_trace(go.Candlestick(
    x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
    name="K线", increasing_line_color="#ef5350", decreasing_line_color="#26a69a"
), row=1, col=1, secondary_y=False)

fig.add_trace(go.Scatter(x=df['date'], y=df['bb_upper'], name="BB上轨", line=dict(color="gray", width=1, dash="dot")), row=1, col=1)
fig.add_trace(go.Scatter(x=df['date'], y=df['bb_mid'], name="BB中轨", line=dict(color="orange", width=1)), row=1, col=1)
fig.add_trace(go.Scatter(x=df['date'], y=df['bb_lower'], name="BB下轨", line=dict(color="gray", width=1, dash="dot"), fill='tonexty', fillcolor='rgba(128,128,128,0.05)'), row=1, col=1)

colors = ["#ef5350" if c >= o else "#26a69a" for c, o in zip(df['close'], df['open'])]
fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="成交量", marker_color=colors, opacity=0.3), row=1, col=1, secondary_y=True)

fig.add_trace(go.Scatter(x=df['date'], y=df['rsi'], name="RSI", line=dict(color="#ff9800")), row=2, col=1)
fig.add_hline(y=entry_rsi, line_dash="dash", line_color="green", row=2, col=1, annotation_text="入场")
fig.add_hline(y=add_rsi, line_dash="dash", line_color="blue", row=2, col=1, annotation_text="加仓")
fig.add_hline(y=reduce_rsi, line_dash="dash", line_color="orange", row=2, col=1, annotation_text="分批卖")
fig.add_hline(y=full_exit_rsi, line_dash="dash", line_color="red", row=2, col=1, annotation_text="清仓")

fig.add_trace(go.Bar(x=df['date'], y=df['macd_hist'], name="MACD柱", marker_color=np.where(df['macd_hist'] >= 0, "#ef5350", "#26a69a")), row=3, col=1)
fig.add_trace(go.Scatter(x=df['date'], y=df['macd'], name="MACD", line=dict(color="#2196f3")), row=3, col=1)
fig.add_trace(go.Scatter(x=df['date'], y=df['macd_signal'], name="Signal", line=dict(color="#ff5722")), row=3, col=1)

eq_dates = pd.to_datetime(result["dates"])
fig.add_trace(go.Scatter(x=eq_dates, y=result["equity"], name="策略权益", line=dict(color="#2196f3", width=2), fill="tozeroy", fillcolor="rgba(33,150,243,0.1)"), row=4, col=1)
bh = df['close'] / df['close'].iloc[0] * 100000
fig.add_trace(go.Scatter(x=df['date'], y=bh, name="买入持有", line=dict(color="#9e9e9e", dash="dot")), row=4, col=1)

fig.update_layout(height=1100, xaxis_rangeslider_visible=False, showlegend=True,
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                  margin=dict(l=40, r=40, t=80, b=40))
fig.update_yaxes(title_text="价格", row=1, col=1, secondary_y=False)
fig.update_yaxes(title_text="成交量", row=1, col=1, secondary_y=True, showgrid=False)
fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
fig.update_yaxes(title_text="MACD", row=3, col=1)
fig.update_yaxes(title_text="权益", row=4, col=1)

st.plotly_chart(fig, use_container_width=True)

st.info(f"""
**当前策略逻辑**：
- RSI < {entry_rsi} 建立首仓，RSI < {add_rsi} 继续加仓（最多 {max_layers} 层，每层初始资金 25%）
- RSI > {reduce_rsi} 开始分批卖出（每次卖一层）
- RSI > {full_exit_rsi} 全部清仓
- 布林带过滤: {'开启（价格接近下轨才买）' if use_bb else '关闭'}
- MACD 过滤: {'开启' if use_macd else '关闭'}
""")

with st.expander("🔍 参数扫描排名（点击展开后运行）"):
    if st.button("运行 RSI 组合扫描"):
        param_grid = {
            "entry_rsi": [30, 35, 40],
            "add_rsi": [20, 25],
            "reduce_rsi": [60, 65, 70],
            "full_exit_rsi": [70, 75, 80],
            "max_layers": [max_layers]
        }
        results = []
        for combo in itertools.product(*param_grid.values()):
            p = dict(zip(param_grid.keys(), combo))
            if p["add_rsi"] >= p["entry_rsi"] or p["reduce_rsi"] >= p["full_exit_rsi"]:
                continue
            res = backtest_leftside(df, **{k: p[k] for k in ["entry_rsi", "add_rsi", "reduce_rsi", "full_exit_rsi", "max_layers"]},
                                    use_bb_filter=use_bb, use_macd_filter=use_macd)
            res.update(p)
            results.append(res)
        if results:
            rdf = pd.DataFrame(results).sort_values(["total_return", "win_rate"], ascending=False)
            st.dataframe(rdf[["entry_rsi", "add_rsi", "reduce_rsi", "full_exit_rsi", "total_return", "win_rate", "trades", "max_dd", "sharpe"]].head(15),
                         use_container_width=True)

st.caption("数据来源：akshare | 回测为历史模拟，不构成投资建议。交易成本按万分之三估算。")

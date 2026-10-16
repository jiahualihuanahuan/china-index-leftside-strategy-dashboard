import { useState, useEffect } from 'react'
import Plot from 'react-plotly.js'

const INDICES = [
  { name: "沪深300 (CSI 300)", symbol: "sh000300" },
  { name: "中证500 (CSI 500)", symbol: "sh000905" },
  { name: "中证1000 (CSI 1000)", symbol: "sh000852" },
  { name: "上证50 (SSE 50)", symbol: "sh000016" },
  { name: "创业板指 (ChiNext)", symbol: "sz399006" },
]

export default function App() {
  const [symbol, setSymbol] = useState("sh000300")
  const [startDate, setStartDate] = useState("2020-01-01")
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10))
  const [rsiPeriod, setRsiPeriod] = useState(14)
  const [entryRsi, setEntryRsi] = useState(35)
  const [addRsi, setAddRsi] = useState(25)
  const [reduceRsi, setReduceRsi] = useState(65)
  const [fullExitRsi, setFullExitRsi] = useState(75)
  const [maxLayers, setMaxLayers] = useState(4)
  const [useBb, setUseBb] = useState(false)
  const [useMacd, setUseMacd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState("")

  const runBacktest = async () => {
    setLoading(true)
    setError("")
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          start_date: startDate,
          end_date: endDate,
          rsi_period: rsiPeriod,
          entry_rsi: entryRsi,
          add_rsi: addRsi,
          reduce_rsi: reduceRsi,
          full_exit_rsi: fullExitRsi,
          max_layers: maxLayers,
          use_bb_filter: useBb,
          use_macd_filter: useMacd,
        }),
      })
      const json = await res.json()
      if (json.error) {
        setError(json.error)
        setData(null)
      } else {
        setData(json)
      }
    } catch (e: any) {
      setError(e.message || "请求失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    runBacktest()
  }, [symbol, startDate, endDate, rsiPeriod, entryRsi, addRsi, reduceRsi, fullExitRsi, maxLayers, useBb, useMacd])

  const chart = data?.chart
  const metrics = data?.metrics

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      <aside className="w-80 bg-slate-900 border-r border-slate-800 p-5 overflow-y-auto flex-shrink-0">
        <h1 className="text-xl font-bold mb-6 text-cyan-400">股指左侧交易回测</h1>
        <div className="space-y-4 text-sm">
          <label className="block">
            <span className="text-slate-400">选择股指</span>
            <select className="mt-1 w-full bg-slate-800 border border-slate-700 rounded px-3 py-2" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {INDICES.map((i) => (
                <option key={i.symbol} value={i.symbol}>{i.name}</option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label>
              <span className="text-slate-400">开始</span>
              <input type="date" className="mt-1 w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <label>
              <span className="text-slate-400">结束</span>
              <input type="date" className="mt-1 w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </label>
          </div>
          <hr className="border-slate-700" />
          <Slider label={`RSI 周期: ${rsiPeriod}`} min={6} max={30} value={rsiPeriod} onChange={setRsiPeriod} />
          <Slider label={`入场 RSI: ${entryRsi}`} min={20} max={50} value={entryRsi} onChange={setEntryRsi} />
          <Slider label={`加仓 RSI: ${addRsi}`} min={10} max={40} value={addRsi} onChange={setAddRsi} />
          <Slider label={`分批卖出 RSI: ${reduceRsi}`} min={50} max={80} value={reduceRsi} onChange={setReduceRsi} />
          <Slider label={`全部清仓 RSI: ${fullExitRsi}`} min={60} max={90} value={fullExitRsi} onChange={setFullExitRsi} />
          <Slider label={`最大层数: ${maxLayers}`} min={2} max={8} value={maxLayers} onChange={setMaxLayers} />
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useBb} onChange={(e) => setUseBb(e.target.checked)} />
            <span>布林带下轨共振</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useMacd} onChange={(e) => setUseMacd(e.target.checked)} />
            <span>MACD 共振</span>
          </label>
        </div>
        <p className="mt-6 text-xs text-slate-500">调整参数后自动重新回测</p>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        {loading && <div className="text-cyan-400 mb-4">计算中...</div>}
        {error && <div className="text-red-400 mb-4">{error}</div>}

        {chart && (
          <>
            <div className="space-y-6 mb-8">
              <Plot
                data={[
                  {
                    x: chart.dates,
                    open: chart.open,
                    high: chart.high,
                    low: chart.low,
                    close: chart.close,
                    type: "candlestick",
                    name: "K线",
                    increasing: { line: { color: "#ef5350" } },
                    decreasing: { line: { color: "#26a69a" } },
                  },
                  { x: chart.dates, y: chart.bb_upper, type: "scatter", name: "BB上", line: { color: "gray", dash: "dot", width: 1 } },
                  { x: chart.dates, y: chart.bb_mid, type: "scatter", name: "BB中", line: { color: "orange", width: 1 } },
                  { x: chart.dates, y: chart.bb_lower, type: "scatter", name: "BB下", line: { color: "gray", dash: "dot", width: 1 } },
                ]}
                layout={{
                  title: "K线 + 布林带",
                  height: 420,
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  font: { color: "#e2e8f0" },
                  xaxis: { rangeslider: { visible: false } },
                  yaxis: { title: "价格" },
                  margin: { t: 40, b: 40, l: 50, r: 20 },
                }}
                config={{ displayModeBar: false }}
                className="w-full"
              />

              <Plot
                data={[{ x: chart.dates, y: chart.rsi, type: "scatter", name: "RSI", line: { color: "#ff9800" } }]}
                layout={{
                  title: "RSI",
                  height: 220,
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  font: { color: "#e2e8f0" },
                  yaxis: { range: [0, 100] },
                  shapes: [
                    { type: "line", y0: entryRsi, y1: entryRsi, x0: 0, x1: 1, xref: "paper", line: { color: "green", dash: "dash" } },
                    { type: "line", y0: addRsi, y1: addRsi, x0: 0, x1: 1, xref: "paper", line: { color: "blue", dash: "dash" } },
                    { type: "line", y0: reduceRsi, y1: reduceRsi, x0: 0, x1: 1, xref: "paper", line: { color: "orange", dash: "dash" } },
                    { type: "line", y0: fullExitRsi, y1: fullExitRsi, x0: 0, x1: 1, xref: "paper", line: { color: "red", dash: "dash" } },
                  ],
                  margin: { t: 30, b: 30, l: 50, r: 20 },
                }}
                config={{ displayModeBar: false }}
                className="w-full"
              />

              <Plot
                data={[
                  { x: chart.dates, y: chart.macd_hist, type: "bar", name: "MACD柱", marker: { color: chart.macd_hist.map((v: number) => v >= 0 ? "#ef5350" : "#26a69a") } },
                  { x: chart.dates, y: chart.macd, type: "scatter", name: "MACD", line: { color: "#2196f3" } },
                  { x: chart.dates, y: chart.macd_signal, type: "scatter", name: "Signal", line: { color: "#ff5722" } },
                ]}
                layout={{
                  title: "MACD",
                  height: 220,
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  font: { color: "#e2e8f0" },
                  margin: { t: 30, b: 30, l: 50, r: 20 },
                }}
                config={{ displayModeBar: false }}
                className="w-full"
              />

              <Plot
                data={[
                  { x: metrics?.dates, y: metrics?.equity, type: "scatter", name: "策略权益", line: { color: "#2196f3", width: 2 }, fill: "tozeroy" },
                  {
                    x: chart.dates,
                    y: chart.close.map((c: number) => (c / chart.close[0]) * 100000),
                    type: "scatter",
                    name: "买入持有",
                    line: { color: "#9e9e9e", dash: "dot" },
                  },
                ]}
                layout={{
                  title: "策略权益 vs 买入持有",
                  height: 280,
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  font: { color: "#e2e8f0" },
                  margin: { t: 30, b: 40, l: 50, r: 20 },
                }}
                config={{ displayModeBar: false }}
                className="w-full"
              />
            </div>

            {metrics && (
              <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
                <h2 className="text-lg font-semibold mb-4 text-cyan-400">策略绩效</h2>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                  <Metric label="总收益率" value={`${metrics.total_return}%`} />
                  <Metric label="胜率" value={`${metrics.win_rate}%`} />
                  <Metric label="交易次数" value={metrics.trades} />
                  <Metric label="最大回撤" value={`${metrics.max_dd}%`} />
                  <Metric label="Sharpe" value={metrics.sharpe} />
                </div>
                <p className="text-sm text-slate-400 leading-relaxed">
                  RSI {"<"} {entryRsi} 建立首仓，RSI {"<"} {addRsi} 继续加仓（最多 {maxLayers} 层）。
                  RSI {">"} {reduceRsi} 开始分批卖出，RSI {">"} {fullExitRsi} 全部清仓。
                  {useBb && " 已启用布林带下轨过滤。"}
                  {useMacd && " 已启用 MACD 共振过滤。"}
                </p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

function Slider({ label, min, max, value, onChange }: { label: string; min: number; max: number; value: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <span className="text-slate-400 text-xs">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full mt-1 accent-cyan-500"
      />
    </label>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3 text-center">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-xl font-bold text-cyan-300 mt-1">{value}</div>
    </div>
  )
}

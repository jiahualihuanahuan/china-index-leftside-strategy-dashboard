# 中国股指左侧交易策略回测仪表盘

现代技术栈版本：**FastAPI** 后端 + **React / Vite / TypeScript / Tailwind / Plotly.js** 前端。

## 功能

- 实时调节 RSI 入场/加仓/分批卖出/清仓阈值，自动重新回测
- 布林带下轨共振、MACD 共振过滤
- 图表在上：K线+布林带、RSI、MACD、权益曲线
- 策略绩效数据在图表下方展示
- 支持沪深300、中证500、中证1000、上证50、创业板指

## 一键启动（Docker Compose）

```bash
docker compose up -d --build
```

浏览器打开：**http://localhost:3330**

停止：
```bash
docker compose down
```

## 技术栈

- **Backend**: FastAPI + pandas + akshare
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + Plotly.js
- **部署**: Docker Compose（前端 Nginx 反向代理到后端）

## 策略逻辑

- **越跌越买**：RSI 低于入场阈值建仓，更低时继续加仓（分层）
- **分批卖出**：RSI 升至减仓阈值时逐层卖出，更高时全部清仓
- 可叠加布林带与 MACD 作为买入共振条件

仅供研究与学习，不构成投资建议。

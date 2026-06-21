"use strict";

const REFRESH_MS = 5000;

function fmt(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}
function money(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const v = Number(n);
  return (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function cls(n) { if (n === null || n === undefined) return "neu"; return n > 0 ? "pos" : n < 0 ? "neg" : "neu"; }
function el(tag, className, html) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function card(k, v, klass) {
  return `<div class="card"><div class="k">${k}</div><div class="v ${klass || "neu"}">${v}</div></div>`;
}

function statusClass(s) {
  s = (s || "").toUpperCase();
  if (s === "LIVE") return "live";
  if (s === "DRY RUN") return "dry";
  if (s === "SAFE MODE") return "safe";
  if (s === "HALTED") return "halted";
  if (s === "RUNNING") return "running";
  if (s === "WAITING") return "waiting";
  if (s === "OFFLINE") return "offline";
  if (s === "ERROR") return "error";
  return "";
}

function renderAccount(a) {
  const c = document.getElementById("account-cards");
  c.innerHTML =
    card("Balance", money(a.balance)) +
    card("Equity", money(a.equity)) +
    card("Open PnL", money(a.open_pnl), cls(a.open_pnl)) +
    card("Daily PnL", money(a.daily_pnl), cls(a.daily_pnl)) +
    card("Closed PnL", money(a.closed_pnl), cls(a.closed_pnl)) +
    card("Monthly PnL", a.monthly_pnl == null ? "—" : money(a.monthly_pnl), cls(a.monthly_pnl)) +
    card("Total Revenue", a.total_revenue == null ? "—" : money(a.total_revenue), cls(a.total_revenue));
}

function renderPerf(p) {
  const c = document.getElementById("perf-cards");
  const pf = p.profit_factor === null ? "∞" : fmt(p.profit_factor, 2);
  c.innerHTML =
    card("Win Rate", fmt(p.win_rate, 1) + "%") +
    card("Loss Rate", fmt(p.loss_rate, 1) + "%") +
    card("Profit Factor", pf, p.profit_factor >= 1 ? "pos" : "neg") +
    card("Avg RR", fmt(p.avg_rr, 2)) +
    card("Sharpe", fmt(p.sharpe, 2)) +
    card("Max DD", money(p.max_drawdown) + (p.max_drawdown_pct ? ` (${fmt(p.max_drawdown_pct,1)}%)` : ""), "neg") +
    card("Trades", p.trades) +
    card("Net PnL", money(p.net_pnl), cls(p.net_pnl));
}

function gauge(label, used, limit) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  let k = "ok"; if (pct >= 100) k = "bad"; else if (pct >= 70) k = "warn";
  return `<div class="gauge"><div class="lab"><span>${label}</span><span>${fmt(used,2)}% / ${fmt(limit,2)}%</span></div>
    <div class="track"><div class="fill ${k}" style="width:${pct}%"></div></div></div>`;
}

function renderRisk(r) {
  const b = document.getElementById("risk-block");
  let html =
    gauge("Daily Loss Used", r.daily_loss_used_pct, r.daily_loss_limit_pct) +
    gauge("Drawdown Used", r.drawdown_used_pct, r.max_drawdown_pct) +
    `<div class="metricline">
      <span>Risk / trade <b>${fmt(r.max_risk_per_trade_pct,2)}%</b></span>
      <span>Hard cap <b>${fmt(r.max_risk_hard_pct,2)}%</b></span>
      <span>Daily limit <b>${fmt(r.daily_loss_limit_pct,2)}%</b></span>
      <span>Max DD <b>${fmt(r.max_drawdown_pct,2)}%</b></span>
    </div>`;
  if (r.breaches && r.breaches.length) {
    html += `<div class="warnbar">⚠ SAFE MODE — ${r.breaches.join("; ")}. Manual approval required to resume.</div>`;
  }
  b.innerHTML = html;
}

function renderPositions(rows) {
  const tb = document.querySelector("#positions tbody");
  if (!rows || !rows.length) {
    tb.innerHTML = `<tr><td colspan="12" class="empty">No open positions — flat.</td></tr>`;
    return;
  }
  tb.innerHTML = rows.map(p => `<tr>
    <td>${p.platform || "—"}</td>
    <td>${p.symbol}</td>
    <td>${(p.side || "").toUpperCase()}</td>
    <td>${fmt(p.entry, 5)}</td>
    <td>${p.price == null || Number.isNaN(p.price) ? "—" : fmt(p.price, 5)}</td>
    <td>${p.sl == null ? "—" : fmt(p.sl, 5)}</td>
    <td>${p.tp == null ? "—" : fmt(p.tp, 5)}</td>
    <td>${fmt(p.qty, 2)}</td>
    <td class="${cls(p.pnl)}">${money(p.pnl)}</td>
    <td>${p.risk_pct == null ? "—" : fmt(p.risk_pct, 2)}</td>
    <td>${p.confidence == null ? "—" : fmt(p.confidence, 2)}</td>
    <td>${p.agent || "—"}</td>
  </tr>`).join("");
}

function regimeClass(r) {
  r = (r || "").toUpperCase();
  if (r === "TRENDING") return "trending";
  if (r === "RANGING") return "ranging";
  if (r.includes("HIGH")) return "highvol";
  if (r.includes("LOW")) return "lowvol";
  return "notrade";
}
function bar(label, v) {
  const pct = Math.round((v || 0) * 100);
  return `<div class="bar"><div class="lab"><span>${label}</span><span>${pct}%</span></div>
    <div class="track"><div class="fill" style="width:${pct}%"></div></div></div>`;
}
function dchip(label, d) {
  const k = (d || "WAIT").toLowerCase();
  return `<div class="dchip ${k}">${label}<b>${d}</b></div>`;
}

function renderMarket(rows) {
  const c = document.getElementById("market");
  c.innerHTML = (rows || []).map(m => {
    if (!m.ok) {
      return `<div class="sym"><div class="head"><span class="name">${m.symbol}</span></div>
        <div class="regime notrade">NO DATA</div><div class="dt">${m.error || ""}</div></div>`;
    }
    return `<div class="sym">
      <div class="head"><span class="name">${m.symbol}</span><span class="price">${fmt(m.price, 4)}</span></div>
      <div class="regime ${regimeClass(m.regime)}">${m.regime}</div>
      ${bar("Trend", m.trend_score)}
      ${bar("Momentum", m.momentum_score)}
      ${bar("Volatility", m.volatility_score)}
      ${bar("Confidence", m.confidence_score)}
      <div class="decisions">${dchip("Trend", m.trend_decision)}${dchip("Range", m.range_decision)}</div>
      <div class="metricline">
        <span>ADX <b>${fmt(m.adx,1)}</b></span>
        <span>RSI <b>${fmt(m.rsi,1)}</b></span>
        <span>ATR% <b>${fmt(m.atr_pct,2)}</b></span>
        <span>Spread <b>${m.spread == null ? "—" : fmt(m.spread,5)}</b></span>
      </div>
    </div>`;
  }).join("");
}

function renderAgents(rows) {
  const c = document.getElementById("agents");
  c.innerHTML = (rows || []).map(a => `<div class="agent">
    <div class="top"><span class="nm">${a.name}</span>
      <span class="pill ${statusClass(a.status)}">${a.status}</span></div>
    <div class="dt">${a.detail || ""}</div>
  </div>`).join("");
}

async function tick() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    const s = await res.json();
    const ss = document.getElementById("system-status");
    ss.textContent = s.system_status;
    ss.className = "pill big " + statusClass(s.system_status);
    document.getElementById("decision").textContent = s.decision || "";
    document.getElementById("updated").textContent = (s.generated_at || "").replace("T", " ").replace("+00:00", " UTC");
    const src = s.source || {};
    document.getElementById("source").textContent = `${src.mode || ""} (${src.name || ""})`;
    renderAccount(s.account || {});
    renderPerf(s.performance || {});
    renderRisk(s.risk || {});
    renderPositions(s.positions || []);
    renderMarket(s.market || []);
    renderAgents(s.agents || []);
  } catch (e) {
    console.error("state fetch failed", e);
  }
}

tick();
setInterval(tick, REFRESH_MS);

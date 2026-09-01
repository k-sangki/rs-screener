const PAGE_SIZE = 50;
const FILTER_KEYS = ["trendTemplate", "vcp", "maAligned", "newHigh52", "rsLineNew", "midCapPlus", "boxBreakout", "epsExplosion"];
const SIGNAL_LABELS = {
  pocketPivot: "포켓 피봇", high52Breakout: "52주 신고가 돌파", high50Breakout: "50일 신고가 돌파", high20Breakout: "20일 신고가 돌파", dryUp: "드라이업",
  turtleSoup: "터틀 수프", turtleSoupPlusOne: "터틀 수프 +1", turtleSoupShort: "터틀 수프 숏", turtleSoupShortPlusOne: "터틀 수프 숏 +1",
  eightyTwenty: "80-20", momentumPinball: "모멘텀 핀볼", antiSlowStochastic: "Anti Slow Stochastic", holyGrail: "Holy Grail", adxGap: "ADX Gap",
  whiplash: "Whiplash", idNr4: "ID/NR4", nr7: "NR7", idNr7: "ID/NR7", crabelHvs: "Crabel HVS"
};

const state = {
  region: "kr", data: [], meta: {}, query: "", minRs: 70, minTrend: 0, sepaGrade: "ALL", minQuarterEps: null, minQuarterSales: null,
  minAnnualEps: null, minCanSlim: 0, minRoe: null, filters: Object.fromEntries(FILTER_KEYS.map((key) => [key, false])), signals: new Set(),
  sortKey: "rs", sortDirection: "desc", page: 1, watchOnly: false, watchlist: new Set(JSON.parse(localStorage.getItem("rs-watchlist") || "[]")),
  compare: new Set(), expanded: new Set(), availableFields: new Set(), availableSignals: new Set()
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const finite = (value) => value !== null && value !== "" && Number.isFinite(Number(value));
const numberOrNull = (value) => finite(value) ? Number(value) : null;

function normalizeItem(raw) {
  const inferredSignals = [];
  if (raw.pocketPivot) inferredSignals.push("pocketPivot");
  const trendScore = numberOrNull(raw.trendScore) ?? [raw.trendTemplate, raw.maAligned, raw.newHigh52, raw.rs >= 70].filter(Boolean).length * 2;
  return {
    ...raw, trendScore: Math.min(8, trendScore), sepaGrade: raw.sepaGrade || "-", quarterEpsGrowth: numberOrNull(raw.quarterEpsGrowth),
    quarterSalesGrowth: numberOrNull(raw.quarterSalesGrowth), annualEpsGrowth: numberOrNull(raw.annualEpsGrowth), roe: numberOrNull(raw.roe),
    canSlimScore: numberOrNull(raw.canSlimScore), canSlim: raw.canSlim || {}, signals: [...new Set([...(raw.signals || []), ...inferredSignals])],
    boxBreakout: Boolean(raw.boxBreakout), epsExplosion: Boolean(raw.epsExplosion || Number(raw.quarterEpsGrowth) >= 100)
  };
}
function formatNumber(value) { return finite(value) ? Math.round(Number(value)).toLocaleString("ko-KR") : "-"; }
function formatPercent(value) { return finite(value) ? `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(1)}%` : "-"; }
function formatMarketCap(value) { if (!finite(value)) return "-"; return value >= 1e12 ? `${(value / 1e12).toFixed(1)}조` : `${Math.round(value / 1e8).toLocaleString("ko-KR")}억`; }
function changeClass(value) { return value > 0 ? "positive" : value < 0 ? "negative" : ""; }
function marketLink(item) { return state.region === "kr" ? `https://stock.naver.com/domestic/stock/${item.ticker}/price` : `https://finance.yahoo.com/quote/${encodeURIComponent(item.ticker)}`; }
function renderSignalFilters() {
  $("#signalFilters").innerHTML = Object.entries(SIGNAL_LABELS).map(([key, label]) => {
    const available = state.availableSignals.has(key);
    return `<label class="${available ? "" : "unavailable-control"}" title="${available ? "" : "계산식 연결 전"}"><input type="checkbox" data-signal="${key}" ${available ? "" : "disabled"}> ${label}${available ? "" : " · 준비중"}</label>`;
  }).join("");
}

function setControlAvailability(selector, available) {
  const control = $(selector);
  if (!control) return;
  control.disabled = !available;
  control.closest("label")?.classList.toggle("unavailable-control", !available);
  control.closest("label")?.setAttribute("title", available ? "" : "재무 데이터 연결 전");
}

function updateAvailability(rawItems) {
  state.availableFields = new Set(rawItems.flatMap((item) => Object.keys(item)));
  state.availableSignals = new Set(rawItems.flatMap((item) => item.signals || []));
  if (rawItems.some((item) => item.pocketPivot)) state.availableSignals.add("pocketPivot");

  const controls = {
    "#sepaGrade": "sepaGrade", "#minQuarterEps": "quarterEpsGrowth", "#minQuarterSales": "quarterSalesGrowth",
    "#minAnnualEps": "annualEpsGrowth", "#minCanSlim": "canSlimScore", "#minRoe": "roe"
  };
  Object.entries(controls).forEach(([selector, field]) => setControlAvailability(selector, state.availableFields.has(field)));
  [["boxBreakout", "boxBreakout"], ["epsExplosion", "epsExplosion"]].forEach(([filter, field]) => {
    const input = $(`[data-filter="${filter}"]`), available = state.availableFields.has(field);
    input.disabled = !available; input.closest("label")?.classList.toggle("unavailable-control", !available);
    input.closest("label")?.setAttribute("title", available ? "" : "데이터 연결 전");
  });

  const sepaReady = ["sepaGrade", "quarterEpsGrowth", "quarterSalesGrowth", "annualEpsGrowth"].some((field) => state.availableFields.has(field));
  const canSlimReady = state.availableFields.has("canSlimScore");
  $("#sepaAvailability").textContent = sepaReady ? "" : "· DART 연결 전";
  $("#canSlimAvailability").textContent = canSlimReady ? "" : "· DART 연결 전";
  $("#signalAvailability").textContent = `${state.availableSignals.size}/${Object.keys(SIGNAL_LABELS).length}개 계산 중 · 선택 신호 중 하나 이상`;
  $("#qualityLabel").textContent = canSlimReady ? "Trend 8 · CANSLIM 7+" : "Trend 8";
  state.signals = new Set([...state.signals].filter((signal) => state.availableSignals.has(signal)));
  renderSignalFilters();

  const unavailableSorts = { sepaGrade: "sepaGrade", quarterEpsGrowth: "quarterEpsGrowth", quarterSalesGrowth: "quarterSalesGrowth", canSlimScore: "canSlimScore" };
  Object.entries(unavailableSorts).forEach(([sort, field]) => $("th[data-sort=\"" + sort + "\"]")?.classList.toggle("unavailable-column", !state.availableFields.has(field)));
}

async function loadRegion(region) {
  state.region = region; state.page = 1; state.compare.clear(); state.expanded.clear(); setStatus("데이터를 불러오는 중입니다…");
  try {
    const response = await fetch(`./data/${region}.json`, { cache: "no-store" }); if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json(); const rawItems = Array.isArray(payload.items) ? payload.items : [];
    state.meta = payload; updateAvailability(rawItems); state.data = rawItems.map(normalizeItem);
    setStatus(payload.message || "", Boolean(payload.message)); updateRegionCopy(); render();
  } catch (error) { state.data = []; setStatus(`데이터를 불러오지 못했습니다: ${error.message}`, true); render(); }
}
function setStatus(message, visible = true) { const box = $("#statusMessage"); box.textContent = message; box.hidden = !visible || !message; }
function updateRegionCopy() {
  const kr = state.region === "kr"; $("#regionEyebrow").textContent = kr ? "KR" : "US"; $("#pageTitle").textContent = kr ? "KRX 통합 주식 스크리너" : "미국 통합 주식 스크리너";
  $("#pageDescription").textContent = "RS·SEPA·CANSLIM·기술 신호를 한 화면에서 조합해 종목을 탐색합니다.";
  $("#updatedAt").textContent = state.meta.updatedAt ? `${state.meta.updatedAt} 업데이트` : "업데이트 대기 중";
  $$(".region-tab").forEach((button) => { const active = button.dataset.region === state.region; button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active)); });
}
function gradePass(grade) { if (state.sepaGrade === "ALL") return true; const order = { S: 3, A: 2, B: 1, C: 0, "-": -1 }; return (order[grade] ?? -1) >= order[state.sepaGrade]; }
function visibleItems() {
  const query = state.query.trim().toLowerCase();
  const list = state.data.filter((item) => {
    if (item.rs < state.minRs || item.trendScore < state.minTrend || !gradePass(item.sepaGrade)) return false;
    if (state.minQuarterEps !== null && (item.quarterEpsGrowth === null || item.quarterEpsGrowth < state.minQuarterEps)) return false;
    if (state.minQuarterSales !== null && (item.quarterSalesGrowth === null || item.quarterSalesGrowth < state.minQuarterSales)) return false;
    if (state.minAnnualEps !== null && (item.annualEpsGrowth === null || item.annualEpsGrowth < state.minAnnualEps)) return false;
    if (state.minCanSlim && (item.canSlimScore === null || item.canSlimScore < state.minCanSlim)) return false;
    if (state.minRoe !== null && (item.roe === null || item.roe < state.minRoe)) return false;
    if (state.watchOnly && !state.watchlist.has(`${state.region}:${item.ticker}`)) return false;
    if (query && ![item.name, item.ticker, item.market, item.theme].filter(Boolean).some((value) => String(value).toLowerCase().includes(query))) return false;
    if (state.filters.midCapPlus && item.marketCap < 300_000_000_000) return false;
    if (!FILTER_KEYS.filter((key) => key !== "midCapPlus").every((key) => !state.filters[key] || Boolean(item[key]))) return false;
    return !state.signals.size || [...state.signals].some((signal) => item.signals.includes(signal));
  });
  return list.sort((a, b) => { const av = a[state.sortKey] ?? -Infinity, bv = b[state.sortKey] ?? -Infinity; const compared = typeof av === "string" ? av.localeCompare(String(bv), state.region === "kr" ? "ko" : "en") : Number(av) - Number(bv); return compared ? (state.sortDirection === "asc" ? compared : -compared) : b.rs - a.rs || String(a.ticker).localeCompare(String(b.ticker)); });
}
function signalBadges(item) { if (!item.signals.length) return '<span class="muted">-</span>'; return item.signals.slice(0, 3).map((key) => `<span class="signal-chip">${SIGNAL_LABELS[key] || key}</span>`).join("") + (item.signals.length > 3 ? `<span class="more-chip">+${item.signals.length - 3}</span>` : ""); }
function canSlimBadges(item) { return ["C", "A", "N", "S", "L", "I", "M"].map((key) => `<span class="letter-badge ${item.canSlim[key] ? "on" : ""}">${key}</span>`).join(""); }
function detailRow(item) {
  return `<tr class="detail-row"><td colspan="11"><div class="detail-grid"><section><strong>CANSLIM 구성</strong><div class="letter-list">${canSlimBadges(item)}</div><small>ROE ${formatPercent(item.roe)}</small></section><section><strong>SEPA 성장</strong><span>연간 EPS ${formatPercent(item.annualEpsGrowth)}</span><span>박스 돌파 ${item.boxBreakout ? "O" : "-"}</span><span>EPS 폭발 ${item.epsExplosion ? "O" : "-"}</span></section><section><strong>가격 구조</strong><span>Trend Template ${item.trendTemplate ? "O" : "-"}</span><span>VCP ${item.vcp ? "O" : "-"}</span><span>RS Line NEW ${item.rsLineNew ? "O" : "-"}</span></section><section><strong>감지 신호</strong><div class="signal-cell">${signalBadges(item)}</div></section></div></td></tr>`;
}
function renderRows(items) {
  const body = $("#stockRows"); if (!items.length) { body.innerHTML = '<tr class="empty-row"><td colspan="11">조건에 맞는 종목이 없습니다.</td></tr>'; return; }
  body.innerHTML = items.map((item) => {
    const watchKey = `${state.region}:${item.ticker}`, watched = state.watchlist.has(watchKey), compared = state.compare.has(item.ticker), change = Number(item.changePct) || 0, expanded = state.expanded.has(item.ticker);
    const row = `<tr><td><div class="stock-cell"><button class="watch-button ${watched ? "active" : ""}" data-watch="${item.ticker}" type="button">${watched ? "★" : "☆"}</button><div><a class="stock-name" href="${marketLink(item)}" target="_blank" rel="noopener noreferrer">${item.name}</a><span class="stock-meta"><span>${item.ticker} · ${item.market}</span>${item.theme ? `<span class="theme-chip">${item.theme}</span>` : ""}</span></div><button class="compare-button ${compared ? "active" : ""}" data-compare="${item.ticker}" type="button">${compared ? "✓" : "+"}</button></div></td><td class="text-right"><span class="price">${formatNumber(item.close)}</span><span class="change ${changeClass(change)}">${change > 0 ? "+" : ""}${change.toFixed(1)}%</span></td><td class="text-right">${formatMarketCap(item.marketCap)}<span class="size-label">${item.size || ""}</span></td><td class="text-center"><span class="rs-badge ${item.rs >= 90 ? "rs-elite" : "rs-strong"}">${item.rs}</span></td><td class="text-center"><strong>${item.trendScore}/8</strong></td><td class="text-center"><span class="grade-badge grade-${item.sepaGrade}">${item.sepaGrade}</span></td><td class="text-right ${changeClass(item.quarterEpsGrowth || 0)}">${formatPercent(item.quarterEpsGrowth)}</td><td class="text-right ${changeClass(item.quarterSalesGrowth || 0)}">${formatPercent(item.quarterSalesGrowth)}</td><td class="text-center">${item.canSlimScore === null ? "-" : `<span class="can-score">${item.canSlimScore}<small>/11</small></span>`}</td><td><div class="signal-cell">${signalBadges(item)}</div></td><td class="text-center"><button class="detail-button" data-detail="${item.ticker}" type="button" aria-expanded="${expanded}">${expanded ? "닫기" : "보기"}</button></td></tr>`;
    return row + (expanded ? detailRow(item) : "");
  }).join("");
}
function renderHeaders() { $$("th[data-sort]").forEach((header) => { const active = header.dataset.sort === state.sortKey; header.classList.toggle("active", active); header.querySelector("span").textContent = active ? (state.sortDirection === "asc" ? "▲" : "▼") : ""; }); }
function renderCompare() { const selected = state.data.filter((item) => state.compare.has(item.ticker)); $("#compareBar").hidden = !selected.length; $("#compareNames").textContent = selected.map((item) => item.name).join(" · "); }
function render() {
  const list = visibleItems(), totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE)); state.page = Math.min(state.page, totalPages); renderRows(list.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE)); renderHeaders(); renderCompare();
  const canSlimReady = state.availableFields.has("canSlimScore");
  $("#filteredCount").textContent = list.length.toLocaleString(); $("#rs90Count").textContent = list.filter((item) => item.rs >= 90).length.toLocaleString(); $("#qualityCount").textContent = list.filter((item) => item.trendScore === 8 && (!canSlimReady || item.canSlimScore >= 7)).length.toLocaleString(); $("#watchCount").textContent = state.watchlist.size;
  $("#pageIndicator").textContent = `${state.page} / ${totalPages}`; $("#firstPage").disabled = $("#prevPage").disabled = state.page === 1; $("#nextPage").disabled = $("#lastPage").disabled = state.page === totalPages;
}
function bindSelect(id, stateKey, numeric = true) { $(id).addEventListener("change", (event) => { state[stateKey] = event.target.value === "" ? null : numeric ? Number(event.target.value) : event.target.value; state.page = 1; render(); }); }
$("#searchInput").addEventListener("input", (event) => { state.query = event.target.value; state.page = 1; render(); });
bindSelect("#minRs", "minRs"); bindSelect("#minTrend", "minTrend"); bindSelect("#sepaGrade", "sepaGrade", false); bindSelect("#minQuarterEps", "minQuarterEps"); bindSelect("#minQuarterSales", "minQuarterSales"); bindSelect("#minAnnualEps", "minAnnualEps"); bindSelect("#minCanSlim", "minCanSlim"); bindSelect("#minRoe", "minRoe");
$("#filterToggle").addEventListener("click", () => { const panel = $("#filterPanel"); panel.hidden = !panel.hidden; $("#filterToggle").setAttribute("aria-expanded", String(!panel.hidden)); $("#filterToggle span").textContent = panel.hidden ? "▼" : "▲"; });
$$("[data-filter]").forEach((input) => input.addEventListener("change", () => { state.filters[input.dataset.filter] = input.checked; state.page = 1; render(); }));
$("#signalFilters").addEventListener("change", (event) => { const signal = event.target.dataset.signal; if (!signal) return; event.target.checked ? state.signals.add(signal) : state.signals.delete(signal); state.page = 1; render(); });
$$(".region-tab").forEach((button) => button.addEventListener("click", () => loadRegion(button.dataset.region)));
$$("th[data-sort]").forEach((header) => header.addEventListener("click", () => { if (header.classList.contains("unavailable-column")) return; const key = header.dataset.sort; state.sortDirection = state.sortKey === key && state.sortDirection === "desc" ? "asc" : "desc"; state.sortKey = key; state.page = 1; render(); }));
$("#stockRows").addEventListener("click", (event) => {
  const watch = event.target.closest("[data-watch]"); if (watch) { const key = `${state.region}:${watch.dataset.watch}`; state.watchlist.has(key) ? state.watchlist.delete(key) : state.watchlist.add(key); localStorage.setItem("rs-watchlist", JSON.stringify([...state.watchlist])); render(); return; }
  const compare = event.target.closest("[data-compare]"); if (compare) { const ticker = compare.dataset.compare; if (state.compare.has(ticker)) state.compare.delete(ticker); else if (state.compare.size < 4) state.compare.add(ticker); render(); return; }
  const detail = event.target.closest("[data-detail]"); if (detail) { state.expanded.has(detail.dataset.detail) ? state.expanded.delete(detail.dataset.detail) : state.expanded.add(detail.dataset.detail); render(); }
});
$("#watchlistToggle").addEventListener("click", () => { state.watchOnly = !state.watchOnly; $("#watchlistToggle").classList.toggle("active", state.watchOnly); state.page = 1; render(); }); $("#clearCompare").addEventListener("click", () => { state.compare.clear(); render(); });
$("#firstPage").addEventListener("click", () => { state.page = 1; render(); }); $("#prevPage").addEventListener("click", () => { state.page -= 1; render(); }); $("#nextPage").addEventListener("click", () => { state.page += 1; render(); }); $("#lastPage").addEventListener("click", () => { state.page = Math.max(1, Math.ceil(visibleItems().length / PAGE_SIZE)); render(); });
$("#resetButton").addEventListener("click", () => {
  Object.assign(state, { query: "", minRs: 70, minTrend: 0, sepaGrade: "ALL", minQuarterEps: null, minQuarterSales: null, minAnnualEps: null, minCanSlim: 0, minRoe: null, filters: Object.fromEntries(FILTER_KEYS.map((key) => [key, false])), signals: new Set(), watchOnly: false, page: 1 });
  $("#searchInput").value = ""; [["#minRs", "70"], ["#minTrend", "0"], ["#sepaGrade", "ALL"], ["#minQuarterEps", ""], ["#minQuarterSales", ""], ["#minAnnualEps", ""], ["#minCanSlim", "0"], ["#minRoe", ""]].forEach(([id, value]) => { $(id).value = value; }); $$("input[type=checkbox]").forEach((input) => { input.checked = false; }); render();
});
const savedTheme = localStorage.getItem("rs-theme"); if (savedTheme === "dark" || (!savedTheme && matchMedia("(prefers-color-scheme: dark)").matches)) document.documentElement.dataset.theme = "dark";
$("#themeToggle").addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; document.documentElement.dataset.theme = dark ? "dark" : "light"; localStorage.setItem("rs-theme", dark ? "dark" : "light"); });
renderSignalFilters(); loadRegion("kr");

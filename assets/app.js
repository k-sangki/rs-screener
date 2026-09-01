const PAGE_SIZE = 50;
const FILTER_KEYS = ["trendTemplate", "vcp", "pocketPivot", "maAligned", "newHigh52", "newEntry", "midCapPlus"];

const state = {
  region: "kr",
  data: [],
  meta: {},
  query: "",
  minRs: 70,
  filters: Object.fromEntries(FILTER_KEYS.map((key) => [key, false])),
  sortKey: "rs",
  sortDirection: "desc",
  page: 1,
  watchOnly: false,
  watchlist: new Set(JSON.parse(localStorage.getItem("rs-watchlist") || "[]")),
  compare: new Set(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function formatNumber(value) {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-";
}

function formatMarketCap(value) {
  if (!Number.isFinite(value)) return "-";
  if (value >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
  return `${Math.round(value / 1e8).toLocaleString("ko-KR")}억`;
}

function changeClass(value) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

function marketLink(item) {
  if (state.region === "kr") return `https://stock.naver.com/domestic/stock/${item.ticker}/price`;
  return `https://finance.yahoo.com/quote/${encodeURIComponent(item.ticker)}`;
}

async function loadRegion(region) {
  state.region = region;
  state.page = 1;
  state.compare.clear();
  setStatus("데이터를 불러오는 중입니다…");
  try {
    const response = await fetch(`./data/${region}.json`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.meta = payload;
    state.data = Array.isArray(payload.items) ? payload.items : [];
    setStatus(payload.message || "", Boolean(payload.message));
    updateRegionCopy();
    render();
  } catch (error) {
    state.data = [];
    setStatus(`데이터를 불러오지 못했습니다: ${error.message}`, true);
    render();
  }
}

function setStatus(message, visible = true) {
  const box = $("#statusMessage");
  box.textContent = message;
  box.hidden = !visible || !message;
}

function updateRegionCopy() {
  const kr = state.region === "kr";
  $("#regionEyebrow").textContent = kr ? "KR" : "US";
  $("#pageTitle").textContent = kr ? "KRX 상대강도 스크리너" : "미국 주식 상대강도 스크리너";
  $("#pageDescription").textContent = kr
    ? "RS 점수로 KOSPI·KOSDAQ의 상대적으로 강한 종목을 탐색합니다."
    : "RS 점수로 NYSE·NASDAQ의 상대적으로 강한 종목을 탐색합니다.";
  $("#updatedAt").textContent = state.meta.updatedAt ? `${state.meta.updatedAt} 업데이트` : "업데이트 대기 중";
  $$(".region-tab").forEach((button) => {
    const active = button.dataset.region === state.region;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function visibleItems() {
  const query = state.query.trim().toLowerCase();
  const list = state.data.filter((item) => {
    if (item.rs < state.minRs) return false;
    if (state.watchOnly && !state.watchlist.has(`${state.region}:${item.ticker}`)) return false;
    if (query && ![item.name, item.ticker, item.market, item.theme].filter(Boolean).some((value) => String(value).toLowerCase().includes(query))) return false;
    if (state.filters.midCapPlus && item.marketCap < 300_000_000_000) return false;
    return FILTER_KEYS.filter((key) => key !== "midCapPlus").every((key) => !state.filters[key] || Boolean(item[key]));
  });

  return list.sort((a, b) => {
    const av = a[state.sortKey] ?? "";
    const bv = b[state.sortKey] ?? "";
    const compared = typeof av === "string"
      ? av.localeCompare(String(bv), state.region === "kr" ? "ko" : "en")
      : Number(av) - Number(bv);
    if (compared !== 0) return state.sortDirection === "asc" ? compared : -compared;
    return b.rs - a.rs || String(a.ticker).localeCompare(String(b.ticker));
  });
}

function renderRows(items) {
  const body = $("#stockRows");
  if (!items.length) {
    body.innerHTML = '<tr class="empty-row"><td colspan="9">조건에 맞는 종목이 없습니다.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const watchKey = `${state.region}:${item.ticker}`;
    const watched = state.watchlist.has(watchKey);
    const compared = state.compare.has(item.ticker);
    const change = Number(item.changePct) || 0;
    return `<tr>
      <td>
        <div class="stock-cell">
          <button class="watch-button ${watched ? "active" : ""}" data-watch="${item.ticker}" type="button" aria-label="${watched ? "워치리스트에서 제거" : "워치리스트에 추가"}">${watched ? "★" : "☆"}</button>
          <div>
            <a class="stock-name" href="${marketLink(item)}" target="_blank" rel="noopener noreferrer">${item.name}</a>
            <span class="stock-meta"><span>${item.ticker} · ${item.market}</span>${item.theme ? `<span class="theme-chip">${item.theme}</span>` : ""}</span>
          </div>
          <button class="compare-button ${compared ? "active" : ""}" data-compare="${item.ticker}" type="button" aria-label="비교에 ${compared ? "제거" : "추가"}">${compared ? "✓" : "+"}</button>
        </div>
      </td>
      <td class="text-right"><span class="price">${formatNumber(item.close)}</span><span class="change ${changeClass(change)}">${change > 0 ? "+" : ""}${change.toFixed(1)}%</span></td>
      <td class="text-right">${formatMarketCap(item.marketCap)}<span class="size-label">${item.size || ""}</span></td>
      <td class="text-center"><span class="rs-badge ${item.rs >= 90 ? "rs-elite" : "rs-strong"}">${item.rs}</span></td>
      <td class="text-center">${item.rsLineNew ? '<span class="new-badge">▲ NEW</span>' : "-"}</td>
      <td class="text-center">${item.newHigh52 ? "O" : "-"}</td>
      <td class="text-right">${formatNumber(item.ma50)}</td>
      <td class="text-right">${formatNumber(item.ma150)}</td>
      <td class="text-right">${formatNumber(item.ma200)}</td>
    </tr>`;
  }).join("");
}

function renderHeaders() {
  $$("th[data-sort]").forEach((header) => {
    const active = header.dataset.sort === state.sortKey;
    header.classList.toggle("active", active);
    header.querySelector("span").textContent = active ? (state.sortDirection === "asc" ? "▲" : "▼") : "";
    header.setAttribute("aria-sort", active ? (state.sortDirection === "asc" ? "ascending" : "descending") : "none");
  });
}

function renderCompare() {
  const selected = state.data.filter((item) => state.compare.has(item.ticker));
  $("#compareBar").hidden = selected.length === 0;
  $("#compareNames").textContent = selected.map((item) => item.name).join(" · ");
}

function render() {
  const list = visibleItems();
  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * PAGE_SIZE;
  renderRows(list.slice(start, start + PAGE_SIZE));
  renderHeaders();
  renderCompare();
  $("#filteredCount").textContent = list.length.toLocaleString();
  $("#rs90Count").textContent = list.filter((item) => item.rs >= 90).length.toLocaleString();
  $("#watchCount").textContent = state.watchlist.size;
  $("#pageIndicator").textContent = `${state.page} / ${totalPages}`;
  $("#firstPage").disabled = state.page === 1;
  $("#prevPage").disabled = state.page === 1;
  $("#nextPage").disabled = state.page === totalPages;
  $("#lastPage").disabled = state.page === totalPages;
}

$("#searchInput").addEventListener("input", (event) => { state.query = event.target.value; state.page = 1; render(); });
$("#minRs").addEventListener("change", (event) => { state.minRs = Number(event.target.value); state.page = 1; render(); });
$("#filterToggle").addEventListener("click", () => {
  const panel = $("#filterPanel");
  panel.hidden = !panel.hidden;
  $("#filterToggle").setAttribute("aria-expanded", String(!panel.hidden));
  $("#filterToggle span").textContent = panel.hidden ? "▼" : "▲";
});
$$("[data-filter]").forEach((input) => input.addEventListener("change", () => { state.filters[input.dataset.filter] = input.checked; state.page = 1; render(); }));
$$(".region-tab").forEach((button) => button.addEventListener("click", () => loadRegion(button.dataset.region)));
$$("th[data-sort]").forEach((header) => header.addEventListener("click", () => {
  const key = header.dataset.sort;
  state.sortDirection = state.sortKey === key && state.sortDirection === "desc" ? "asc" : "desc";
  state.sortKey = key;
  state.page = 1;
  render();
}));

$("#stockRows").addEventListener("click", (event) => {
  const watch = event.target.closest("[data-watch]");
  if (watch) {
    const key = `${state.region}:${watch.dataset.watch}`;
    state.watchlist.has(key) ? state.watchlist.delete(key) : state.watchlist.add(key);
    localStorage.setItem("rs-watchlist", JSON.stringify([...state.watchlist]));
    render();
    return;
  }
  const compare = event.target.closest("[data-compare]");
  if (compare) {
    const ticker = compare.dataset.compare;
    if (state.compare.has(ticker)) state.compare.delete(ticker);
    else if (state.compare.size < 4) state.compare.add(ticker);
    render();
  }
});

$("#watchlistToggle").addEventListener("click", () => { state.watchOnly = !state.watchOnly; $("#watchlistToggle").classList.toggle("active", state.watchOnly); state.page = 1; render(); });
$("#clearCompare").addEventListener("click", () => { state.compare.clear(); render(); });
$("#firstPage").addEventListener("click", () => { state.page = 1; render(); });
$("#prevPage").addEventListener("click", () => { state.page -= 1; render(); });
$("#nextPage").addEventListener("click", () => { state.page += 1; render(); });
$("#lastPage").addEventListener("click", () => { state.page = Math.max(1, Math.ceil(visibleItems().length / PAGE_SIZE)); render(); });
$("#resetButton").addEventListener("click", () => {
  state.query = "";
  state.minRs = 70;
  state.filters = Object.fromEntries(FILTER_KEYS.map((key) => [key, false]));
  state.watchOnly = false;
  state.page = 1;
  $("#searchInput").value = "";
  $("#minRs").value = "70";
  $$("[data-filter]").forEach((input) => { input.checked = false; });
  render();
});

const savedTheme = localStorage.getItem("rs-theme");
if (savedTheme === "dark" || (!savedTheme && matchMedia("(prefers-color-scheme: dark)").matches)) document.documentElement.dataset.theme = "dark";
$("#themeToggle").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem("rs-theme", dark ? "dark" : "light");
  $("#themeToggle").setAttribute("aria-label", dark ? "라이트 모드로 전환" : "다크 모드로 전환");
});

loadRegion("kr");

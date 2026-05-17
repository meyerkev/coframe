const API_BASE = "http://localhost:8000";

const form = document.querySelector("#site-form");
const siteInput = document.querySelector("#site-id");
const pagesBody = document.querySelector("#pages");
const trend = document.querySelector("#trend");
const trendAxis = document.querySelector("#trend-axis");
const experiments = document.querySelector("#experiments");
const zoomButtons = [...document.querySelectorAll("[data-window]")];

let trendWindow = 10;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  refresh(siteInput.value.trim() || "demo");
});

zoomButtons.forEach((button) => {
  button.addEventListener("click", () => {
    trendWindow = Number(button.dataset.window);
    zoomButtons.forEach((item) => item.classList.toggle("active", item === button));
    refresh(siteInput.value.trim() || "demo");
  });
});

async function refresh(siteId) {
  const [config, aggregates, trendData] = await Promise.all([
    fetch(`${API_BASE}/config/${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/aggregates?site_id=${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/trend?site_id=${encodeURIComponent(siteId)}&limit=${trendWindow}`).then((response) => response.json()),
  ]);

  renderPages(aggregates.pages || []);
  renderTrend(trendData.points || []);
  renderExperiments(config.active_experiments || []);
}

function renderPages(pages) {
  pagesBody.innerHTML = "";
  if (pages.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = `<td class="empty" colspan="4">No events processed yet.</td>`;
    pagesBody.append(row);
    return;
  }

  for (const page of pages) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(page.page_url)}</td>
      <td>${page.event_count}</td>
      <td>${page.p75_lcp_ms} ms</td>
      <td>${escapeHtml(page.last_seen_timestamp)}</td>
    `;
    pagesBody.append(row);
  }
}

function renderTrend(points) {
  trend.innerHTML = "";
  trendAxis.innerHTML = "";
  if (points.length === 0) {
    trend.innerHTML = `<div class="empty">No LCP data yet.</div>`;
    return;
  }
  const max = Math.max(...points.map((point) => point.lcp_ms), 1);
  for (const point of points) {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max((point.lcp_ms / max) * 100, 4)}%`;
    bar.title = `${point.page_url}: ${point.lcp_ms} ms at ${formatTimestamp(point.timestamp)}`;
    trend.append(bar);
  }
  const first = points[0];
  const last = points[points.length - 1];
  trendAxis.innerHTML = `
    <span>${escapeHtml(formatTimestamp(first.timestamp))}</span>
    <span>${points.length} events</span>
    <span>${escapeHtml(formatTimestamp(last.timestamp))}</span>
  `;
}

function renderExperiments(items) {
  experiments.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    experiments.append(li);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().replace("T", " ").replace(".000", "").replace("Z", " UTC");
}

refresh("demo").catch((error) => {
  pagesBody.innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(error.message)}</td></tr>`;
});

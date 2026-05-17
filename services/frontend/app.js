const API_BASE = "http://localhost:8000";

const form = document.querySelector("#site-form");
const siteInput = document.querySelector("#site-id");
const pagesBody = document.querySelector("#pages");
const trend = document.querySelector("#trend");
const experiments = document.querySelector("#experiments");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  refresh(siteInput.value.trim() || "demo");
});

async function refresh(siteId) {
  const [config, aggregates] = await Promise.all([
    fetch(`${API_BASE}/config/${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/aggregates?site_id=${encodeURIComponent(siteId)}`).then((response) => response.json()),
  ]);

  renderPages(aggregates.pages || []);
  renderTrend(aggregates.pages || []);
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

function renderTrend(pages) {
  trend.innerHTML = "";
  if (pages.length === 0) {
    trend.innerHTML = `<div class="empty">No LCP data yet.</div>`;
    return;
  }
  const max = Math.max(...pages.map((page) => page.p75_lcp_ms), 1);
  for (const page of pages.slice(0, 8).reverse()) {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max((page.p75_lcp_ms / max) * 100, 4)}%`;
    bar.title = `${page.page_url}: ${page.p75_lcp_ms} ms`;
    trend.append(bar);
  }
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

refresh("demo").catch((error) => {
  pagesBody.innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(error.message)}</td></tr>`;
});


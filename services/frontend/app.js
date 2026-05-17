const API_BASE = "http://localhost:8000";

const form = document.querySelector("#site-form");
const siteInput = document.querySelector("#site-id");
const pagesBody = document.querySelector("#pages");
const trend = document.querySelector("#trend");
const experiments = document.querySelector("#experiments");
const zoomButtons = [...document.querySelectorAll("[data-window]")];
const bucketButtons = [...document.querySelectorAll("[data-bucket]")];

let trendWindow = 30;
let bucketMinutes = 1;

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

bucketButtons.forEach((button) => {
  button.addEventListener("click", () => {
    bucketMinutes = Number(button.dataset.bucket);
    bucketButtons.forEach((item) => item.classList.toggle("active", item === button));
    refresh(siteInput.value.trim() || "demo");
  });
});

async function refresh(siteId) {
  const [config, aggregates, trendData] = await Promise.all([
    fetch(`${API_BASE}/config/${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/aggregates?site_id=${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/trend?site_id=${encodeURIComponent(siteId)}&limit=${trendWindow}&window_minutes=${bucketMinutes}`).then((response) => response.json()),
  ]);

  renderPages(aggregates.pages || []);
  renderTrend(trendData.windows || [], trendData.window_minutes || bucketMinutes);
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

function renderTrend(windows, windowMinutes) {
  trend.innerHTML = "";
  const populated = windows.filter((window) => window.event_count > 0);
  if (populated.length === 0) {
    trend.innerHTML = `<div class="empty">No LCP data yet.</div>`;
    return;
  }
  const chartWindows = windows.map((window) => ({
    ...window,
    p75_lcp_ms: window.p75_lcp_ms ?? 0,
  }));

  const width = 920;
  const height = 260;
  const margin = { top: 14, right: 28, bottom: 44, left: 66 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = populated.map((window) => window.p75_lcp_ms);
  const maxY = niceMax(Math.max(...values, 1000));
  const yTicks = [0, maxY / 4, maxY / 2, (maxY * 3) / 4, maxY];
  const points = chartWindows.map((window, index) => {
    const x = margin.left + (chartWindows.length === 1 ? chartWidth : (index / (chartWindows.length - 1)) * chartWidth);
    const y = margin.top + chartHeight - (window.p75_lcp_ms / maxY) * chartHeight;
    return { ...window, x, y };
  });
  const xTicks = pickXTicks(points, 4);
  const linePath = buildLinePath(points);
  const bucketLabel = `${windowMinutes}m buckets`;

  trend.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="p75 LCP line chart by ${escapeHtml(bucketLabel)}">
      <g class="grid-lines">
        ${yTicks.map((tick) => {
          const y = margin.top + chartHeight - (tick / maxY) * chartHeight;
          return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y}" y2="${y}"></line>`;
        }).join("")}
      </g>
      <g class="y-axis">
        <line x1="${margin.left}" x2="${margin.left}" y1="${margin.top}" y2="${height - margin.bottom}"></line>
        ${yTicks.map((tick) => {
          const y = margin.top + chartHeight - (tick / maxY) * chartHeight;
          return `<text x="${margin.left - 10}" y="${y + 4}" text-anchor="end">${Math.round(tick)}</text>`;
        }).join("")}
      </g>
      <g class="x-axis">
        <line x1="${margin.left}" x2="${width - margin.right}" y1="${height - margin.bottom}" y2="${height - margin.bottom}"></line>
        ${xTicks.map((point, index) => {
          const anchor = index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle";
          return `
          <text x="${point.x}" y="${height - margin.bottom + 22}" text-anchor="${anchor}">${escapeHtml(formatShortTimestamp(point.window_start))}</text>
        `;
        }).join("")}
      </g>
      <text class="axis-label y-label" x="18" y="${margin.top + chartHeight / 2}" text-anchor="middle" transform="rotate(-90 18 ${margin.top + chartHeight / 2})">p75 LCP (ms)</text>
      <text class="axis-label" x="${margin.left + chartWidth / 2}" y="${height - 10}" text-anchor="middle">Time (UTC), ${escapeHtml(bucketLabel)}</text>
      <path class="line" d="${linePath}"></path>
      <g class="points">
        ${points.filter((point) => point.y !== null).map((point) => `
          <circle cx="${point.x}" cy="${point.y}" r="4">
            <title>${point.p75_lcp_ms} ms, ${point.event_count} events, ${formatTimestamp(point.window_start)} - ${formatTimestamp(point.window_end)}</title>
          </circle>
        `).join("")}
      </g>
    </svg>
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

function formatShortTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString().slice(11, 16);
}

function niceMax(value) {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

function pickXTicks(points, maxTicks) {
  if (points.length <= maxTicks) {
    return points;
  }
  const indexes = new Set();
  for (let i = 0; i < maxTicks; i += 1) {
    indexes.add(Math.round((i / (maxTicks - 1)) * (points.length - 1)));
  }
  return [...indexes].sort((a, b) => a - b).map((index) => points[index]);
}

function buildLinePath(points) {
  const segments = [];
  let open = false;
  for (const point of points) {
    if (point.y === null) {
      continue;
    }
    segments.push(`${open ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`);
    open = true;
  }
  return segments.join(" ");
}

refresh("demo").catch((error) => {
  pagesBody.innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(error.message)}</td></tr>`;
});

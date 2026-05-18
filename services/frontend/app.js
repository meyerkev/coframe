const API_BASE = "http://localhost:8000";

const form = document.querySelector("#site-form");
const siteInput = document.querySelector("#site-id");
const pagesBody = document.querySelector("#pages");
const trend = document.querySelector("#trend");
const experiments = document.querySelector("#experiments");
const queueCount = document.querySelector("#queue-count");
const queueName = document.querySelector("#queue-name");
const rangeButtons = [...document.querySelectorAll("[data-range]")];
const bucketButtons = [...document.querySelectorAll("[data-bucket]")];

let trendRangeMinutes = 30;
let bucketSeconds = 60;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  refresh(siteInput.value.trim() || "demo");
});

rangeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    trendRangeMinutes = Number(button.dataset.range);
    rangeButtons.forEach((item) => item.classList.toggle("active", item === button));
    refresh(siteInput.value.trim() || "demo");
  });
});

bucketButtons.forEach((button) => {
  button.addEventListener("click", () => {
    bucketSeconds = Number(button.dataset.bucket);
    bucketButtons.forEach((item) => item.classList.toggle("active", item === button));
    refresh(siteInput.value.trim() || "demo");
  });
});

async function refresh(siteId) {
  const trendLimit = Math.max(1, Math.ceil((trendRangeMinutes * 60) / bucketSeconds));
  const [config, aggregates, trendData, experimentData, queueStatus] = await Promise.all([
    fetch(`${API_BASE}/config/${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/aggregates?site_id=${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/trend?site_id=${encodeURIComponent(siteId)}&limit=${trendLimit}&window_seconds=${bucketSeconds}`).then((response) => response.json()),
    fetch(`${API_BASE}/experiments?site_id=${encodeURIComponent(siteId)}`).then((response) => response.json()),
    fetch(`${API_BASE}/queue`).then((response) => response.json()),
  ]);

  renderPages(aggregates.pages || []);
  renderTrend(trendData);
  renderExperiments(experimentData || []);
  renderQueueStatus(queueStatus);
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

function renderTrend(trendData) {
  trend.innerHTML = "";
  const windows = trendData.windows || [];
  const series = trendData.series || [];
  const windowSeconds = trendData.window_seconds || bucketSeconds;
  const chartSeries = series.length > 0
    ? series
    : [{
        experiment: "unknown",
        label: "unknown",
        windows,
      }];

  const referenceWindows = chartSeries[0]?.windows || windows;
  const populatedValues = chartSeries.flatMap((item) => (item.windows || []).filter((window) => window.event_count > 0).map((window) => window.p75_lcp_ms));
  if (referenceWindows.length === 0) {
    trend.innerHTML = `<div class="empty">No LCP data yet.</div>`;
    return;
  }

  const width = 920;
  const height = 260;
  const margin = { top: 14, right: 28, bottom: 44, left: 66 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const maxY = niceMax(Math.max(...populatedValues, 1000));
  const yTicks = [0, maxY / 4, maxY / 2, (maxY * 3) / 4, maxY];
  const xPoints = referenceWindows.map((window, index) => {
    const x = margin.left + (referenceWindows.length === 1 ? chartWidth : (index / (referenceWindows.length - 1)) * chartWidth);
    return { ...window, x };
  });
  const xTicks = pickXTicks(xPoints, 4);
  const bucketLabel = `${formatBucketLabel(windowSeconds)} buckets`;
  const legendItems = chartSeries.map((item, index) => ({
    label: item.label || item.experiment || "unknown",
    color: seriesColor(item.label || item.experiment || "unknown", index),
  }));

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
          const labelValue = index === xTicks.length - 1 ? point.window_end : point.window_start;
          return `
          <text x="${point.x}" y="${height - margin.bottom + 22}" text-anchor="${anchor}">${escapeHtml(formatAxisTimestamp(labelValue, windowSeconds))}</text>
        `;
        }).join("")}
      </g>
      <text class="axis-label y-label" x="18" y="${margin.top + chartHeight / 2}" text-anchor="middle" transform="rotate(-90 18 ${margin.top + chartHeight / 2})">p75 LCP (ms)</text>
      <text class="axis-label" x="${margin.left + chartWidth / 2}" y="${height - 10}" text-anchor="middle">Time (UTC), ${escapeHtml(bucketLabel)}</text>
      ${chartSeries.map((item, index) => {
        const color = seriesColor(item.label || item.experiment || "unknown", index);
        const points = (item.windows || []).map((window, pointIndex) => {
          const x = margin.left + (referenceWindows.length === 1 ? chartWidth : (pointIndex / (referenceWindows.length - 1)) * chartWidth);
          const y = margin.top + chartHeight - ((window.p75_lcp_ms ?? 0) / maxY) * chartHeight;
          return { ...window, x, y };
        });
        return `
          <path class="line" d="${buildLinePath(points)}" stroke="${color}"></path>
          <g class="points">
            ${points.map((point) => `
              <circle cx="${point.x}" cy="${point.y}" r="4" fill="${color}">
                <title>${escapeHtml(item.label || item.experiment || "unknown")} · ${point.p75_lcp_ms ?? 0} ms, ${point.event_count ?? 0} events, ${formatTimestamp(point.window_start)} - ${formatTimestamp(point.window_end)}</title>
              </circle>
            `).join("")}
          </g>
        `;
      }).join("")}
    </svg>
    <div class="trend-legend">
      ${legendItems.map((item) => `
        <div class="legend-item">
          <span class="legend-swatch" style="background:${item.color}"></span>
          <span>${escapeHtml(item.label)}</span>
        </div>
      `).join("")}
    </div>
  `;
  if (populatedValues.length === 0) {
    trend.insertAdjacentHTML("afterbegin", `<div class="empty chart-note">No recent LCP data in this range.</div>`);
  }
}

function renderExperiments(items) {
  experiments.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.experiment)}</td>
      <td>${item.event_count}</td>
      <td>${item.p75_lcp_ms} ms</td>
      <td>${escapeHtml(item.last_seen_timestamp || "")}</td>
    `;
    experiments.append(row);
  }
}

function renderQueueStatus(status) {
  queueCount.textContent = `${status.message_count ?? 0}`;
  queueName.textContent = status.queue_name || "page-events";
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

function formatAxisTimestamp(value, windowSeconds) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return windowSeconds < 60 ? date.toISOString().slice(11, 19) : date.toISOString().slice(11, 16);
}

function formatBucketLabel(seconds) {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds % 3600 === 0) {
    return `${seconds / 3600}h`;
  }
  return `${seconds / 60}m`;
}

function niceMax(value) {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

function seriesColor(label, index) {
  if (label === "unknown") {
    return "#6b7280";
  }
  const hue = Math.round((index * 137.508) % 360);
  return `hsl(${hue} 72% 44%)`;
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

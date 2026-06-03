const dataSourceSelect = document.querySelector("#dataSource");
const dealTypeSelect = document.querySelector("#dealType");
const propertyTypeSelect = document.querySelector("#propertyType");
const roomsSelect = document.querySelector("#rooms");
const locationScopeSelect = document.querySelector("#locationScope");
const periodButtons = document.querySelectorAll(".period-button");
const statusText = document.querySelector("#statusText");
const currentMetric = document.querySelector("#currentMetric");
const change7Metric = document.querySelector("#change7Metric");
const change30Metric = document.querySelector("#change30Metric");
const trendMetric = document.querySelector("#trendMetric");
const sourceMetric = document.querySelector("#sourceMetric");
const domriaStatusMetric = document.querySelector("#domriaStatusMetric");
const collectedTodayMetric = document.querySelector("#collectedTodayMetric");
const missingTodayMetric = document.querySelector("#missingTodayMetric");
const lastUpdateMetric = document.querySelector("#lastUpdateMetric");
const canvas = document.querySelector("#listingChart");

let selectedPeriod = "30";
let sourceInitialized = false;
let chart;
let fallbackData;
let chartJsRequested = false;

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const source = params.get("data_source");
  const dealType = params.get("deal_type");
  const propertyType = params.get("property_type");
  const rooms = params.get("rooms");
  const locationScope = params.get("location_scope");
  const period = params.get("period");

  if (source && dataSourceSelect.querySelector(`option[value="${source}"]`)) {
    dataSourceSelect.value = source;
    sourceInitialized = true;
  } else {
    dataSourceSelect.value = "all";
    sourceInitialized = false;
  }

  if (dealType && dealTypeSelect.querySelector(`option[value="${dealType}"]`)) {
    dealTypeSelect.value = dealType;
  }
  if (propertyType && propertyTypeSelect.querySelector(`option[value="${propertyType}"]`)) {
    propertyTypeSelect.value = propertyType;
  }
  if (rooms && roomsSelect.querySelector(`option[value="${rooms}"]`)) {
    roomsSelect.value = rooms;
  }
  if (locationScope && locationScopeSelect.querySelector(`option[value="${locationScope}"]`)) {
    locationScopeSelect.value = locationScope;
  }
  if (period && document.querySelector(`.period-button[data-period="${period}"]`)) {
    selectedPeriod = period;
    periodButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.period === period);
    });
  }
}

function updateUrlState() {
  const params = new URLSearchParams();
  params.set("deal_type", dealTypeSelect.value);
  params.set("property_type", propertyTypeSelect.value);
  params.set("rooms", roomsSelect.value);
  params.set("location_scope", locationScopeSelect.value);
  params.set("period", selectedPeriod);
  params.set("data_source", dataSourceSelect.value || "all");
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}
function formatNumber(value) {
  return new Intl.NumberFormat("uk-UA").format(value);
}

function formatMetric(value) {
  if (typeof value === "number") {
    return formatNumber(value);
  }
  return value || "0";
}

function formatChange(value) {
  if (typeof value !== "number") {
    return value || "0";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}`;
}

function formatTimestamp(value) {
  if (!value) {
    return "Немає даних";
  }
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function setMetrics(metrics) {
  currentMetric.textContent = formatMetric(metrics.current);
  change7Metric.textContent = formatChange(metrics.change7);
  change30Metric.textContent = formatChange(metrics.change30);
  trendMetric.textContent = formatMetric(metrics.trend);
}

function setSource(source) {
  sourceMetric.textContent = source.label;
  domriaStatusMetric.textContent = source.status;
}

function setStatusSnapshot(snapshot) {
  collectedTodayMetric.textContent = formatNumber(snapshot.collected_today.length);
  missingTodayMetric.textContent = formatNumber(snapshot.missing_today.length);
  lastUpdateMetric.textContent = formatTimestamp(snapshot.last_successful_update);
}

function syncRoomFilter() {
  const supportsRooms = propertyTypeSelect.value === "apartments";
  roomsSelect.disabled = !supportsRooms;
  if (!supportsRooms) {
    roomsSelect.value = "all";
  }
}

function syncSourceOptions(availability) {
  ["olx", "domria", "demo"].forEach((key) => {
    const option = dataSourceSelect.querySelector(`option[value="${key}"]`);
    if (option) {
      option.disabled = false;
    }
  });
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: "index",
      intersect: false,
    },
    plugins: {
      legend: {
        display: true,
        labels: {
          boxWidth: 12,
          color: "#111111",
        },
      },
      tooltip: {
        callbacks: {
          label(context) {
            return `${context.dataset.label}: ${formatNumber(context.parsed.y)}`;
          },
        },
      },
    },
    scales: {
      x: {
        grid: {
          display: false,
        },
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          color: "#65655e",
        },
      },
      y: {
        beginAtZero: false,
        ticks: {
          color: "#65655e",
          callback: formatNumber,
        },
        grid: {
          color: "#eeeeea",
        },
      },
    },
  };
}

function drawFallbackChart(data) {
  fallbackData = data;
  const pixelRatio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 300;
  const height = canvas.clientHeight || 180;
  canvas.width = width * pixelRatio;
  canvas.height = height * pixelRatio;
  const context = canvas.getContext("2d");
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);

  const allValues = data.datasets.flatMap((dataset) => dataset.data.filter((value) => value !== null));
  if (!allValues.length) {
    return;
  }

  const padding = 32;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = Math.max(1, max - min);

  context.strokeStyle = "#eeeeea";
  context.lineWidth = 1;
  for (let index = 0; index < 4; index += 1) {
    const y = padding + ((height - padding * 2) / 3) * index;
    context.beginPath();
    context.moveTo(padding, y);
    context.lineTo(width - padding, y);
    context.stroke();
  }

  data.datasets.forEach((dataset) => {
    context.strokeStyle = dataset.borderColor || "#111111";
    context.lineWidth = 2;
    context.beginPath();
    let hasPoint = false;
    dataset.data.forEach((value, index) => {
      if (value === null) {
        return;
      }
      const x = padding + ((width - padding * 2) / Math.max(1, data.labels.length - 1)) * index;
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      if (!hasPoint) {
        context.moveTo(x, y);
        hasPoint = true;
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();
  });

  context.fillStyle = "#111111";
  context.font = "12px system-ui, sans-serif";
  context.fillText(formatNumber(max), padding, 18);
  context.fillText(formatNumber(min), padding, height - 8);
}

function updateChart(data) {
  if (!window.Chart) {
    drawFallbackChart(data);
    return;
  }

  if (chart) {
    chart.data.labels = data.labels;
    chart.data.datasets = data.datasets;
    chart.update();
  } else {
    chart = new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: data.datasets,
      },
      options: chartOptions(),
    });
  }
}

function loadChartJs() {
  if (window.Chart || chartJsRequested) {
    return;
  }
  chartJsRequested = true;
  const script = document.createElement("script");
  script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js";
  script.async = true;
  script.onload = () => {
    if (fallbackData && !chart) {
      updateChart(fallbackData);
    }
  };
  document.head.appendChild(script);
}

async function loadAnalytics() {
  syncRoomFilter();
  statusText.textContent = "Завантаження даних...";
  const params = new URLSearchParams({
    deal_type: dealTypeSelect.value,
    property_type: propertyTypeSelect.value,
    rooms: roomsSelect.value,
    location_scope: locationScopeSelect.value,
    period: selectedPeriod,
  });

  if (sourceInitialized) {
    params.set("data_source", dataSourceSelect.value);
  }

  const response = await fetch(`/api/analytics?${params}`);
  if (!response.ok) {
    throw new Error("Analytics request failed");
  }

  const data = await response.json();
  dataSourceSelect.value = data.selected_source;
  sourceInitialized = true;
  syncSourceOptions(data.source_availability);
  setMetrics(data.metrics);
  setSource(data.source);
  updateChart(data);
  updateUrlState();

  if (data.labels.length) {
    statusText.textContent = `Показано дат: ${data.labels.length}`;
  } else {
    statusText.textContent = "Немає даних для вибраного джерела та фільтрів.";
  }
}

async function loadStatusSnapshot() {
  const response = await fetch("/api/analytics/status");
  if (!response.ok) {
    throw new Error("Status request failed");
  }
  const data = await response.json();
  setStatusSnapshot(data);
}

function handleLoadError() {
  statusText.textContent = "Не вдалося завантажити дані";
}

function selectPeriod(button) {
  periodButtons.forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  selectedPeriod = button.dataset.period;
  loadAnalytics().catch(handleLoadError);
}

periodButtons.forEach((button) => {
  button.addEventListener("click", () => selectPeriod(button));
});

dataSourceSelect.addEventListener("change", () => {
  sourceInitialized = true;
  loadAnalytics().catch(handleLoadError);
});

[dealTypeSelect, propertyTypeSelect, roomsSelect, locationScopeSelect].forEach((select) => {
  select.addEventListener("change", () => {
    loadAnalytics().catch(handleLoadError);
  });
});

window.addEventListener("load", () => {
  applyUrlState();
  loadAnalytics().catch(handleLoadError);
  loadStatusSnapshot().catch(() => {
    lastUpdateMetric.textContent = "Немає даних";
  });
  loadChartJs();
});

window.addEventListener("resize", () => {
  if (!window.Chart && fallbackData) {
    drawFallbackChart(fallbackData);
  }
});

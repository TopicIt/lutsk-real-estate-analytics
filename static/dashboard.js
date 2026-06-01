const saleCanvas = document.querySelector("#saleTrendChart");
const rentCanvas = document.querySelector("#rentTrendChart");
const saleStatusText = document.querySelector("#saleStatusText");
const rentStatusText = document.querySelector("#rentStatusText");
const domriaSaleMetric = document.querySelector("#domriaSaleMetric");
const olxSaleMetric = document.querySelector("#olxSaleMetric");
const domriaRentMetric = document.querySelector("#domriaRentMetric");
const olxRentMetric = document.querySelector("#olxRentMetric");
const lastUpdateMetric = document.querySelector("#lastUpdateMetric");
const autoRunMetric = document.querySelector("#autoRunMetric");
const collectedTodayMetric = document.querySelector("#collectedTodayMetric");
const missingTodayMetric = document.querySelector("#missingTodayMetric");

let saleChart;
let rentChart;
let fallbackSaleData;
let fallbackRentData;
let chartJsRequested = false;

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("uk-UA").format(value);
}

function formatTimestamp(value) {
  if (!value) {
    return "-";
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

function drawFallbackChart(canvas, data) {
  const pixelRatio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 300;
  const height = canvas.clientHeight || 180;
  canvas.width = width * pixelRatio;
  canvas.height = height * pixelRatio;
  const context = canvas.getContext("2d");
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);

  const values = data.datasets.flatMap((dataset) => dataset.data.filter((value) => value !== null && value !== undefined));
  if (!values.length) {
    context.fillStyle = "#65655e";
    context.font = "14px system-ui, sans-serif";
    context.fillText("Немає даних", 24, 34);
    return;
  }

  const padding = 34;
  const min = Math.min(...values);
  const max = Math.max(...values);
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
      if (value === null || value === undefined) {
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

function updateChart(canvas, data, currentChart) {
  if (!window.Chart) {
    drawFallbackChart(canvas, data);
    return null;
  }

  if (currentChart) {
    currentChart.data.labels = data.labels;
    currentChart.data.datasets = data.datasets;
    currentChart.update();
    return currentChart;
  }

  return new Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: data.datasets,
    },
    options: chartOptions(),
  });
}

function setStatus(element, data) {
  const hasValues = data.datasets.some((dataset) => dataset.data.some((value) => value !== null && value !== undefined));
  element.textContent = hasValues ? `Показано дат: ${data.labels.length}` : "Немає даних для цього тренду.";
}

function setMetrics(data) {
  domriaSaleMetric.textContent = formatNumber(data.sale.latest.domria);
  olxSaleMetric.textContent = formatNumber(data.sale.latest.olx);
  domriaRentMetric.textContent = formatNumber(data.rent.latest.domria);
  olxRentMetric.textContent = formatNumber(data.rent.latest.olx);
  lastUpdateMetric.textContent = formatTimestamp(data.last_update);
}

function setCollectionStatus(data) {
  autoRunMetric.textContent = formatTimestamp(data.last_domria_run_time);
  collectedTodayMetric.textContent = formatNumber(data.categories_collected_today.length);
  missingTodayMetric.textContent = formatNumber(data.categories_missing_today.length);
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
    if (fallbackSaleData && !saleChart) {
      saleChart = updateChart(saleCanvas, fallbackSaleData, saleChart);
    }
    if (fallbackRentData && !rentChart) {
      rentChart = updateChart(rentCanvas, fallbackRentData, rentChart);
    }
  };
  document.head.appendChild(script);
}

async function loadDashboard() {
  saleStatusText.textContent = "Завантаження даних...";
  rentStatusText.textContent = "Завантаження даних...";
  const response = await fetch("/api/analytics/trends");
  if (!response.ok) {
    throw new Error("Dashboard request failed");
  }
  const data = await response.json();
  setMetrics(data);
  fallbackSaleData = data.sale;
  fallbackRentData = data.rent;
  saleChart = updateChart(saleCanvas, data.sale, saleChart);
  rentChart = updateChart(rentCanvas, data.rent, rentChart);
  setStatus(saleStatusText, data.sale);
  setStatus(rentStatusText, data.rent);
}

async function loadCollectionStatus() {
  const response = await fetch("/api/collection/status");
  if (!response.ok) {
    throw new Error("Collection status request failed");
  }
  setCollectionStatus(await response.json());
}

window.addEventListener("load", () => {
  loadDashboard().catch(() => {
    saleStatusText.textContent = "Не вдалося завантажити дані.";
    rentStatusText.textContent = "Не вдалося завантажити дані.";
  });
  loadCollectionStatus().catch(() => {
    autoRunMetric.textContent = "-";
    collectedTodayMetric.textContent = "-";
    missingTodayMetric.textContent = "-";
  });
  loadChartJs();
});

window.addEventListener("resize", () => {
  if (!window.Chart) {
    if (fallbackSaleData) {
      drawFallbackChart(saleCanvas, fallbackSaleData);
    }
    if (fallbackRentData) {
      drawFallbackChart(rentCanvas, fallbackRentData);
    }
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const sidebar = document.getElementById("sidebar");
  if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => {
      const open = sidebar.classList.toggle("open");
      menuToggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", (event) => {
      if (sidebar.classList.contains("open") && !sidebar.contains(event.target) && !menuToggle.contains(event.target)) {
        sidebar.classList.remove("open");
        menuToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  const input = document.getElementById("dataset");
  const dropzone = document.getElementById("dropzone");
  const fileName = document.getElementById("file-name");
  const fileMeta = document.getElementById("file-meta");
  const uploadForm = document.getElementById("upload-form");
  if (input && dropzone) {
    const renderFile = (file) => {
      if (!file) return;
      fileName.textContent = file.name;
      fileMeta.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB · Ready to analyze`;
    };
    input.addEventListener("change", () => renderFile(input.files[0]));
    ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("drag-over");
    }));
    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      renderFile(file);
    });
    uploadForm.addEventListener("submit", (event) => {
      const file = input.files[0];
      if (!file || !file.name.toLowerCase().endsWith(".csv")) {
        event.preventDefault();
        fileMeta.textContent = "Choose a .csv file to continue.";
      } else if (file.size > 16 * 1024 * 1024) {
        event.preventDefault();
        fileMeta.textContent = "That file exceeds the 16 MB limit.";
      }
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  if (typeof Chart === "undefined") return;
  Chart.defaults.color = "#929bb1";
  Chart.defaults.font.family = '"DM Sans", "Segoe UI", sans-serif';
  Chart.defaults.font.size = 9;
  const palette = ["#a78bfa", "#62cbd3", "#f1b878", "#ef829b", "#7cdaa6"];
  const clusterCanvas = document.querySelector('[data-chart="clusters"]');
  if (clusterCanvas) {
    const groups = JSON.parse(clusterCanvas.dataset.points);
    new Chart(clusterCanvas, {
      type: "bar",
      data: {
        labels: groups.map((group) => `Group ${group.id + 1}`),
        datasets: [{ data: groups.map((group) => group.size), backgroundColor: groups.map((_, i) => palette[i % palette.length]), borderRadius: 4, barThickness: 18 }],
      },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => `${context.raw} records (${groups[context.dataIndex].share}%)` } } }, scales: { x: { grid: { display: false }, border: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#ffffff0c" }, border: { display: false } } } },
    });
  }

  const pcaCanvas = document.querySelector('[data-chart="pca"]');
  if (pcaCanvas) {
    const points = JSON.parse(pcaCanvas.dataset.points);
    const groups = JSON.parse(pcaCanvas.dataset.clusters);
    const datasets = groups.length
      ? [...new Set(groups.map((point) => point.cluster))].map((cluster) => ({
          label: `Group ${cluster + 1}`,
          data: points.filter((_, index) => groups[index] && groups[index].cluster === cluster).map((point) => ({ x: point.x, y: point.y })),
          backgroundColor: palette[cluster % palette.length],
          pointRadius: 2.5,
          pointHoverRadius: 5,
        }))
      : [{ label: "Records", data: points, backgroundColor: palette[0], pointRadius: 2.5 }];
    new Chart(pcaCanvas, {
      type: "scatter",
      data: { datasets },
      options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { boxWidth: 7, boxHeight: 7, usePointStyle: true, padding: 10 } } }, scales: { x: { title: { display: true, text: "Principal component 1" }, grid: { color: "#ffffff0c" }, border: { display: false } }, y: { title: { display: true, text: "Principal component 2" }, grid: { color: "#ffffff0c" }, border: { display: false } } } },
    });
  }

  const heatmapCanvas = document.querySelector('[data-chart="heatmap"]');
  if (heatmapCanvas) {
    const heatmap = JSON.parse(heatmapCanvas.dataset.heatmap);
    const count = heatmap.labels.length;
    new Chart(heatmapCanvas, {
      type: "matrix",
      data: {
        datasets: [{
          data: heatmap.values.flatMap((row, y) => row.map((value, x) => ({ x, y, v: value }))),
          backgroundColor: (context) => {
            const value = context.dataset.data[context.dataIndex]?.v;
            if (value === null || value === undefined) return "#252b40";
            const alpha = Math.min(0.85, Math.abs(value) * 0.8 + 0.08);
            return value >= 0 ? `rgba(125, 102, 237, ${alpha})` : `rgba(83, 192, 198, ${alpha})`;
          },
          borderWidth: 1,
          borderColor: "#151a2c",
          width: (context) => Math.max(8, Math.min(25, context.chart.chartArea?.width / count - 2 || 14)),
          height: (context) => Math.max(8, Math.min(25, context.chart.chartArea?.height / count - 2 || 14)),
        }],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: () => "", label: (context) => `${heatmap.labels[context.raw.y]} × ${heatmap.labels[context.raw.x]}: ${context.raw.v === null ? "not available" : Number(context.raw.v).toFixed(2)}` } } },
        scales: {
          x: { type: "linear", min: -0.5, max: count - 0.5, ticks: { stepSize: 1, callback: (value) => heatmap.labels[value] || "", maxRotation: 45, minRotation: 25 }, grid: { display: false }, border: { display: false } },
          y: { type: "linear", min: -0.5, max: count - 0.5, reverse: true, ticks: { stepSize: 1, callback: (value) => heatmap.labels[value] || "" }, grid: { display: false }, border: { display: false } },
        },
      },
    });
  }
});

// ABOUTME: Renders the dashboard pie chart cards with Chart.js from each canvas's data-pie-chart JSON
// ABOUTME: Loaded only by pages that use the pie_chart_card macro (assembly dashboard, showcase)

import { ArcElement, Chart, Legend, PieController, Tooltip } from "chart.js";

Chart.register(PieController, ArcElement, Tooltip, Legend);

// The macro emits colours as CSS custom-property references (e.g. "var(--color-info-600)")
// so slices stay on the semantic palette; the canvas API needs concrete values, so they
// are resolved against the canvas element at build time.
const CSS_VAR = /^var\((--[^,)]+)\)$/;

function resolveColor(color, element) {
  const match = CSS_VAR.exec(color.trim());
  if (!match) {
    return color;
  }
  return getComputedStyle(element).getPropertyValue(match[1]).trim() || color;
}

function buildChart(canvas) {
  const config = JSON.parse(canvas.dataset.pieChart);
  const cardColor = resolveColor("var(--color-tables-cards)", canvas);
  const textColor = resolveColor("var(--color-headings)", canvas);

  new Chart(canvas, {
    type: "pie",
    data: {
      labels: config.labels,
      datasets: [
        {
          data: config.values,
          backgroundColor: config.colors.map((color) =>
            resolveColor(color, canvas),
          ),
          // With gaps, a thin card-coloured border reads as a divider between slices.
          borderColor: cardColor,
          borderWidth: config.gaps ? 2 : 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          // legend: false → the layout renders one shared legend for the row
          // (see pie_chart_legend in the pie_chart_card component).
          display: config.legend !== false,
          position: "bottom",
          labels: { color: textColor, boxWidth: 10, boxHeight: 10 },
        },
        tooltip: {
          callbacks: {
            // The macro precomputes "Label 50% (10)" per slice, so the tooltip,
            // the aria-label and any server-side test all show the same text.
            // No title: it would just repeat the label.
            title: () => "",
            label: (context) => config.tooltips[context.dataIndex],
          },
        },
      },
    },
  });
}

function init() {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  document.querySelectorAll("canvas[data-pie-chart]").forEach((canvas) => {
    // Guarded per canvas: one bad payload or Chart.js throw must not blank
    // every later card on the page.
    try {
      buildChart(canvas);
    } catch (error) {
      console.error("pie-chart: failed to render a card", error);
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

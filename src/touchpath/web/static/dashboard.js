/* Dashboard behaviour: a grouped bar chart drawn as inline SVG, and the
   incrementality calculator.

   No charting library: the chart is small enough to draw directly, which keeps
   the page dependency-free (nothing to load from a CDN, works offline) and lets
   the marks follow the house rules exactly - 2px surface gaps between adjacent
   bars, 4px rounded tops anchored to the baseline, recessive grid, hover
   tooltip, and a table view underneath for anyone who cannot rely on colour.
   Colours come from CSS custom properties, so light and dark stay in step. */

(function () {
  const payloadEl = document.getElementById("payload");
  const data = payloadEl ? JSON.parse(payloadEl.textContent || "null") : null;

  const css = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const SVG = "http://www.w3.org/2000/svg";
  const el = (name, attrs = {}) => {
    const node = document.createElementNS(SVG, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };

  /* ------------------------------------------------------------- the chart */
  function drawChart(root, channels, series) {
    const surface = css("--surface-1");
    const border = css("--border");
    const text = css("--text-secondary");
    const muted = css("--text-muted");

    const width = root.clientWidth || 900;
    const height = root.clientHeight || 380;
    const pad = { top: 14, right: 12, bottom: 46, left: 44 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const maxValue = Math.max(10, ...series.flatMap((s) => s.values));
    const step = maxValue > 60 ? 20 : maxValue > 30 ? 10 : 5;
    const top = Math.ceil(maxValue / step) * step;
    const y = (value) => pad.top + plotH - (value / top) * plotH;

    const groupW = plotW / channels.length;
    const barW = Math.max(3, (groupW * 0.78) / series.length);
    const groupPad = (groupW - barW * series.length) / 2;

    const svg = el("svg", {
      viewBox: `0 0 ${width} ${height}`,
      width: "100%",
      height: "100%",
      role: "img",
      "aria-label": "Revenue share by channel for each attribution model",
    });

    // horizontal grid + y axis labels (recessive)
    for (let value = 0; value <= top; value += step) {
      svg.appendChild(
        el("line", {
          x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value),
          stroke: border, "stroke-width": 1,
        })
      );
      const label = el("text", {
        x: pad.left - 8, y: y(value) + 4, "text-anchor": "end",
        fill: muted, "font-size": 11,
      });
      label.textContent = `${value}%`;
      svg.appendChild(label);
    }

    // bars
    channels.forEach((channel, ci) => {
      const groupX = pad.left + ci * groupW + groupPad;

      // invisible hit area covering the whole group, for a forgiving hover target
      const hit = el("rect", {
        x: pad.left + ci * groupW, y: pad.top, width: groupW, height: plotH,
        fill: "transparent",
      });
      hit.dataset.channel = ci;
      svg.appendChild(hit);

      series.forEach((s, si) => {
        const value = s.values[ci] || 0;
        const barH = Math.max(1, pad.top + plotH - y(value));
        const bar = el("rect", {
          x: groupX + si * barW,
          y: y(value),
          width: Math.max(1, barW - 2), // 2px surface gap between adjacent bars
          height: barH,
          rx: Math.min(4, barW / 2),    // rounded data-end
          fill: s.color,
          stroke: surface,
          "stroke-width": 0,
        });
        bar.dataset.channel = ci;
        svg.appendChild(bar);
      });

      const label = el("text", {
        x: pad.left + ci * groupW + groupW / 2,
        y: height - 26,
        "text-anchor": "middle",
        fill: text,
        "font-size": 11,
      });
      label.textContent = channel.length > 13 ? channel.slice(0, 12) + "…" : channel;
      svg.appendChild(label);
    });

    // baseline
    svg.appendChild(
      el("line", {
        x1: pad.left, x2: width - pad.right, y1: pad.top + plotH, y2: pad.top + plotH,
        stroke: border, "stroke-width": 1,
      })
    );

    root.innerHTML = "";
    root.appendChild(svg);

    /* hover tooltip */
    const tip = document.createElement("div");
    tip.className = "tooltip";
    tip.hidden = true;
    root.appendChild(tip);

    svg.addEventListener("mousemove", (event) => {
      const target = event.target.closest("[data-channel]");
      if (!target) {
        tip.hidden = true;
        return;
      }
      const ci = Number(target.dataset.channel);
      const rows = series
        .map(
          (s) =>
            `<div class="tip-row"><i class="swatch" style="background:${s.color}"></i>` +
            `<span>${s.label}</span><b>${s.values[ci].toFixed(1)}%</b></div>`
        )
        .join("");
      tip.innerHTML = `<div class="tip-title">${channels[ci]}</div>${rows}`;
      tip.hidden = false;

      const bounds = root.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      tip.style.left = `${Math.min(Math.max(x + 14, 8), bounds.width - tip.offsetWidth - 8)}px`;
      tip.style.top = `${Math.max(event.clientY - bounds.top - 10, 8)}px`;
    });
    svg.addEventListener("mouseleave", () => { tip.hidden = true; });
  }

  if (data && document.getElementById("shareChart")) {
    const palette = [1, 2, 3, 4, 5, 6, 7].map((i) => css(`--series-${i}`));
    const series = data.series.map((s, i) => ({
      label: s.label,
      values: s.share,
      color: palette[i % palette.length],
    }));
    if (data.ground_truth) {
      series.unshift({
        label: "True influence",
        values: data.ground_truth,
        color: css("--series-truth"),
      });
    }

    document.getElementById("legend").innerHTML = series
      .map((s) => `<span><i class="swatch" style="background:${s.color}"></i>${s.label}</span>`)
      .join("");

    const root = document.getElementById("shareChart");
    const render = () => drawChart(root, data.channels, series);
    render();

    let timer;
    window.addEventListener("resize", () => {
      clearTimeout(timer);
      timer = setTimeout(render, 150);
    });
  }

  /* ------------------------------------------------- incrementality panel */
  const button = document.getElementById("incBtn");
  if (!button) return;

  const out = document.getElementById("incOut");
  const value = (id) => parseInt(document.getElementById(id).value, 10);

  button.addEventListener("click", async () => {
    out.innerHTML = '<p class="muted">calculating…</p>';
    try {
      const response = await fetch("/api/incrementality", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          treatment_users: value("tu"),
          treatment_conversions: value("tc"),
          control_users: value("cu"),
          control_conversions: value("cc"),
        }),
      });
      const r = await response.json();
      if (!response.ok) {
        out.innerHTML = `<div class="error">${r.detail || "could not calculate"}</div>`;
        return;
      }

      const verdict = r.significant
        ? '<span class="pill good">significant</span>'
        : '<span class="pill warn">not significant</span>';

      out.innerHTML = `
        <div class="tiles">
          <div class="tile">
            <div class="label">Relative lift</div>
            <div class="value">${r.relative_lift > 0 ? "+" : ""}${r.relative_lift}%</div>
            <div class="note">${r.treatment_rate}% vs ${r.control_rate}% conversion</div>
          </div>
          <div class="tile">
            <div class="label">Incremental conversions</div>
            <div class="value">${r.incremental_conversions.toLocaleString()}</div>
            <div class="note">caused by the channel</div>
          </div>
          <div class="tile">
            <div class="label">95% interval</div>
            <div class="value" style="font-size:17px">${r.ci_low}% … ${r.ci_high}%</div>
            <div class="note">absolute difference in rate</div>
          </div>
          <div class="tile">
            <div class="label">p-value</div>
            <div class="value">${r.p_value}</div>
            <div class="note">${verdict}</div>
          </div>
        </div>`;
    } catch (error) {
      out.innerHTML = `<div class="error">${error}</div>`;
    }
  });
})();

// thong-ke.js — Statistics page
(function() {
  const user = initPage('statistics');
  if (!user) return;

  window.loadTrend = loadTrend;

  loadByType();
  loadRatio();
  loadTrend();
  loadHeatmap();

  let typeChart = null, ratioChart = null, trendChart = null;

  async function loadByType() {
    try {
      const data = await api('GET', '/api/statistics/by-type');
      const labels = data.map(d => SOUND_TYPE_LABELS[d.sound_type]?.label || d.sound_type);
      const values = data.map(d => d.count);
      const colors = data.map(d => {
        const c = { dap_pha: '#EF4444', scream: '#DC2626', help: '#F97316', threat: '#EAB308', argument: '#6366f1' };
        return c[d.sound_type] || '#94a3b8';
      });

      const ctx = document.getElementById('type-chart').getContext('2d');
      if (typeChart) typeChart.destroy();
      typeChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{ label: 'Số lượng', data: values, backgroundColor: colors, borderRadius: 8, barThickness: 40 }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } }, x: { grid: { display: false } } }
        }
      });
    } catch (err) { console.error(err); }
  }

  async function loadRatio() {
    try {
      const data = await api('GET', '/api/statistics/ratio');
      const ctx = document.getElementById('ratio-chart').getContext('2d');
      if (ratioChart) ratioChart.destroy();
      ratioChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['Đã xác nhận', 'Báo động giả', 'Chờ xử lý'],
          datasets: [{
            data: [data.confirmed, data.false_alarm, data.pending],
            backgroundColor: ['#DC2626', '#94a3b8', '#F97316'],
            borderWidth: 0,
            hoverOffset: 8
          }]
        },
        options: {
          responsive: true,
          cutout: '60%',
          plugins: {
            legend: { position: 'bottom', labels: { padding: 16, font: { size: 12 } } }
          }
        }
      });
    } catch (err) { console.error(err); }
  }

  async function loadTrend() {
    try {
      const period = document.getElementById('trend-period').value;
      const data = await api('GET', `/api/statistics/trend?period=${period}`);
      const ctx = document.getElementById('trend-chart').getContext('2d');

      if (trendChart) trendChart.destroy();
      trendChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.map(d => d.date),
          datasets: [{
            label: 'Cảnh báo',
            data: data.map(d => d.count),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.08)',
            fill: true,
            tension: 0.3,
            pointRadius: 4,
            pointBackgroundColor: '#3b82f6',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } }, x: { grid: { display: false } } }
        }
      });
    } catch (err) { console.error(err); }
  }

  async function loadHeatmap() {
    try {
      const data = await api('GET', '/api/statistics/heatmap');
      if (data.length === 0) {
        document.getElementById('heatmap-container').innerHTML = '<p style="color:var(--text-muted);text-align:center;">Chưa có dữ liệu</p>';
        return;
      }

      // Find max for color scaling
      let maxVal = 0;
      data.forEach(row => row.hours.forEach(h => { if (h.count > maxVal) maxVal = h.count; }));
      if (maxVal === 0) maxVal = 1;

      let html = '<table style="width:100%;font-size:11px;border-collapse:collapse;">';
      html += '<thead><tr><th style="text-align:left;padding:4px 8px;">Khu vực</th>';
      for (let h = 0; h < 24; h++) {
        html += `<th style="padding:4px;text-align:center;min-width:28px;">${h}</th>`;
      }
      html += '</tr></thead><tbody>';

      data.forEach(row => {
        html += `<tr><td style="padding:4px 8px;white-space:nowrap;font-weight:500;">${row.area}</td>`;
        row.hours.forEach(h => {
          const intensity = h.count / maxVal;
          const bg = intensity === 0 ? 'var(--bg-hover)' :
                     `rgba(220, 38, 38, ${0.15 + intensity * 0.7})`;
          const color = intensity > 0.5 ? '#fff' : 'var(--text)';
          html += `<td style="padding:4px;text-align:center;background:${bg};color:${color};border-radius:3px;" title="${row.area} — ${h.hour}:00: ${h.count} cảnh báo">${h.count || ''}</td>`;
        });
        html += '</tr>';
      });

      html += '</tbody></table>';
      document.getElementById('heatmap-container').innerHTML = html;
    } catch (err) { console.error(err); }
  }
})();

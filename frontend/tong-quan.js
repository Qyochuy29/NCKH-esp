// tong-quan.js — Dashboard page logic
(function () {
  let hourlyChart = null;
  const user = initPage('dashboard');
  if (!user) return;

  loadKPIs();
  loadDevicesMap(1);
  loadAlertFeed();
  loadHourlyChart();

  // Floor tabs
  const floorTabs = document.getElementById('floor-tabs');
  if (floorTabs) {
    floorTabs.addEventListener('click', (e) => {
      if (e.target.classList.contains('floor-tab')) {
        document.querySelectorAll('.floor-tab').forEach(t => t.classList.remove('active'));
        e.target.classList.add('active');
        loadDevicesMap(parseInt(e.target.dataset.floor));
      }
    });
  }

  // WebSocket: live alert feed
  onWsEvent('new-alert', (alert) => {
    prependAlertToFeed(alert);
    loadKPIs(); // Refresh KPIs
  });

  async function loadKPIs() {
    try {
      const data = await api('GET', '/api/statistics/summary');
      document.getElementById('kpi-devices').textContent = data.devices_online;
      document.getElementById('kpi-devices-sub').textContent = `/ ${data.total_devices} tổng`;
      document.getElementById('kpi-alerts').textContent = data.alerts_today;
      document.getElementById('kpi-urgent').textContent = data.pending_urgent;
      document.getElementById('kpi-response').textContent = data.avg_response_minutes + ' phút';
    } catch (err) {
      console.error('Failed to load KPIs:', err);
    }
  }

  async function loadDevicesMap(floor) {
    try {
      const devices = await api('GET', '/api/devices');
      renderDevicesTable(devices);
    } catch (err) {
      console.error('Failed to load devices:', err);
    }
  }

  function renderDevicesTable(devices) {
    const tbody = document.getElementById('dashboard-devices-tbody');
    if (!tbody) return;

    if (devices.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">Không có thiết bị nào</td></tr>';
      return;
    }

    let html = '';
    devices.forEach(d => {
      const statusColor = d.status === 'online' ? 'var(--success)' :
        d.status === 'error' ? 'var(--danger)' : 'var(--text-muted)';
      const statusText = d.status === 'online' ? 'Trực tuyến' :
        d.status === 'error' ? 'Lỗi/Mất kết nối' : 'Ngoại tuyến';
      const areaName = d.area?.name || d.area || 'Không xác định';

      html += `
        <tr>
          <td><strong>${escapeHTML(d.name)}</strong></td>
          <td>${escapeHTML(areaName)}</td>
          <td><span style="color:${statusColor}; font-weight:600;"><i class="bi bi-circle-fill" style="font-size:0.5rem;vertical-align:middle;margin-right:4px;"></i> ${statusText}</span></td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  }

  async function loadAlertFeed() {
    try {
      const result = await api('GET', '/api/alerts?limit=10');
      const feed = document.getElementById('alert-feed');
      if (result.data.length === 0) {
        feed.innerHTML = '<div class="empty-state"><div class="empty-icon"><i class="bi bi-check-circle text-success"></i></div><h3>Không có cảnh báo</h3><p>Hệ thống đang hoạt động bình thường</p></div>';
        return;
      }
      feed.innerHTML = result.data.map(a => renderAlertItem(a)).join('');
    } catch (err) {
      console.error('Failed to load alerts:', err);
    }
  }

  function renderAlertItem(a) {
    const type = SOUND_TYPE_LABELS[a.sound_type] || { icon: '<i class="bi bi-question-circle"></i>', label: a.sound_type, color: 'info' };
    const status = STATUS_LABELS[a.status] || { label: a.status, class: 'badge-muted' };
    return `
      <div class="alert-card ${a.risk_level === 'high' ? 'severity-high' : 'severity-medium'}" style="padding:12px 16px;margin-bottom:8px;">
        <div class="alert-card-header" style="margin-bottom:4px;">
          <span class="alert-card-type">${type.icon} ${type.label}</span>
          <span class="badge ${status.class}">${status.label}</span>
        </div>
        <div class="alert-card-meta" style="margin-bottom: 8px;">
          <span><i class="bi bi-geo-alt"></i> ${escapeHTML(a.device?.area?.name || a.device?.area || '?')}</span>
          <span><i class="bi bi-bullseye"></i> ${riskLabel(a)}</span>
          <span><i class="bi bi-clock"></i> ${formatRelative(a.timestamp)}</span>
        </div>
        ${a.audio_file_url ? `<div style="margin-top: 8px;"><audio controls preload="none" style="height:32px; width: 100%;"><source src="${a.audio_file_url}">Trình duyệt không hỗ trợ</audio></div>` : ''}
      </div>
    `;
  }

  function prependAlertToFeed(alert) {
    const feed = document.getElementById('alert-feed');
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.innerHTML = renderAlertItem(alert);
    const el = div.firstElementChild;
    el.classList.add('alert-new');
    feed.prepend(el);

    // Keep max 10
    while (feed.children.length > 10) {
      feed.lastElementChild.remove();
    }
  }

  async function loadHourlyChart() {
    try {
      const data = await api('GET', '/api/statistics/hourly-today');
      const ctx = document.getElementById('hourly-chart').getContext('2d');

      if (hourlyChart) hourlyChart.destroy();
      hourlyChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.map(d => `${d.hour}:00`),
          datasets: [{
            label: 'Số cảnh báo',
            data: data.map(d => d.count),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.1)',
            fill: true,
            tension: 0.4,
            pointRadius: 3,
            pointBackgroundColor: '#3b82f6',
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { stepSize: 1 } },
            x: { grid: { display: false } }
          }
        }
      });
    } catch (err) {
      document.querySelector('#hourly-chart').parentElement.innerHTML = `<div style="color:red;padding:20px;font-family:monospace;">
        <b>Chart Error:</b> ${err.message}<br>
        <pre>${err.stack}</pre>
      </div>`;
      console.error('Failed to load hourly chart:', err);
    }
  }
})();

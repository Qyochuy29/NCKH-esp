// lich-su.js — Alert history page
(function() {
  const user = initPage('history');
  if (!user) return;

  let currentOffset = 0;
  const pageSize = 20;
  let currentData = [];

  window.loadHistory = loadHistory;
  window.exportCSV = exportCSV;
  window.closeModal = closeModal;
  window.showDetail = showDetail;
  window.goPage = goPage;

  loadAreaFilter();
  loadHistory();
  loadAudioHistory();

  async function loadAudioHistory() {
    const container = document.getElementById('audio-analysis-history');
    try {
      const result = await api('GET', '/api/alerts/analyses?limit=20');
      container.innerHTML = result.data.length ? result.data.map(a => `
        <p>${formatDateTime(a.created_at)} — ${escapeHTML(a.original_name || a.audio_file_url.split('/').pop())}
          <strong>${riskLabel(a.analysis)}</strong>
          <button class="btn btn-sm btn-outline" data-analysis-id="${escapeHTML(a.id)}">Xem transcript và bằng chứng</button>
        </p>`).join('') : '<p>Chưa có audio được phân tích.</p>';
      container.querySelectorAll('[data-analysis-id]').forEach(button => {
        button.addEventListener('click', async () => {
          try {
            const analysis = await api('GET', '/api/alerts/analyses/' + encodeURIComponent(button.dataset.analysisId));
            document.getElementById('modal-body').innerHTML = renderAnalysisReport(analysis);
            document.getElementById('detail-modal').classList.add('active');
          } catch (error) { showToast('Lỗi', error.message, 'danger'); }
        });
      });
    } catch (error) { container.textContent = 'Không tải được lịch sử phân tích audio: ' + error.message; }
  }

  // WebSocket: live updates for History
  onWsEvent('new-alert', (alert) => {
    // Reload history to ensure proper sorting/pagination
    loadHistory();
  });

  onWsEvent('alert-updated', (alert) => {
    loadHistory();
  });

  async function loadAreaFilter() {
    try {
      const areas = await api('GET', '/api/areas');
      const select = document.getElementById('filter-area');
      areas.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.name;
        opt.textContent = a.name;
        select.appendChild(opt);
      });
    } catch {}
  }

  async function loadHistory() {
    const from = document.getElementById('filter-from').value;
    const to = document.getElementById('filter-to').value;
    const type = document.getElementById('filter-type').value;
    const status = document.getElementById('filter-status').value;
    const area = document.getElementById('filter-area').value;

    let url = `/api/alerts?offset=${currentOffset}&limit=${pageSize}`;
    if (from) url += `&dateFrom=${from}`;
    if (to) url += `&dateTo=${to}T23:59:59`;
    if (type) url += `&soundType=${type}`;
    if (status) url += `&status=${status}`;
    if (area) url += `&area=${encodeURIComponent(area)}`;

    try {
      const result = await api('GET', url);
      currentData = result.data;
      renderTable(result.data);
      const currentPage = Math.floor(currentOffset / pageSize) + 1;
      window.renderPagination(result.total, pageSize, currentPage, 'pagination', goPage);
    } catch (err) {
      showToast('Lỗi', err.message, 'danger');
    }
  }

  function renderTable(data) {
    const tbody = document.getElementById('history-tbody');
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted);">Không có dữ liệu</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(a => {
      const type = SOUND_TYPE_LABELS[a.sound_type] || { icon: '❓', label: a.sound_type };
      const status = STATUS_LABELS[a.status] || { label: a.status, class: 'badge-muted' };
      return `
        <tr style="cursor:pointer" onclick="showDetail('${a.id}')">
          <td>${formatDateTime(a.timestamp)}</td>
          <td>${type.icon} ${type.label}</td>
          <td>${escapeHTML(a.device?.area?.name || a.device?.area || '?')}</td>
          <td>${escapeHTML(a.device?.name || '?')}</td>
          <td>
            ${riskLabel(a)}
          </td>
          <td><span class="badge ${status.class}">${status.label}</span></td>
          <td>${escapeHTML(a.handled_by?.full_name || '—')}</td>
          <td onclick="event.stopPropagation()">
            ${a.audio_file_url ? `<audio controls style="height:32px; width:160px;" preload="none"><source src="${a.audio_file_url}"></audio>` : '<span style="color:#aaa;font-size:12px;">Không có</span>'}
          </td>
          <td><button class="btn btn-outline btn-sm btn-icon" title="Chi tiết">📄</button></td>
        </tr>
      `;
    }).join('');
  }



  function goPage(page) {
    currentOffset = (page - 1) * pageSize;
    if (currentOffset < 0) currentOffset = 0;
    loadHistory();
  }

  async function showDetail(id) {
    try {
      const alert = await api('GET', `/api/alerts/${id}`);
      const type = SOUND_TYPE_LABELS[alert.sound_type] || { icon: '❓', label: alert.sound_type };
      const status = STATUS_LABELS[alert.status] || { label: alert.status, class: 'badge-muted' };

      let logsHtml = '';
      if (alert.logs && alert.logs.length > 0) {
        logsHtml = `
          <h4 style="margin:16px 0 8px;">📋 Nhật ký xử lý</h4>
          <div class="timeline">
            ${alert.logs.map(l => `
              <div class="timeline-item">
                <div class="timeline-action">${l.action}</div>
                <div class="timeline-actor">👤 ${l.actor?.full_name || '?'}</div>
                <div class="timeline-time">${formatDateTime(l.timestamp)}</div>
              </div>
            `).join('')}
          </div>
        `;
      }

      document.getElementById('modal-body').innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
          <div><strong>Loại âm thanh:</strong> ${type.icon} ${type.label}</div>
          <div><strong>Trạng thái:</strong> <span class="badge ${status.class}">${status.label}</span></div>
          <div><strong>Khu vực:</strong> ${escapeHTML(alert.device?.area?.name || alert.device?.area || '?')}</div>
          <div><strong>Thiết bị:</strong> ${escapeHTML(alert.device?.name || '?')}</div>
          <div><strong>Nguy cơ:</strong> ${riskLabel(alert)}</div>
          <div><strong>Thời gian:</strong> ${formatDateTime(alert.timestamp)}</div>
          <div><strong>Người xử lý:</strong> ${escapeHTML(alert.handled_by?.full_name || '—')}</div>
          <div><strong>Xử lý lúc:</strong> ${alert.resolved_at ? formatDateTime(alert.resolved_at) : '—'}</div>
        </div>
        ${alert.notes ? `<div style="margin-bottom:12px;"><strong>Ghi chú:</strong> <br> ${
          alert.notes.includes('[Giây') 
            ? `<div style="background: rgba(239, 68, 68, 0.05); color: var(--danger); padding: 8px 12px; border-radius: 6px; margin-top: 6px; border-left: 3px solid var(--danger); font-size: 13px;"><i class="bi bi-robot text-primary"></i> ${escapeHTML(alert.notes.replace(/<i[^>]*><\/i>/g, '').replace(/🗣|🔇/g, '').replace(/AI:/g, '').trim())}</div>`
            : `<span style="font-size:13px; color:var(--text-secondary);"><i class="bi bi-pencil-square"></i> ${escapeHTML(alert.notes.replace(/<i[^>]*><\/i>/g, '').trim())}</span>`
        }</div>` : ''}
        ${alert.audio_file_url ? `<div style="margin-bottom:12px;"><strong>Audio:</strong><br><audio controls style="margin-top:4px;"><source src="${alert.audio_file_url}"></audio></div>` : ''}
        <div><strong>Bằng chứng:</strong> ${alert.is_evidence ? '✅ Đã đánh dấu' : '❌ Không'}</div>
        ${renderAnalysisReport(alert.dialog_data)}
        ${logsHtml}
      `;

      document.getElementById('detail-modal').classList.add('active');
    } catch (err) {
      showToast('Lỗi', err.message, 'danger');
    }
  }

  function closeModal() {
    document.getElementById('detail-modal').classList.remove('active');
  }

  // Close modal on overlay click
  document.getElementById('detail-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) closeModal();
  });

  function exportCSV() {
    if (currentData.length === 0) {
      showToast('Thông báo', 'Không có dữ liệu để xuất', 'info');
      return;
    }

    const headers = ['Thời gian', 'Loại', 'Khu vực', 'Thiết bị', 'Nguy cơ', 'Trạng thái', 'Người xử lý', 'Ghi chú'];
    const rows = currentData.map(a => [
      formatDateTime(a.timestamp),
      SOUND_TYPE_LABELS[a.sound_type]?.label || a.sound_type,
      a.device?.area?.name || a.device?.area || '',
      a.device?.name || '',
      riskLabel(a),
      STATUS_LABELS[a.status]?.label || a.status,
      a.handled_by?.full_name || '',
      (a.notes || '').replace(/,/g, ';'),
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `canh-bao-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();

    showToast('Thành công', 'Đã tải xuống file CSV', 'success');
  }
})();

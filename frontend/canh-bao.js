// canh-bao.js — Live Alerts page logic
(function() {
  const user = initPage('alerts');
  if (!user) return;

  window.loadAlerts = loadAlerts;
  window.clearFilters = clearFilters;
  window.uploadAudio = uploadAudio;

  let allAlerts = [];
  let currentPage = 1;
  const itemsPerPage = 10;

  loadAreaFilter();
  loadAlerts();

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

  async function uploadAudio(event) {
    const file = event.target.files[0];
    if (!file) return;

    const overlay = document.getElementById('ai-loading-overlay');
    overlay.style.display = 'flex';

    const formData = new FormData();
    formData.append('audio', file);

    try {
      const res = await fetch(`${API_BASE}/api/alerts/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` },
        body: formData
      });

      overlay.style.display = 'none';

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.error || `HTTP ${res.status}`);
      }
      
      const data = await res.json();
      const count = data.total_alerts ?? data.totalAlerts ?? 0;
      document.getElementById('dialog-modal-body').innerHTML = renderAnalysisReport(data.result || data);
      document.getElementById('dialog-modal').style.display = 'flex';

      if (count > 0) {
        showToast('🚨 Phân tích hoàn tất', `Tìm thấy ${count} cảnh báo trong file âm thanh!`, 'danger');
        // Reload danh sách để hiện các cảnh báo mới
        await loadAlerts();
      } else {
        const analysis=(data.result || data).analysis;
        showToast('Phân tích hoàn tất', analysis?.summary || 'Xem nội dung lời nói và kết quả phân tích.', 'info');
      }

      event.target.value = '';
    } catch (err) {
      overlay.style.display = 'none';
      showToast('❌ Lỗi phân tích', err.message, 'danger');
      event.target.value = '';
    }
  }

  // WebSocket: new alerts
  onWsEvent('new-alert', (alert) => {
    prependAlertCard(alert);
  });

  onWsEvent('alert-updated', (alert) => {
    const card = document.getElementById(`alert-${alert.id}`);
    if (card) {
      card.outerHTML = renderAlertCard(alert);
    }
  });

  async function loadAlerts() {
    const type = document.getElementById('filter-type').value;
    const status = document.getElementById('filter-status').value;
    const area = document.getElementById('filter-area').value;

    let url = '/api/alerts?limit=1000';
    if (type) url += `&soundType=${type}`;
    if (status) url += `&status=${status}`;
    if (area) url += `&area=${encodeURIComponent(area)}`;

    try {
      const result = await api('GET', url);
      allAlerts = result.data || [];
      currentPage = 1;
      renderAlerts();
    } catch (err) {
      showToast('Lỗi', 'Không thể tải cảnh báo: ' + err.message, 'danger');
    }
  }

  function renderAlerts() {
    const list = document.getElementById('alerts-list');
    const empty = document.getElementById('alerts-empty');

    if (allAlerts.length === 0) {
      list.innerHTML = '';
      empty.style.display = 'block';
      document.getElementById('pagination-alerts').innerHTML = '';
      return;
    }

    empty.style.display = 'none';
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pagedAlerts = allAlerts.slice(start, end);

    list.innerHTML = pagedAlerts.map(a => renderAlertCard(a)).join('');

    renderPagination(allAlerts.length, itemsPerPage, currentPage, 'pagination-alerts', (page) => {
      currentPage = page;
      renderAlerts();
    });
  }

  function clearFilters() {
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-area').value = '';
    loadAlerts();
  }

  function renderAlertCard(a) {
    const type = SOUND_TYPE_LABELS[a.sound_type] || { icon: '❓', label: a.sound_type, color: 'info' };
    const audioUrlWithCacheBust = a.audio_file_url
      ? `${a.audio_file_url}${a.audio_file_url.includes('?') ? '&' : '?'}v=${encodeURIComponent(a.timestamp || Date.now())}`
      : '';
    const audioHtml = audioUrlWithCacheBust
      ? `<audio controls preload="none" style="height:32px;"><source src="${audioUrlWithCacheBust}">Trình duyệt không hỗ trợ</audio>`
      : '';

    function formatNotesHtml(notes, soundType) {
      if (!notes) return '';
      // Clean up old emojis and legacy HTML tags from DB
      let cleanNotes = notes.replace(/<i[^>]*><\/i>/g, '').replace(/🗣|🔇/g, '').replace(/AI:/g, '').trim();
      cleanNotes = cleanNotes.replace(/\"Không có lời thoại\"/g, 'Không có lời thoại').replace(/\'Không có lời thoại\'/g, 'Không có lời thoại');
      
      // Escape HTML for XSS protection
      let text = escapeHTML(cleanNotes);
      
      let icon = '';
      if (soundType === 'dap_pha') icon = '<i class="bi bi-hammer text-danger"></i>';
      else if (soundType === 'threat') icon = '<i class="bi bi-exclamation-triangle-fill text-warning"></i>';
      else if (soundType === 'scream') icon = '<i class="bi bi-volume-up-fill text-danger"></i>';
      else if (soundType === 'help') icon = '<i class="bi bi-person-arms-up text-danger"></i>';
      else if (soundType === 'argument') icon = '<i class="bi bi-chat-right-text-fill text-info"></i>';
      
      return `${icon} ${text}`;
    }
      const statusObj = STATUS_LABELS[a.status] || { class: 'badge-warning', label: a.status || 'Chờ xử lý' };
      return `
      <div class="alert-card ${a.risk_level === 'high' ? 'severity-high' : 'severity-medium'}" id="alert-${a.id}">

        <div class="alert-card-header">
          <span class="alert-card-type">
            ${type.icon} ${type.label}
            <strong>Nguy cơ: ${riskLabel(a)}</strong>
          </span>
          <span class="badge ${statusObj.class}">${statusObj.label}</span>
        </div>
        <div class="alert-card-meta">
          <span><i class="bi bi-geo-alt-fill"></i> ${escapeHTML(a.device?.area?.name || a.device?.area || '?')} — ${escapeHTML(a.device?.name || '')}</span>
          <span><i class="bi bi-clock-fill"></i> ${formatDateTime(a.timestamp)}</span>
          ${a.handled_by ? `<span><i class="bi bi-person-check-fill"></i> ${escapeHTML(a.handled_by.full_name)}</span>` : ''}
        </div>
        <div class="alert-card-body" style="margin-top:10px;">
          <div>${audioHtml}</div>
          ${a.dialog_data || (a.notes && a.notes.includes('[Giây')) ? `
              <div style="background: rgba(239, 68, 68, 0.05); color: var(--danger); padding: 12px; border-radius: 8px; margin: 12px 0 8px 0; font-weight: 600; font-size: 14px; border-left: 4px solid var(--danger);">
                <div style="margin-bottom: 8px;"><i class="bi bi-robot text-primary"></i> ${formatNotesHtml(a.notes, a.sound_type)}</div>
                ${a.dialog_data ? `
                <button onclick="window.openDialogModal('${a.id}')" style="background: var(--danger); color: white; border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: bold; display: flex; align-items: center; gap: 6px;">
                  <i class="bi bi-chat-text"></i> Xem chi tiết AI phân tích
                </button>
                ` : ''}
              </div>
            ` : (a.notes ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px;"><i class="bi bi-pencil-square"></i> Ghi chú: ${escapeHTML(a.notes)}</div>` : '')}
        </div>
      </div>
    `;
  }

  function prependAlertCard(alert) {
    const list = document.getElementById('alerts-list');
    const empty = document.getElementById('alerts-empty');
    empty.style.display = 'none';

    const div = document.createElement('div');
    div.innerHTML = renderAlertCard(alert);
    const el = div.firstElementChild;
    el.classList.add('alert-new');
    list.prepend(el);
  }

  window.openDialogModal = async function(alertId) {
    const modalBody = document.getElementById('dialog-modal-body');
    const modal = document.getElementById('dialog-modal');

    modalBody.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-secondary)"><i class="bi bi-hourglass-split" style="font-size:32px"></i><p style="margin-top:12px">Đang tải dữ liệu...</p></div>';
    modal.style.display = 'flex';

    try {
      const alertData = await api('GET', `/api/alerts/${alertId}`);
      modalBody.innerHTML = renderAnalysisReport(alertData.dialog_data);
    } catch (err) {
      modalBody.innerHTML = `<div style="text-align:center;padding:30px;color:var(--danger)"><i class="bi bi-exclamation-triangle" style="font-size:32px"></i><p style="margin-top:12px">Lỗi tải dữ liệu: ${err.message}</p></div>`;
    }
  };
})();

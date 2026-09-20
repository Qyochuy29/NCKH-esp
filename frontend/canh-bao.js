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

      if (count > 0) {
        showToast('🚨 Phân tích hoàn tất', `Tìm thấy ${count} cảnh báo trong file âm thanh!`, 'danger');
        // Reload danh sách để hiện các cảnh báo mới
        await loadAlerts();
      } else {
        showToast('✅ Phân tích hoàn tất', 'Không phát hiện dấu hiệu bạo lực trong file âm thanh.', 'success');
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
      const confidence = Math.max(10, Math.min(95, Number(a.confidence_score) || 10));
      const confidenceLabel = getConfidenceLabel(confidence);
      const statusObj = STATUS_LABELS[a.status] || { class: 'badge-warning', label: a.status || 'Chờ xử lý' };
      return `
      <div class="alert-card ${getSeverityClass(a.confidence_score)}" id="alert-${a.id}">

        <div class="alert-card-header">
          <span class="alert-card-type">
            ${type.icon} ${type.label}
            <span class="confidence-bar"><span class="confidence-bar-fill" style="width:${confidence}%;background:${getConfidenceColor(confidence)}"></span></span>
            <strong>${confidence.toFixed(0)}%</strong>
            <small style="font-weight:600;color:${getConfidenceColor(confidence)}">${confidenceLabel}</small>
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
      const dialogDataObj = alertData.dialog_data;

      // dialog_data là object: { dialogue: [...], violence_probability, ... }
      // hoặc dialog_data chính là mảng (fallback)
      const dialogue = Array.isArray(dialogDataObj)
        ? dialogDataObj
        : (dialogDataObj?.dialogue ?? []);

      const prob = dialogDataObj?.violence_probability ?? null;
      const scream = dialogDataObj?.has_scream ?? false;
      const crying = dialogDataObj?.has_crying ?? false;
      const threats = dialogDataObj?.threats_count ?? 0;
      const vulgarity = dialogDataObj?.vulgarity_count ?? 0;
      const emergency = dialogDataObj?.emergency_count ?? 0;

      let statsHtml = '';
      if (prob !== null) {
        const probColor = prob >= 70 ? 'var(--danger)' : prob >= 40 ? '#f59e0b' : '#10b981';
        statsHtml = `<div style="display:flex;gap:16px;flex-wrap:wrap;padding:12px 16px;background:rgba(239,68,68,0.07);border-radius:8px;margin-bottom:16px;font-size:13px;font-weight:600;">
          <span><i class="bi bi-exclamation-triangle-fill" style="color:${probColor}"></i> Tỉ lệ bạo lực: <strong style="color:${probColor};font-size:16px">${prob.toFixed(0)}%</strong></span>
          ${scream ? '<span><i class="bi bi-volume-up-fill text-danger"></i> Có tiếng gào thét</span>' : ''}
          ${crying ? '<span><i class="bi bi-emoji-tear-fill text-warning"></i> Có tiếng khóc lóc</span>' : ''}
          ${dialogDataObj?.has_impact ? '<span><i class="bi bi-hammer text-danger"></i> Có tiếng đập phá</span>' : ''}
          ${emergency > 0 ? `<span><i class="bi bi-person-arms-up text-danger"></i> Kêu cứu / Van xin: ${emergency}</span>` : ''}
          ${threats > 0 ? `<span><i class="bi bi-shield-x-fill text-danger"></i> Lời đe dọa: ${threats}</span>` : ''}
          ${vulgarity > 0 ? `<span><i class="bi bi-chat-x-fill text-warning"></i> Chửi thề: ${vulgarity}</span>` : ''}
        </div>`;
      }

      const origUrl = dialogDataObj?.original_audio_url;
      const clipUrl = alertData.audio_file_url;

      let audioPlayersHtml = `
        <div style="background:var(--bg-secondary, #f8fafc);border:1px solid #e2e8f0;border-radius:10px;padding:12px 16px;margin-bottom:16px;">
          <div style="font-weight:700;font-size:13px;color:var(--text);margin-bottom:10px;"><i class="bi bi-file-earmark-play-fill text-danger"></i> Tệp âm thanh liên quan:</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(260px, 1fr));gap:12px;">
            ${clipUrl ? `
            <div style="background:#fff;border:1px solid #fee2e2;border-radius:8px;padding:8px 12px;box-shadow:0 1px 2px rgba(0,0,0,0.03);">
              <div style="font-weight:600;font-size:12px;color:var(--danger);margin-bottom:4px;"><i class="bi bi-scissors"></i> Đoạn cắt cảnh báo 10s:</div>
              <audio controls style="width:100%;height:32px;"><source src="${clipUrl}${clipUrl.includes('?') ? '&' : '?'}v=${Date.now()}">Trình duyệt không hỗ trợ</audio>
            </div>` : ''}
            ${origUrl ? `
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;box-shadow:0 1px 2px rgba(0,0,0,0.03);">
              <div style="font-weight:600;font-size:12px;color:#2563eb;margin-bottom:4px;"><i class="bi bi-soundwave"></i> Toàn bộ file âm thanh:</div>
              <audio controls style="width:100%;height:32px;"><source src="${origUrl}${origUrl.includes('?') ? '&' : '?'}v=${Date.now()}">Trình duyệt không hỗ trợ</audio>
            </div>` : ''}
          </div>
        </div>`;

      if (dialogue.length === 0) {
        modalBody.innerHTML = `
          ${statsHtml}
          <div style="background:rgba(239,68,68,0.04);border:1.5px dashed rgba(239,68,68,0.3);border-radius:10px;padding:24px;text-align:center;margin:12px 0;">
            <i class="bi bi-mic-mute-fill" style="font-size:36px;color:var(--text-secondary);"></i>
            <div style="font-weight:700;font-size:15px;color:var(--text);margin-top:8px;">Không có lời thoại</div>
            <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">
              Hệ thống nhận diện sự kiện âm thanh (tiếng đập phá hoặc tiếng khóc), không phát hiện lời nói.
            </div>
          </div>
          ${audioPlayersHtml}
        `;
        return;
      }

      const html = dialogue.map(d => {
        const isAI = (d.speaker || '').toLowerCase() === 'ai';
        const bg = isAI ? 'rgba(239,68,68,0.07)' : 'rgba(0,0,0,0.03)';
        const borderColor = isAI ? 'var(--danger)' : '#d1d5db';
        const ts = escapeHTML(d.timestamp_s ?? d.time ?? d.timestamp ?? '?');
        return `<div style="background:${bg};border-left:3px solid ${borderColor};padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:10px;font-size:14px;">
          <span style="font-size:11px;color:var(--text-secondary);font-weight:600;">[Giây ${ts}]</span>
          <strong style="color:${isAI ? 'var(--danger)' : 'var(--text)'}"> ${escapeHTML(d.speaker ?? 'Unknown')}:</strong>
          <span style="color:var(--text)"> ${escapeHTML(d.text ?? '')}</span>
        </div>`;
      }).join('');

      modalBody.innerHTML = statsHtml + audioPlayersHtml + html;
    } catch (err) {
      modalBody.innerHTML = `<div style="text-align:center;padding:30px;color:var(--danger)"><i class="bi bi-exclamation-triangle" style="font-size:32px"></i><p style="margin-top:12px">Lỗi tải dữ liệu: ${err.message}</p></div>`;
    }
  };
})();

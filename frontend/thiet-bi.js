// thiet-bi.js — Device management page
(function() {
  const user = initPage('devices');
  if (!user) return;

  window.showAddModal = showAddModal;
  window.editDevice = editDevice;
  window.closeDeviceModal = closeDeviceModal;
  window.saveDevice = saveDevice;

  loadDevices();

  let allDevices = [];
  let currentPage = 1;
  const itemsPerPage = 10;
  let isEditing = false;
  let editingDeviceId = null;

  async function loadAreas() {
    try {
      const areas = await api('GET', '/api/areas');
      const select = document.getElementById('device-area');
      const currentVal = select.value;
      // Keep placeholder, remove rest
      while (select.options.length > 1) select.remove(1);
      areas.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = a.name;
        select.appendChild(opt);
      });
      if (currentVal) select.value = currentVal;
      return areas;
    } catch (err) {
      showToast('Lỗi', 'Không thể tải danh sách khu vực', 'danger');
      return [];
    }
  }

  async function loadDevices() {
    try {
      allDevices = await api('GET', '/api/devices');
      renderDevices();
    } catch (err) {
      showToast('Lỗi', err.message, 'danger');
    }
  }

  function renderDevices() {
    const tbody = document.getElementById('devices-tbody');
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const pagedDevices = allDevices.slice(start, end);

    tbody.innerHTML = pagedDevices.map(d => {
      const areaName = d.area?.name || d.area || '—';
      const statusBadge = d.status === 'online' ? 'badge-online' :
                         d.status === 'error' ? 'badge-error' : 'badge-offline';
      const statusLabel = d.status === 'online' ? 'Hoạt động' :
                         d.status === 'error' ? 'Lỗi' : 'Ngoại tuyến';
      const batteryColor = d.battery_level > 50 ? 'var(--success)' :
                          d.battery_level > 20 ? 'var(--warning)' : 'var(--danger)';
      return `
        <tr>
          <td><strong>${escapeHTML(d.name)}</strong></td>
          <td>${escapeHTML(areaName)}</td>
          <td><span class="badge ${statusBadge}">${statusLabel}</span></td>
          <td>
            <span style="color:${batteryColor};font-weight:600;">${d.battery_level}%</span>
            <span class="confidence-bar" style="width:50px;"><span class="confidence-bar-fill" style="width:${d.battery_level}%;background:${batteryColor}"></span></span>
          </td>
          <td>${formatRelative(d.last_seen)}</td>
          <td>
            <button class="btn btn-outline btn-sm" onclick='editDevice(${JSON.stringify(d).replace(/'/g, "\\'")})'><i class="bi bi-pencil"></i> Sửa</button>
            <button class="btn btn-outline btn-sm" style="color: var(--danger); border-color: var(--danger);" onclick='deleteDevice("${d.id}")'><i class="bi bi-trash"></i> Xóa</button>
          </td>
        </tr>
      `;
    }).join('');

    renderPagination(allDevices.length, itemsPerPage, currentPage, 'pagination-devices', (page) => {
      currentPage = page;
      renderDevices();
    });
  }

  async function showAddModal() {
    isEditing = false;
    editingDeviceId = null;
    document.getElementById('modal-title').textContent = 'Thêm thiết bị mới';
    document.getElementById('device-id').value = '';
    document.getElementById('device-name').value = '';
    await loadAreas();
    document.getElementById('device-area').value = '';
    document.getElementById('device-modal').classList.add('active');
  }

  async function editDevice(d) {
    isEditing = true;
    editingDeviceId = d.id;
    document.getElementById('modal-title').textContent = 'Sửa thiết bị';
    document.getElementById('device-id').value = d.id;
    document.getElementById('device-name').value = d.name;
    await loadAreas();
    // Set area value: d.area_id or d.area.id
    const areaId = d.area_id || d.area?.id || '';
    document.getElementById('device-area').value = areaId;
    document.getElementById('device-modal').classList.add('active');
  }

  function closeDeviceModal() {
    document.getElementById('device-modal').classList.remove('active');
  }

  async function saveDevice() {
    const id = document.getElementById('device-id').value.trim();
    const area_id = document.getElementById('device-area').value;
    const data = {
      name: document.getElementById('device-name').value.trim(),
      area_id,
      floor: 1, // Mặc định là 1 do đã bỏ UI
      position_x: 0,
      position_y: 0,
    };

    if (!data.name || !data.area_id) {
      showToast('Lỗi', 'Vui lòng nhập tên và chọn khu vực', 'danger');
      return;
    }

    try {
      if (isEditing && editingDeviceId) {
        if (id && id !== editingDeviceId) {
           data.new_id = id;
           data.NewId = id;
           data.newId = id;
        }
        await api('PUT', `/api/devices/${editingDeviceId}`, data);
        showToast('Thành công', 'Đã cập nhật thiết bị', 'success');
      } else {
        if (id) {
          data.id = id;
          data.Id = id;
        }
        await api('POST', '/api/devices', data);
        showToast('Thành công', 'Đã thêm thiết bị mới', 'success');
      }
      closeDeviceModal();
      loadDevices();
    } catch (err) {
      showToast('Lỗi', err.message, 'danger');
    }
  }

  // Close modal on overlay click
  document.getElementById('device-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) closeDeviceModal();
  });

  async function deleteDevice(id) {
    if (!confirm('Bạn có chắc chắn muốn xóa thiết bị này? Toàn bộ dữ liệu cảnh báo liên quan cũng sẽ bị xóa.')) return;
    try {
      await api('DELETE', `/api/devices/${id}`);
      showToast('Thành công', 'Đã xóa thiết bị', 'success');
      loadDevices();
    } catch (err) {
      showToast('Lỗi', err.message, 'danger');
    }
  }
  window.deleteDevice = deleteDevice;
})();

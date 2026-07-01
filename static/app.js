function fmt(n) { return Number(n || 0).toLocaleString('zh-CN') }
function imgTag(url) { return `<img class="thumb" src="${url}" alt="产品图片" onerror="this.style.display='none'" onclick="openImagePreview('${url}')">` }
function openImagePreview(url) { const modal = document.getElementById('imageModal'); const img = document.getElementById('imageModalImg'); if (!modal || !img) return; img.src = url; modal.classList.add('open') }
function closeImagePreview() { const modal = document.getElementById('imageModal'); const img = document.getElementById('imageModalImg'); if (!modal || !img) return; modal.classList.remove('open'); img.src = '' }
function syncDateInputs() { const preset = document.getElementById('datePreset').value; const disabled = preset !== 'custom'; document.getElementById('startDate').disabled = disabled; document.getElementById('endDate').disabled = disabled }
function initTabs() { document.querySelectorAll('.tab-btn').forEach(btn => { btn.addEventListener('click', () => { const target = btn.dataset.tabTarget; const group = btn.parentElement; group.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn)); const container = group.parentElement; container.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === target)); }); }); }
async function reloadData() {
  const button = document.querySelector('button[onclick="reloadData()"]');
  const previousText = button ? button.textContent : '';
  try {
    if (button) {
      button.disabled = true;
      button.textContent = '刷新中...';
    }
    const response = await fetch('/api/reload');
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `刷新失败：HTTP ${response.status}`);
    }
    alert(`刷新完成：${payload.rows}行，图片${payload.images}张`);
    await loadDashboard();
  } catch (error) {
    alert(`刷新失败：${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = previousText || '刷新数据';
    }
  }
}
function renderDailySalesChart(rows) {
  const el = document.getElementById('dailySalesChart');
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = '<p class="meta">暂无日销售数据</p>';
    return;
  }

  const width = 1200;
  const height = 380;
  const pad = { top: 24, right: 72, bottom: 56, left: 68 };
  const qtyMax = Math.max(...rows.map(r => r.销量), 1);
  const amtMax = Math.max(...rows.map(r => r.销售额), 1);
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const xStep = rows.length === 1 ? 0 : innerW / (rows.length - 1);
  const yQty = v => pad.top + innerH - (v / qtyMax) * innerH;
  const yAmt = v => pad.top + innerH - (v / amtMax) * innerH;
  const x = i => pad.left + i * xStep;
  const gridVals = [0.25, 0.5, 0.75, 1];
  const tickStep = Math.max(1, Math.ceil(rows.length / 8));
  const tooltipId = 'dailySalesChartTooltip';

  const qtyPts = rows.map((r, i) => `${x(i)},${yQty(r.销量)}`).join(' ');
  const amtPts = rows.map((r, i) => `${x(i)},${yAmt(r.销售额)}`).join(' ');

  el.innerHTML = `
    <div class="chart-legend"><span><i class="legend-dot qty"></i>销量</span><span><i class="legend-dot amt"></i>销售额</span></div>
    <div id="${tooltipId}" class="chart-tooltip" hidden></div>
    <svg viewBox="0 0 ${width} ${height}" class="trend-svg" role="img" aria-label="日销售趋势">
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="#fff"></rect>
      ${gridVals.map(v => {
        const y = pad.top + innerH - innerH * v;
        return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="#e5e7eb" stroke-dasharray="4 6"/>`;
      }).join('')}
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#94a3b8"/>
      <line x1="${width - pad.right}" y1="${pad.top}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#94a3b8"/>
      <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#94a3b8"/>
      <polyline fill="none" stroke="#0f766e" stroke-width="3" points="${qtyPts}" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <polyline fill="none" stroke="#ea580c" stroke-width="3" points="${amtPts}" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${rows.map((r, i) => `<circle cx="${x(i)}" cy="${yQty(r.销量)}" r="4" fill="#0f766e"/><circle cx="${x(i)}" cy="${yAmt(r.销售额)}" r="4" fill="#ea580c"/>`).join('')}
      ${rows.map((r, i) => i % tickStep === 0 ? `<text x="${x(i)}" y="${height - 18}" text-anchor="middle" class="axis-label">${r.日期}</text>` : '').join('')}
      ${rows.map((r, i) => {
        const xPos = i === rows.length - 1 ? x(i) - xStep / 2 : x(i) - xStep / 2;
        const rectW = rows.length === 1 ? innerW : xStep;
        return `<rect class="hover-zone" x="${xPos}" y="${pad.top}" width="${rectW}" height="${innerH}" fill="transparent" data-index="${i}" data-date="${r.日期}" data-qty="${r.销量}" data-amt="${r.销售额}"/>`;
      }).join('')}
      ${gridVals.map((v, idx) => {
        const y = pad.top + innerH - innerH * gridVals[idx];
        return `<text x="${pad.left - 10}" y="${y + 4}" text-anchor="end" class="axis-label">${fmt(Math.round(qtyMax * v))}</text>`;
      }).join('')}
      ${gridVals.map((v, idx) => {
        const y = pad.top + innerH - innerH * gridVals[idx];
        return `<text x="${width - pad.right + 10}" y="${y + 4}" text-anchor="start" class="axis-label">${fmt(Math.round(amtMax * v))}</text>`;
      }).join('')}
    </svg>`;

  const tooltip = el.querySelector(`#${tooltipId}`);
  const zones = el.querySelectorAll('.hover-zone');
  zones.forEach(zone => {
    zone.addEventListener('mouseenter', () => {
      tooltip.hidden = false;
      tooltip.innerHTML = `<b>${zone.dataset.date}</b><div>销量：${fmt(zone.dataset.qty)}</div><div>销售额：¥${fmt(zone.dataset.amt)}</div>`;
    });
    zone.addEventListener('mousemove', event => {
      const rect = el.getBoundingClientRect();
      const offsetX = event.clientX - rect.left;
      const offsetY = event.clientY - rect.top;
      tooltip.style.left = `${Math.min(rect.width - 180, Math.max(12, offsetX + 16))}px`;
      tooltip.style.top = `${Math.max(12, offsetY - 12)}px`;
    });
    zone.addEventListener('mouseleave', () => {
      tooltip.hidden = true;
    });
  });
}
async function loadDashboard() {
  const datePreset = document.getElementById('datePreset').value;
  const startDate = document.getElementById('startDate').value;
  const endDate = document.getElementById('endDate').value;
  const region = document.getElementById('region').value;
  const category = document.getElementById('category').value;
  const yearPrefix = document.getElementById('yearPrefix').value;
  const seasonCode = document.getElementById('seasonCode').value;
  const store = document.getElementById('store').value;
  const topn = document.getElementById('topn').value;
  const url = `/api/dashboard?region=${encodeURIComponent(region)}&category=${encodeURIComponent(category)}&year_prefix=${encodeURIComponent(yearPrefix)}&season_code=${encodeURIComponent(seasonCode)}&store=${encodeURIComponent(store)}&date_preset=${encodeURIComponent(datePreset)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&top_n=${topn}`;
  const data = await (await fetch(url)).json();
  applyFilterState(data.filters, data.meta);
  renderKpis(data.summary); renderDailySalesChart(data.daily_sales); renderProducts('globalTop', data.global_top); renderBars('regionBars', data.by_region, '区域名称'); renderBars('categoryBars', data.by_category, '品类'); renderBars('storeBars', data.by_store, '商店名称'); renderRegionTop(data.region_top); renderProducts('colorTop', data.color_top); renderProducts('slowMoving', data.slow_moving); renderMatrix(data.matrix);
  if (!data.image_index_ready) setTimeout(loadDashboard, 3000);
}
function applyFilterState(filters, meta) { if (!filters) return; document.getElementById('datePreset').value = filters.date_preset || 'week'; document.getElementById('startDate').value = filters.start_date || ''; document.getElementById('endDate').value = filters.end_date || ''; document.getElementById('region').value = filters.region || '全国'; document.getElementById('category').value = filters.category || ''; document.getElementById('yearPrefix').value = filters.year_prefix || meta?.default_year_prefix || ''; document.getElementById('seasonCode').value = filters.season_code || meta?.default_season_code || ''; document.getElementById('store').value = filters.store || ''; if (meta) { document.getElementById('startDate').min = meta.date_min || ''; document.getElementById('startDate').max = meta.date_max || ''; document.getElementById('endDate').min = meta.date_min || ''; document.getElementById('endDate').max = meta.date_max || ''; } syncDateInputs() }
function renderKpis(s) { document.getElementById('kpis').innerHTML = Object.entries(s).map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${fmt(v)}</b></div>`).join('') }
function renderProducts(id, rows) { document.getElementById(id).innerHTML = rows.map(r => `<div class="product">${imgTag(r.image_url)}<div><div class="rank">#${r.排名}</div><div class="code">${r.商品代码}${r.颜色代码 ? '_' + r.颜色代码 : ''}</div><div class="meta">${r.商品名称 || ''} · ${r.颜色名称 || r.品类 || ''}</div><div class="meta">选定价 ¥${fmt(r.选定价)} · <span class="qty">销量 ${fmt(r.销量)}</span>${r.进货数量 !== undefined ? ` · 进货 ${fmt(r.进货数量)}` : ''}</div></div></div>`).join('') || '<p class="meta">暂无数据</p>' }
function renderBars(id, rows, key) { const max = Math.max(...rows.map(r => r.销量), 1); document.getElementById(id).innerHTML = rows.map(r => `<div class="bar-row"><div class="bar-label"><b>${r[key]}</b><span>${fmt(r.销量)}</span></div><div class="bar"><div style="width:${Math.max(2, r.销量 / max * 100)}%"></div></div></div>`).join('') }
function renderRegionTop(obj) { const order = ['全国', '北区', '中区', '南区']; document.getElementById('regionTop').innerHTML = order.filter(region => obj[region]).map(region => `<div class="mini"><h3>${region}</h3>${obj[region].slice(0, 20).map(r => `<div class="mini-row"><div class="mini-img">${imgTag(r.image_url || '')}</div><b>${r.排名}</b><span>${r.商品代码}<br><small>${r.商品名称 || ''}</small></span><b>${fmt(r.销量)}</b></div>`).join('')}</div>`).join('') }
function renderMatrix(rows) { const headers = ['图片', '商品代码', '商品名称', '品类', '全国排名', '全国销量', '北区排名', '北区销量', '中区排名', '中区销量', '南区排名', '南区销量']; document.getElementById('matrixTable').innerHTML = '<thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>' + rows.map(r => '<tr><td>' + imgTag(r.image_url || '') + '</td>' + headers.slice(1).map(h => `<td>${fmtText(r[h])}</td>`).join('') + '</tr>').join('') + '</tbody>' }
function fmtText(v) { return typeof v === 'number' ? fmt(v) : (v ?? '') }
document.getElementById('datePreset').addEventListener('change', syncDateInputs)
initTabs()
syncDateInputs()
loadDashboard();

function fmt(n) { return Number(n || 0).toLocaleString('zh-CN') }
function toNumber(value) { const n = Number(value); return Number.isFinite(n) ? n : 0 }
function formatCurrencySmart(value) {
  const amount = toNumber(value)
  const absAmount = Math.abs(amount)
  if (absAmount >= 100000000) return `¥${(amount / 100000000).toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}亿`
  if (absAmount >= 10000) return `¥${(amount / 10000).toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}万`
  return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
function formatCountSmart(value, unit) { return `${fmt(value)} ${unit}` }
function formatRateSmart(value) { return `${(toNumber(value) * 100).toFixed(2)}%` }
function formatDeltaSmart(value) {
  if (!Number.isFinite(value)) return ''
  const sign = value > 0 ? '↑' : value < 0 ? '↓' : ''
  const magnitude = `${Math.abs(value).toFixed(1)}%`
  return sign ? `${sign}${magnitude}` : magnitude
}
function getExecutiveBriefSeed() { return '' }
function getExecutiveDiscountRate() { return null }
function parseAverageDiscountFromBrief(seed) { return null }
function previousDateText(dateText) {
  if (!dateText) return ''
  const value = new Date(`${dateText}T00:00:00`)
  if (Number.isNaN(value.getTime())) return ''
  value.setDate(value.getDate() - 1)
  return value.toISOString().slice(0, 10)
}
function averageDiscountRateFromRows(rows) {
  const items = Array.isArray(rows) ? rows : []
  let salesAmount = 0
  let standardAmount = 0
  items.forEach(row => {
    const qty = toNumber(row.销量 ?? row.sales_qty)
    const amount = toNumber(row.销售额 ?? row.sales_amount)
    const standardPrice = toNumber(row.选定价 ?? row.standard_price)
    salesAmount += amount
    standardAmount += qty * standardPrice
  })
  return standardAmount > 0 ? salesAmount / standardAmount : 0
}
function buildProductTrendMap(rows) {
  const map = new Map()
  ;(rows || []).forEach(row => {
    const code = row.商品代码 || row.product_code
    if (code) map.set(code, row)
  })
  return map
}
function trendLabel(currentAmount, previousAmount) {
  if (!Number.isFinite(currentAmount) || !Number.isFinite(previousAmount) || previousAmount === 0) return ''
  const change = ((currentAmount - previousAmount) / previousAmount) * 100
  return formatDeltaSmart(change)
}
function safeDate(value) {
  if (!value) return ''
  if (value instanceof Date) return value.toISOString().slice(0, 10)
  return String(value).slice(0, 10)
}
function imgTag(url) { return `<img class="thumb" src="${url}" alt="产品图片" onerror="this.style.display='none'" onclick="openImagePreview('${url}')">` }
function openImagePreview(url) { const modal = document.getElementById('imageModal'); const img = document.getElementById('imageModalImg'); if (!modal || !img) return; img.src = url; modal.classList.add('open') }
function closeImagePreview() { const modal = document.getElementById('imageModal'); const img = document.getElementById('imageModalImg'); if (!modal || !img) return; modal.classList.remove('open'); img.src = '' }
function syncDateInputs() { const presetEl = document.getElementById('datePreset'); const startEl = document.getElementById('startDate'); const endEl = document.getElementById('endDate'); if (!presetEl || !startEl || !endEl) return; const disabled = presetEl.value !== 'custom'; startEl.disabled = disabled; endEl.disabled = disabled }
function selectedValues(id) { const el = document.getElementById(id); return el ? Array.from(el.selectedOptions).map(option => option.value).filter(Boolean) : [] }
function setSelectedValues(id, values) { const select = document.getElementById(id); if (!select) return; const selected = new Set(values || []); Array.from(select.options).forEach(option => { option.selected = selected.has(option.value) }) }
function initTabs() { document.querySelectorAll('.tab-btn').forEach(btn => { btn.addEventListener('click', () => { const target = btn.dataset.tabTarget; const group = btn.parentElement; group.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn)); const container = group.parentElement; container.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === target)); }); }); }
function renderHomeKpis(summary, previousSummary) {
  const container = document.getElementById('homeKpiGrid')
  if (!container) return
  const discountFromBrief = getExecutiveDiscountRate() ?? parseAverageDiscountFromBrief(getExecutiveBriefSeed())
  const metrics = [
    { label: '销售金额', icon: 'bi-currency-yen', value: formatCurrencySmart(summary.总销售额), delta: previousSummary ? trendLabel(toNumber(summary.总销售额), toNumber(previousSummary.总销售额)) : '' },
    { label: '销售数量', icon: 'bi-bag-check', value: formatCountSmart(summary.总销量, '件'), delta: previousSummary ? trendLabel(toNumber(summary.总销量), toNumber(previousSummary.总销量)) : '' },
    { label: '平均折扣', icon: 'bi-percent', value: formatRateSmart(discountFromBrief ?? summary.average_discount_rate ?? 0), delta: '' },
    { label: '活跃门店', icon: 'bi-shop', value: formatCountSmart(summary.商店数, '家'), delta: '' },
  ]
  container.innerHTML = metrics.map(metric => `
    <article class="home-kpi-card">
      <div class="card-body">
        <div class="d-flex align-items-start justify-content-between gap-3">
          <div class="home-kpi-label">${metric.label}</div>
          <div class="home-kpi-icon"><i class="bi ${metric.icon}"></i></div>
        </div>
        <div class="home-kpi-value mt-3">${metric.value}</div>
        ${metric.delta ? `<div class="home-kpi-delta mt-2 ${metric.delta.startsWith('↓') ? 'text-danger' : 'text-success'}">较前日 ${metric.delta}</div>` : '<div class="home-kpi-delta mt-2 text-muted">&nbsp;</div>'}
      </div>
    </article>
  `).join('')
}
function renderHomeAiBrief(summary, previousSummary, currentRows, previousRows, regionRows) {
  const container = document.getElementById('homeAiBrief')
  if (!container) return
  const previousAmount = previousSummary ? toNumber(previousSummary.总销售额) : 0
  const currentAmount = toNumber(summary.总销售额)
  const amountDelta = previousAmount ? ((currentAmount - previousAmount) / previousAmount) * 100 : null
  const previousMap = buildProductTrendMap(previousRows)
  const topProduct = currentRows && currentRows.length ? currentRows[0] : null
  const topProductCode = topProduct ? (topProduct.商品代码 || topProduct.product_code || '') : ''
  const topProductName = topProduct ? (topProduct.商品名称 || topProduct.product_name || '') : ''
  const topProductAmount = topProduct ? formatCurrencySmart(toNumber(topProduct.销售额 ?? topProduct.sales_amount)) : '暂无'
  const regions = Array.isArray(regionRows) ? regionRows.slice(0, 4) : []
  const bestRegion = regions.length ? regions[0] : null
  const weakestRegion = regions.length ? regions[regions.length - 1] : null
  const bestRegionName = bestRegion ? (bestRegion.区域名称 || bestRegion.region_name || '全国') : '全国'
  const worstRegionName = weakestRegion ? (weakestRegion.区域名称 || weakestRegion.region_name || '末位区域') : '末位区域'
  const trendText = topProductCode && previousMap.has(topProductCode)
    ? trendLabel(toNumber(topProduct.销售额 ?? topProduct.sales_amount), toNumber(previousMap.get(topProductCode).销售额 ?? previousMap.get(topProductCode).sales_amount))
    : ''
  const summaryLine = `昨日销售${formatCurrencySmart(currentAmount)}${amountDelta === null ? '' : `，较前日${formatDeltaSmart(amountDelta)}`}。`
  const actionLine = topProductCode
    ? `建议优先补货 ${topProductName}（${topProductCode}），并关注 ${bestRegionName} 的持续表现。`
    : '建议优先关注高动销商品补货，并继续跟踪重点区域表现。'
  const bullets = [
    `销售件数 ${formatCountSmart(toNumber(summary.总销量), '件')}，活跃门店 ${formatCountSmart(summary.商店数, '家')}。`,
    topProductCode ? `最佳商品为 ${topProductName}（${topProductCode}），销售额 ${topProductAmount}${trendText ? `，较前日${trendText}` : ''}。` : '暂无足够数据识别最佳商品。',
    `建议关注 ${worstRegionName} 的库存和折扣。`,
  ].map(text => `<li>${text}</li>`).join('')
  container.classList.remove('home-ai-skeleton')
  container.innerHTML = `<div class="home-ai-summary">${summaryLine}</div><div class="home-ai-summary">${actionLine}</div><ul class="home-ai-bullets">${bullets}</ul>`
}
function renderHomeRegionBrief(regionRows, previousRegionRows) {
  const container = document.getElementById('homeRegionBrief')
  if (!container) return
  const current = Array.isArray(regionRows) ? regionRows : []
  if (!current.length) {
    container.innerHTML = '<div class="home-ai-empty">暂无区域数据</div>'
    return
  }
  const previous = Array.isArray(previousRegionRows) ? previousRegionRows : []
  container.classList.remove('home-ai-skeleton')
  const best = current[0] || null
  const growth = current.slice().sort((a, b) => {
    const currentDelta = toNumber(a.销售额 ?? a.sales_amount) - toNumber((previous.find(item => (item.区域名称 || item.region_name || '') === (a.区域名称 || a.region_name || '')) || {}).销售额 ?? (previous.find(item => (item.区域名称 || item.region_name || '') === (a.区域名称 || a.region_name || '')) || {}).sales_amount)
    const otherDelta = toNumber(b.销售额 ?? b.sales_amount) - toNumber((previous.find(item => (item.区域名称 || item.region_name || '') === (b.区域名称 || b.region_name || '')) || {}).销售额 ?? (previous.find(item => (item.区域名称 || item.region_name || '') === (b.区域名称 || b.region_name || '')) || {}).sales_amount)
    return otherDelta - currentDelta
  })[0] || null
  const decline = current.slice().sort((a, b) => {
    const currentDelta = toNumber(a.销售额 ?? a.sales_amount) - toNumber((previous.find(item => (item.区域名称 || item.region_name || '') === (a.区域名称 || a.region_name || '')) || {}).销售额 ?? (previous.find(item => (item.区域名称 || item.region_name || '') === (a.区域名称 || a.region_name || '')) || {}).sales_amount)
    const otherDelta = toNumber(b.销售额 ?? b.sales_amount) - toNumber((previous.find(item => (item.区域名称 || item.region_name || '') === (b.区域名称 || b.region_name || '')) || {}).销售额 ?? (previous.find(item => (item.区域名称 || item.region_name || '') === (b.区域名称 || b.region_name || '')) || {}).sales_amount)
    return currentDelta - otherDelta
  })[0] || null
  const attention = current[current.length - 1] || null
  const cards = [
    { title: '最佳区域', row: best },
    { title: '增长最快', row: growth },
    { title: '下滑最大', row: decline },
    { title: '需要关注', row: attention },
  ]
  container.innerHTML = cards.map(card => {
    const row = card.row || {}
    const name = row.区域名称 || row.region_name || '区域'
    const sales = toNumber(row.销售额 ?? row.sales_amount)
    const qty = toNumber(row.销量 ?? row.sales_qty)
    const prev = previous.find(item => (item.区域名称 || item.region_name || '') === name)
    const delta = prev ? trendLabel(sales, toNumber(prev.销售额 ?? prev.sales_amount)) : ''
    const trendClass = delta.startsWith('↓') ? 'down' : 'up'
    const trendIcon = delta.startsWith('↓') ? 'bi-arrow-down-short' : 'bi-arrow-up-short'
    return `
      <article class="home-region-card">
        <div class="home-region-label">${card.title}</div>
        <div class="home-region-name">${name}</div>
        <div class="home-region-amount">${formatCurrencySmart(sales)}</div>
        <div class="home-region-qty">${formatCountSmart(qty, '件')}</div>
        <div class="home-region-trend ${trendClass}">${delta ? `<i class="bi ${trendIcon}"></i>${delta}` : '暂无趋势'}</div>
      </article>
    `
  }).join('')
}
function renderHomeTop5(rows, previousRows) {
  const container = document.getElementById('homeTop5Grid')
  if (!container) return
  const previousMap = buildProductTrendMap(previousRows)
  const items = (rows || []).slice(0, 5)
  if (!items.length) {
    container.innerHTML = '<div class="home-top5-skeleton">暂无 Top 5 数据</div>'
    return
  }
  container.innerHTML = items.map(row => {
    const code = row.商品代码 || row.product_code || ''
    const name = row.商品名称 || row.product_name || ''
    const imageUrl = row.image_url || ''
    const amount = toNumber(row.销售额 ?? row.sales_amount)
    const qty = toNumber(row.销量 ?? row.sales_qty)
    const storeCoverage = toNumber(row.store_coverage ?? row.store_count)
    const amountText = formatCurrencySmart(amount)
    const previousRow = previousMap.get(code)
    const deltaText = previousRow ? trendLabel(amount, toNumber(previousRow.销售额 ?? previousRow.sales_amount)) : ''
    const deltaClass = deltaText.startsWith('↓') ? 'down' : 'up'
    const deltaIcon = deltaText.startsWith('↓') ? 'bi-arrow-down-short' : 'bi-arrow-up-short'
    const imageMarkup = imageUrl
      ? `<img src="${imageUrl}" alt="${name}" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.classList.remove('d-none');">`
      : ''
    return `
      <article class="home-top5-card">
        <div class="home-top5-media">
          ${imageMarkup}
          <div class="home-top5-fallback${imageUrl ? ' d-none' : ''}">
            <i class="bi bi-image"></i>
            <div>${code || '暂无图片'}</div>
          </div>
        </div>
        <div class="home-top5-body">
          <div class="home-top5-name">${name || '未命名商品'}</div>
          <div class="home-top5-code">${code}</div>
          <div class="home-top5-amount">${amountText}</div>
          <div class="home-top5-meta">销售数量 ${fmt(qty)} · 覆盖门店 ${fmt(storeCoverage)} 家</div>
          <div class="home-top5-trend ${deltaClass}">${deltaText ? `<i class="bi ${deltaIcon}"></i>${deltaText}` : '暂无趋势'}</div>
          <a class="home-top5-link" href="/products/${code}">查看详情 <i class="bi bi-arrow-right"></i></a>
        </div>
      </article>
    `
  }).join('')
}
async function loadExecutiveDashboard(dateMax, weeklyData) {
  if (!dateMax) return
  const currentDate = safeDate(dateMax)
  const previousDate = previousDateText(currentDate)
  const currentParams = new URLSearchParams({ date_preset: 'custom', start_date: currentDate, end_date: currentDate, top_n: '5' })
  const previousParams = new URLSearchParams({ date_preset: 'custom', start_date: previousDate, end_date: previousDate, top_n: '5' })
  const [currentResponse, previousResponse] = await Promise.all([
    fetch(`/api/dashboard?${currentParams.toString()}`).then(response => response.json()),
    previousDate ? fetch(`/api/dashboard?${previousParams.toString()}`).then(response => response.json()) : Promise.resolve(null),
  ])
  const currentSummary = currentResponse.summary || {}
  const previousSummary = previousResponse ? (previousResponse.summary || {}) : null
  renderHomeKpis(currentSummary, previousSummary)
  renderHomeAiBrief(currentSummary, previousSummary, currentResponse.global_top || [], previousResponse ? (previousResponse.global_top || []) : [], currentResponse.by_region || [])
  renderHomeRegionBrief(currentResponse.by_region || [], previousResponse ? (previousResponse.by_region || []) : [])
  renderHomeTop5(currentResponse.global_top || [], previousResponse ? (previousResponse.global_top || []) : [])
}
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
  const datePresetEl = document.getElementById('datePreset');
  const startDateEl = document.getElementById('startDate');
  const endDateEl = document.getElementById('endDate');
  const topnEl = document.getElementById('topn');
  const datePreset = datePresetEl ? datePresetEl.value : 'week';
  const startDate = startDateEl ? startDateEl.value : '';
  const endDate = endDateEl ? endDateEl.value : '';
  const region = selectedValues('region');
  const category = selectedValues('category');
  const yearPrefix = selectedValues('yearPrefix');
  const seasonCode = selectedValues('seasonCode');
  const wave = selectedValues('wave');
  const store = selectedValues('store');
  const topn = topnEl ? topnEl.value : '20';
  const params = new URLSearchParams();
  region.forEach(value => params.append('region', value));
  category.forEach(value => params.append('category', value));
  yearPrefix.forEach(value => params.append('year_prefix', value));
  seasonCode.forEach(value => params.append('season_code', value));
  wave.forEach(value => params.append('wave', value));
  store.forEach(value => params.append('store', value));
  params.set('date_preset', datePreset);
  params.set('start_date', startDate);
  params.set('end_date', endDate);
  params.set('top_n', topn);
  const url = `/api/dashboard?${params.toString()}`;
  try {
    const response = await fetch(url);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`)
    }

    const hasClassicDashboard = Boolean(document.getElementById('kpis'));
    if (hasClassicDashboard) {
      try {
        applyFilterState(data.filters, data.meta);
        renderKpis(data.summary); renderDailySalesChart(data.daily_sales); renderProducts('globalTop', data.global_top); renderBars('regionBars', data.by_region, '区域名称'); renderBars('categoryBars', data.by_category, '品类'); renderBars('storeBars', data.by_store, '商店名称'); renderRegionTop(data.region_top); renderProducts('colorTop', data.color_top); renderProducts('slowMoving', data.slow_moving); renderMatrix(data.matrix);
      } catch (error) {
        console.error('Classic dashboard render failed', error, data)
      }
    }

    if (document.getElementById('homeKpiGrid')) {
      try {
        await loadExecutiveDashboard(data.meta?.date_max || data.filters?.end_date || '', data)
      } catch (error) {
        console.error('Executive dashboard render failed', error, data)
        const aiBrief = document.getElementById('homeAiBrief')
        const top5 = document.getElementById('homeTop5Grid')
        const regions = document.getElementById('homeRegionBrief')
        const kpis = document.getElementById('homeKpiGrid')
        if (aiBrief) aiBrief.innerHTML = `<div class="home-ai-empty">加载失败：${error.message}</div>`
        if (top5) top5.innerHTML = `<div class="home-top5-skeleton">加载失败：${error.message}</div>`
        if (regions) regions.innerHTML = `<div class="home-ai-empty">加载失败：${error.message}</div>`
        if (kpis) kpis.innerHTML = `<div class="home-kpi-skeleton">加载失败：${error.message}</div>`
      }
    }

    if (hasClassicDashboard && !data.image_index_ready) setTimeout(loadDashboard, 3000);
  } catch (error) {
    console.error('Dashboard load failed', error)
    const aiBrief = document.getElementById('homeAiBrief')
    const top5 = document.getElementById('homeTop5Grid')
    const regions = document.getElementById('homeRegionBrief')
    const kpis = document.getElementById('homeKpiGrid')
    if (aiBrief) aiBrief.innerHTML = `<div class="home-ai-empty">加载失败：${error.message}</div>`
    if (top5) top5.innerHTML = `<div class="home-top5-skeleton">加载失败：${error.message}</div>`
    if (regions) regions.innerHTML = `<div class="home-ai-empty">加载失败：${error.message}</div>`
    if (kpis) kpis.innerHTML = `<div class="home-kpi-skeleton">加载失败：${error.message}</div>`
  }
}
function applyFilterState(filters, meta) { if (!filters) return; const datePresetEl = document.getElementById('datePreset'); const startDateEl = document.getElementById('startDate'); const endDateEl = document.getElementById('endDate'); if (datePresetEl) datePresetEl.value = filters.date_preset || 'week'; if (startDateEl) startDateEl.value = filters.start_date || ''; if (endDateEl) endDateEl.value = filters.end_date || ''; setSelectedValues('region', filters.region?.length ? filters.region : ['全国']); setSelectedValues('category', filters.category || []); setSelectedValues('yearPrefix', filters.year_prefix?.length ? filters.year_prefix : (meta?.default_year_prefix ? [meta.default_year_prefix] : [])); setSelectedValues('seasonCode', filters.season_code?.length ? filters.season_code : (meta?.default_season_code ? [meta.default_season_code] : [])); setSelectedValues('wave', filters.wave || []); setSelectedValues('store', filters.store || []); if (meta) { if (startDateEl) { startDateEl.min = meta.date_min || ''; startDateEl.max = meta.date_max || ''; } if (endDateEl) { endDateEl.min = meta.date_min || ''; endDateEl.max = meta.date_max || ''; } } syncDateInputs() }
function renderKpis(s) { document.getElementById('kpis').innerHTML = Object.entries(s).map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${fmt(v)}</b></div>`).join('') }
function renderProducts(id, rows) { document.getElementById(id).innerHTML = rows.map(r => `<div class="product">${imgTag(r.image_url)}<div><div class="rank">#${r.排名}</div><div class="code">${r.商品代码}${r.颜色代码 ? '_' + r.颜色代码 : ''}</div><div class="meta">${r.商品名称 || ''} · ${r.颜色名称 || r.品类 || ''}</div><div class="meta">选定价 ¥${fmt(r.选定价)} · <span class="qty">销量 ${fmt(r.销量)}</span>${r.进货数量 !== undefined ? ` · 进货 ${fmt(r.进货数量)}` : ''}</div></div></div>`).join('') || '<p class="meta">暂无数据</p>' }
function renderBars(id, rows, key) { const max = Math.max(...rows.map(r => r.销量), 1); document.getElementById(id).innerHTML = rows.map(r => `<div class="bar-row"><div class="bar-label"><b>${r[key]}</b><span>${fmt(r.销量)}</span></div><div class="bar"><div style="width:${Math.max(2, r.销量 / max * 100)}%"></div></div></div>`).join('') }
function renderRegionTop(obj) { const order = ['全国', '北区', '中区', '南区']; document.getElementById('regionTop').innerHTML = order.filter(region => obj[region]).map(region => `<div class="mini"><h3>${region}</h3>${obj[region].slice(0, 20).map(r => `<div class="mini-row with-large-image"><div class="mini-img mini-img-lg">${imgTag(r.image_url || '')}</div><b>${r.排名}</b><span>${r.商品代码}<br><small>${r.商品名称 || ''}</small></span><b>${fmt(r.销量)}</b></div>`).join('')}</div>`).join('') }
function renderMatrix(rows) { const headers = ['图片', '商品代码', '商品名称', '品类', '全国排名', '全国销量', '北区排名', '北区销量', '中区排名', '中区销量', '南区排名', '南区销量']; document.getElementById('matrixTable').innerHTML = '<thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>' + rows.map(r => '<tr><td class="matrix-image-cell">' + imgTag(r.image_url || '') + '</td>' + headers.slice(1).map(h => `<td>${fmtText(r[h])}</td>`).join('') + '</tr>').join('') + '</tbody>' }
function fmtText(v) { return typeof v === 'number' ? fmt(v) : (v ?? '') }
const datePresetControl = document.getElementById('datePreset')
if (datePresetControl) {
  datePresetControl.addEventListener('change', syncDateInputs)
}
initTabs()
syncDateInputs()
loadDashboard().catch(error => {
  console.error('Initial dashboard bootstrap failed', error)
})

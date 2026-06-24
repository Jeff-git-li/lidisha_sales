function fmt(n){return Number(n||0).toLocaleString('zh-CN')}
function imgTag(url){return `<img class="thumb" src="${url}" alt="产品图片" onerror="this.style.display='none'" onclick="openImagePreview('${url}')">`}
function openImagePreview(url){const modal=document.getElementById('imageModal'); const img=document.getElementById('imageModalImg'); if(!modal||!img)return; img.src=url; modal.classList.add('open')}
function closeImagePreview(){const modal=document.getElementById('imageModal'); const img=document.getElementById('imageModalImg'); if(!modal||!img)return; modal.classList.remove('open'); img.src=''}
function syncDateInputs(){const preset=document.getElementById('datePreset').value; const disabled=preset!=='custom'; document.getElementById('startDate').disabled=disabled; document.getElementById('endDate').disabled=disabled}
function initTabs(){document.querySelectorAll('.tab-btn').forEach(btn=>{btn.addEventListener('click',()=>{const target=btn.dataset.tabTarget; const group=btn.parentElement; group.querySelectorAll('.tab-btn').forEach(b=>b.classList.toggle('active', b===btn)); const container=group.parentElement; container.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('active', panel.id===target));});});}
async function reloadData(){const r=await fetch('/api/reload'); const j=await r.json(); alert(`刷新完成：${j.rows}行，图片${j.images}张`); loadDashboard();}
async function loadDashboard(){
  const datePreset=document.getElementById('datePreset').value;
  const startDate=document.getElementById('startDate').value;
  const endDate=document.getElementById('endDate').value;
  const region=document.getElementById('region').value;
  const category=document.getElementById('category').value;
  const yearPrefix=document.getElementById('yearPrefix').value;
  const seasonCode=document.getElementById('seasonCode').value;
  const store=document.getElementById('store').value;
  const topn=document.getElementById('topn').value;
  const url=`/api/dashboard?region=${encodeURIComponent(region)}&category=${encodeURIComponent(category)}&year_prefix=${encodeURIComponent(yearPrefix)}&season_code=${encodeURIComponent(seasonCode)}&store=${encodeURIComponent(store)}&date_preset=${encodeURIComponent(datePreset)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&top_n=${topn}`;
  const data=await (await fetch(url)).json();
  applyFilterState(data.filters, data.meta);
  renderKpis(data.summary); renderProducts('globalTop',data.global_top); renderBars('regionBars',data.by_region,'区域名称'); renderBars('categoryBars',data.by_category,'品类'); renderBars('storeBars',data.by_store,'商店名称'); renderRegionTop(data.region_top); renderProducts('colorTop',data.color_top); renderProducts('slowMoving',data.slow_moving); renderMatrix(data.matrix);
  if (!data.image_index_ready) setTimeout(loadDashboard, 3000);
}
function applyFilterState(filters, meta){if(!filters)return; document.getElementById('datePreset').value=filters.date_preset||'week'; document.getElementById('startDate').value=filters.start_date||''; document.getElementById('endDate').value=filters.end_date||''; document.getElementById('region').value=filters.region||'全国'; document.getElementById('category').value=filters.category||''; document.getElementById('yearPrefix').value=filters.year_prefix||meta?.default_year_prefix||''; document.getElementById('seasonCode').value=filters.season_code||meta?.default_season_code||''; document.getElementById('store').value=filters.store||''; if(meta){document.getElementById('startDate').min=meta.date_min||''; document.getElementById('startDate').max=meta.date_max||''; document.getElementById('endDate').min=meta.date_min||''; document.getElementById('endDate').max=meta.date_max||'';} syncDateInputs()}
function renderKpis(s){document.getElementById('kpis').innerHTML=Object.entries(s).map(([k,v])=>`<div class="kpi"><span>${k}</span><b>${fmt(v)}</b></div>`).join('')}
function renderProducts(id,rows){document.getElementById(id).innerHTML=rows.map(r=>`<div class="product">${imgTag(r.image_url)}<div><div class="rank">#${r.排名}</div><div class="code">${r.商品代码}${r.颜色代码?'_'+r.颜色代码:''}</div><div class="meta">${r.商品名称||''} · ${r.颜色名称||r.品类||''}</div><div class="meta">选定价 ¥${fmt(r.选定价)} · <span class="qty">销量 ${fmt(r.销量)}</span>${r.进货数量!==undefined?` · 进货 ${fmt(r.进货数量)}`:''}</div></div></div>`).join('') || '<p class="meta">暂无数据</p>'}
function renderBars(id,rows,key){const max=Math.max(...rows.map(r=>r.销量),1);document.getElementById(id).innerHTML=rows.map(r=>`<div class="bar-row"><div class="bar-label"><b>${r[key]}</b><span>${fmt(r.销量)}</span></div><div class="bar"><div style="width:${Math.max(2,r.销量/max*100)}%"></div></div></div>`).join('')}
function renderRegionTop(obj){const order=['全国','北区','中区','南区'];document.getElementById('regionTop').innerHTML=order.filter(region=>obj[region]).map(region=>`<div class="mini"><h3>${region}</h3>${obj[region].slice(0,20).map(r=>`<div class="mini-row"><div class="mini-img">${imgTag(r.image_url||'')}</div><b>${r.排名}</b><span>${r.商品代码}<br><small>${r.商品名称||''}</small></span><b>${fmt(r.销量)}</b></div>`).join('')}</div>`).join('')}
function renderMatrix(rows){const headers=['图片','商品代码','商品名称','品类','全国排名','全国销量','北区排名','北区销量','中区排名','中区销量','南区排名','南区销量'];document.getElementById('matrixTable').innerHTML='<thead><tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr><td>'+imgTag(r.image_url||'')+'</td>'+headers.slice(1).map(h=>`<td>${fmtText(r[h])}</td>`).join('')+'</tr>').join('')+'</tbody>'}
function fmtText(v){return typeof v==='number'?fmt(v):(v??'')}
document.getElementById('datePreset').addEventListener('change', syncDateInputs)
initTabs()
syncDateInputs()
loadDashboard();

function fmt(n){return Number(n||0).toLocaleString('zh-CN')}
function imgTag(url){return `<img src="${url}" onerror="this.style.display='none'">`}
async function reloadData(){const r=await fetch('/api/reload'); const j=await r.json(); alert(`刷新完成：${j.rows}行，图片${j.images}张`); loadDashboard();}
async function loadDashboard(){
  const region=document.getElementById('region').value;
  const category=document.getElementById('category').value;
  const topn=document.getElementById('topn').value;
  const url=`/api/dashboard?region=${encodeURIComponent(region)}&category=${encodeURIComponent(category)}&top_n=${topn}`;
  const data=await (await fetch(url)).json();
  renderKpis(data.summary); renderProducts('globalTop',data.global_top); renderBars('regionBars',data.by_region,'区域名称'); renderBars('categoryBars',data.by_category,'品类'); renderRegionTop(data.region_top); renderProducts('colorTop',data.color_top); renderMatrix(data.matrix); renderCategoryTop(data.category_top);
}
function renderKpis(s){document.getElementById('kpis').innerHTML=Object.entries(s).map(([k,v])=>`<div class="kpi"><span>${k}</span><b>${fmt(v)}</b></div>`).join('')}
function renderProducts(id,rows){document.getElementById(id).innerHTML=rows.map(r=>`<div class="product">${imgTag(r.image_url)}<div><div class="rank">#${r.排名}</div><div class="code">${r.商品代码}${r.颜色代码?'_'+r.颜色代码:''}</div><div class="meta">${r.商品名称||''} · ${r.颜色名称||r.品类||''}</div><div class="meta">选定价 ¥${fmt(r.选定价)} · <span class="qty">销量 ${fmt(r.销量)}</span></div></div></div>`).join('') || '<p class="meta">暂无数据</p>'}
function renderBars(id,rows,key){const max=Math.max(...rows.map(r=>r.销量),1);document.getElementById(id).innerHTML=rows.map(r=>`<div class="bar-row"><div class="bar-label"><b>${r[key]}</b><span>${fmt(r.销量)}</span></div><div class="bar"><div style="width:${Math.max(2,r.销量/max*100)}%"></div></div></div>`).join('')}
function renderRegionTop(obj){document.getElementById('regionTop').innerHTML=Object.entries(obj).map(([region,rows])=>`<div class="mini"><h3>${region}</h3>${rows.slice(0,20).map(r=>`<div class="mini-row"><b>${r.排名}</b><span>${r.商品代码}<br><small>${r.商品名称||''}</small></span><b>${fmt(r.销量)}</b></div>`).join('')}</div>`).join('')}
function renderMatrix(rows){const headers=['商品代码','商品名称','品类','全国排名','全国销量','北区排名','北区销量','中区排名','中区销量','南区排名','南区销量'];document.getElementById('matrixTable').innerHTML='<thead><tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+headers.map(h=>`<td>${fmtText(r[h])}</td>`).join('')+'</tr>').join('')+'</tbody>'}
function fmtText(v){return typeof v==='number'?fmt(v):(v??'')}
function renderCategoryTop(obj){document.getElementById('categoryTop').innerHTML=Object.entries(obj).map(([cat,rows])=>`<div class="cat-block"><h3>${cat}</h3><div class="table-wrap"><table><thead><tr><th>排名</th><th>商品代码</th><th>商品名称</th><th>选定价</th><th>销量</th><th>销售额</th></tr></thead><tbody>${rows.slice(0,20).map(r=>`<tr><td>${r.排名}</td><td>${r.商品代码}</td><td>${r.商品名称||''}</td><td>¥${fmt(r.选定价)}</td><td>${fmt(r.销量)}</td><td>${fmt(r.销售额)}</td></tr>`).join('')}</tbody></table></div></div>`).join('')}
loadDashboard();

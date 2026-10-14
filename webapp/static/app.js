const $ = s => document.querySelector(s);
let jobs = [], notes = [], mode = '全部', token = '', previousStatus = '', busy = false;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHTML;
function notice(message = '') { $('#notice').textContent = message; $('#notice').hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
function page(name) {
  document.querySelectorAll('.page').forEach(p => p.hidden = p.id !== `page-${name}`);
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.page === name));
  $('#breadcrumb').textContent = {jobs:'岗位清单',notes:'原始帖子',crawl:'新建搜索',xianyu:'闲鱼需求'}[name];
  location.hash = name;
}
document.querySelectorAll('.nav').forEach(n => n.onclick = () => page(n.dataset.page));
$('#new-search').onclick = () => page('crawl');
$('#see-results').onclick = () => page('notes');
window.addEventListener('hashchange', () => page(['jobs','notes','crawl','xianyu'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'jobs'));
function renderJobs() {
  const query = $('#job-query').value.toLowerCase().trim();
  const filtered = jobs.filter(j => (mode === '全部' || j.mode === mode) && JSON.stringify(j).toLowerCase().includes(query));
  $('#jobs-grid').innerHTML = filtered.length ? filtered.map(j => {
    const url = notes.find(n => n.id === j.note_id)?.url || j.url;
    return `<article class="job-card"><div class="card-top"><div class="company-icon">${e(j.company[0])}</div><div><div class="company">${e(j.company)}</div><div class="source">${e(j.source)}</div></div><span class="badge ${j.mode === '远程' ? '' : 'neutral'}">${e(j.mode === '远程' ? '支持远程' : '远程' + j.mode)}</span></div><h3>${e(j.role)}</h3><div class="pay">${e(j.pay)}</div><div class="period">${e(j.period)}</div><div class="tags">${j.tags.map(t => `<span class="tag">${e(t)}</span>`).join('')}</div><p class="summary">${e(j.summary)}</p><p class="note">${e(j.note)}</p><div class="card-footer"><span>${j.note_id ? '招聘线索 · 身份待核实' : '公开招聘资料 · 名额待确认'}</span><a href="${e(url)}" target="_blank" rel="noopener noreferrer">查看原始招聘 ↗</a></div></article>`;
  }).join('') : '<div class="empty">没有匹配的岗位，试试其他筛选条件。</div>';
}
$('#job-query').oninput = renderJobs;
document.querySelectorAll('#job-filters button').forEach(button => button.onclick = () => {
  mode = button.dataset.mode;
  document.querySelectorAll('#job-filters button').forEach(b => {b.classList.toggle('selected', b === button);b.setAttribute('aria-pressed', b === button);});
  renderJobs();
});
function filteredNotes() {
  const query = $('#note-query').value.toLowerCase().trim(), keyword = $('#keyword-filter').value;
  return notes.filter(n => (!keyword || n.keyword === keyword) && n.title.toLowerCase().includes(query));
}
function renderNotes() {
  const list = filteredNotes();
  $('#note-result-count').textContent = `${list.length} / ${notes.length} 篇`;
  $('#notes-empty').hidden = list.length > 0;
  $('#notes-body').innerHTML = list.map(n => `<tr><td>${e(n.title)}</td><td><span class="tag">${e(n.keyword)}</span></td><td>${e(n.published.slice(0,10))}</td><td><a href="${e(n.url)}" target="_blank" rel="noopener noreferrer">查看 ↗</a></td></tr>`).join('');
}
$('#note-query').oninput = renderNotes;
$('#keyword-filter').onchange = renderNotes;
$('#export').onclick = () => {
  const blob = new Blob([JSON.stringify(filteredNotes(), null, 2)], {type:'application/json;charset=utf-8'});
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = '小红书帖子筛选结果.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
async function refreshNotes() {
  notes = await api('/api/notes');
  $('#notes-count').textContent = notes.length;
  const selected = $('#keyword-filter').value;
  $('#keyword-filter').innerHTML = '<option value="">全部关键词</option>' + [...new Set(notes.map(n => n.keyword))].filter(Boolean).map(k => `<option value="${e(k)}">${e(k)}</option>`).join('');
  $('#keyword-filter').value = [...new Set(notes.map(n => n.keyword))].includes(selected) ? selected : '';
  renderNotes(); renderJobs();
}
async function refreshState() {
  const state = await api('/api/state');
  token = state.token;
  const active = ['running','stopping'].includes(state.status);
  $('#start').disabled = active || busy;
  $('#keywords').disabled = active;
  $('#stop').hidden = !active;
  $('#stop').disabled = state.status === 'stopping';
  $('#status-badge').textContent = {idle:'就绪',running:'运行中',stopping:'停止中',completed:'已完成',failed:'未完成',stopped:'已停止'}[state.status];
  $('#status-title').textContent = {idle:'等待你的下一次发现',running:'正在寻找新的线索',stopping:'正在结束本次搜索',completed:'新的线索已进入帖子库',failed:'本次搜索未能完成',stopped:'本次搜索已停止'}[state.status];
  $('#status-message').textContent = state.message;
  $('#status-visual').classList.toggle('running', state.status === 'running');
  $('#status-visual').textContent = state.status === 'completed' ? '✓' : '⌕';
  $('#events').innerHTML = state.events.map(ev => `<li><time>${e(ev.time)}</time>${e(ev.message)}</li>`).join('');
  $('#qr-box').hidden = !state.qr;
  if (state.qr && $('#qr-image').dataset.stamp !== String(state.qr)) {
    $('#qr-image').src = `/qr.png?v=${state.qr}`; $('#qr-image').dataset.stamp = state.qr;
  }
  if (previousStatus && previousStatus !== state.status && !active) await refreshNotes();
  previousStatus = state.status;
}
$('#crawl-form').onsubmit = async ev => {
  ev.preventDefault(); if (busy) return; busy = true; $('#start').disabled = true; notice();
  try {await api('/api/start', {keywords:$('#keywords').value}); await refreshState();}
  catch (error) {notice(error.message);}
  finally {busy = false; await refreshState().catch(() => notice('本地服务连接中断，请重新启动网页服务。'));}
};
$('#stop').onclick = async () => {
  $('#stop').disabled = true;
  try {await api('/api/stop', {}); await refreshState();} catch (error) {notice(error.message); $('#stop').disabled = false;}
};
document.querySelectorAll('[data-suggestion]').forEach(b => b.onclick = () => {
  if ($('#keywords').disabled) return;
  const values = [...new Set($('#keywords').value.split(/[,，\n]/).map(v => v.trim()).filter(Boolean).concat(b.dataset.suggestion))];
  if (values.length > 3) {notice('每次最多搜索 3 组关键词，请先删除一组。');return;}
  $('#keywords').value = values.join('，');notice();
});
async function poll() {
  try { await refreshState(); $('.local-badge').innerHTML = '<span class="dot"></span> 本地服务'; }
  catch { $('.local-badge').textContent = '服务连接中断'; $('#start').disabled = true; }
  setTimeout(poll, 2500);
}
async function init() {
  page(['jobs','notes','crawl','xianyu'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'jobs');
  try {
    jobs = await api('/api/jobs');
    $('#jobs-count').textContent = $('#nav-count').textContent = jobs.length;
    $('#remote-count').textContent = jobs.filter(j => j.mode === '远程').length;
    await refreshNotes(); await refreshState();
  } catch (error) {notice(`加载失败：${error.message}。请检查本地服务。`);}
  poll();
}
init();

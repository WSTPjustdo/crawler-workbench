(() => {
  let rows = [], state = {}, pageIndex = 0, busy = false, signature = '';
  const pageSize = 24;
  const labels = {idle:'就绪',running:'运行中',stopping:'停止中',completed:'已结束',failed:'未完成',needs_login:'需要登录',stopped:'已停止'};
  function filtered() {
    const category = $('#xy-category').value, query = $('#xy-query').value.trim().toLowerCase();
    const current = $('#xy-scope').value === 'current';
    return rows.filter(r => (!current || r.runs.includes(state.run_id)) &&
      (!category || (category === 'leads' ? ['历史已核对','疑似需求','待判断'].includes(r.category) : r.category === category)) &&
      (!query || [r.title,r.text,r.queries.join(' '),r.reason,r.requirement || ''].join(' ').toLowerCase().includes(query)));
  }
  function render() {
    const items = filtered(), pages = Math.max(1, Math.ceil(items.length / pageSize));
    pageIndex = Math.min(pageIndex, pages - 1);
    $('#xy-count').textContent = `${items.length} 条匹配 / 共 ${rows.length} 条`;
    $('#xy-results').innerHTML = items.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize).map(r => {
      const url = `https://www.goofish.com/item?id=${encodeURIComponent(r.id)}`;
      return `<article class="job-card xy-card"><div class="card-top"><span class="tag">闲鱼</span><span class="badge neutral">${e(r.category)}</span></div><h3>${e(r.title)}</h3><p class="summary">${e(r.requirement || r.text.slice(0,240))}</p>${r.budget ? `<div class="pay">${e(r.budget)}</div>` : ''}<p class="note">${e(r.reason)} ${e(r.review_note)}</p><div class="tags">${r.queries.map(k => `<span class="tag">${e(k)}</span>`).join('')}</div><details><summary>查看采集原文</summary><pre>${e(r.text)}</pre></details><div class="card-footer"><span>${e(r.reviewed_at ? '历史核对 ' + r.reviewed_at.slice(0,10) : (r.collected_at ? '采集 ' + r.collected_at.slice(0,16).replace('T',' ') : '历史采集 · 时间未记录'))}</span><a href="${url}" target="_blank" rel="noopener noreferrer">查看原帖 ↗</a></div></article>`;
    }).join('') || '<div class="empty">当前筛选没有结果。可切换到全部结果，或更换关键词搜索。</div>';
    $('#xy-page-info').textContent = `${pageIndex + 1} / ${pages} 页`;
    $('#xy-prev').disabled = pageIndex === 0;
    $('#xy-next').disabled = pageIndex >= pages - 1;
  }
  async function refreshRecords() { rows = await api('/api/xianyu/records'); render(); }
  async function refresh() {
    state = await api('/api/xianyu/state');
    const active = ['running','stopping'].includes(state.status);
    for (const id of ['xy-start','xy-open','xy-check','xy-keywords']) $('#' + id).disabled = active || busy;
    $('#xy-stop').hidden = !active;
    $('#xy-stop').disabled = state.status === 'stopping' || busy;
    $('#xy-status').textContent = labels[state.status] || state.status;
    $('#xy-login').textContent = {unknown:'登录待检查',ready:'页面显示已登录',required:'需要登录',closed:'窗口未打开',verification:'需要平台验证'}[state.login] || '登录待检查';
    $('#xy-message').textContent = state.message;
    $('#xy-progress').textContent = state.total ? `${state.completed} / ${state.total} 组关键词 · ${state.count} 条去重结果` : '浏览器与登录状态';
    $('#xy-progress-bar').max = state.total || 1;
    $('#xy-progress-bar').value = state.completed;
    $('#xy-events').innerHTML = state.events.map(ev => `<li><time>${e(ev.time)}</time>${e(ev.message)}</li>`).join('');
    const nextSignature = [state.run_id,state.status,state.completed,state.count].join(':');
    if (signature !== nextSignature) { signature = nextSignature; await refreshRecords(); }
  }
  async function action(name, data = {}) {
    if (busy) return;
    busy = true; notice();
    for (const id of ['xy-start','xy-open','xy-check']) $('#' + id).disabled = true;
    try {
      // Obtain a fresh token even if the local service was restarted.
      token = (await api('/api/state')).token;
      await api('/api/xianyu/' + name, data);
      if (name === 'search') { $('#xy-scope').value = 'current'; $('#xy-category').value = ''; pageIndex = 0; }
    } catch (error) { notice(error.message); }
    finally { busy = false; await refresh().catch(() => notice('本地服务连接中断，请重新启动。')); }
  }
  $('#xy-form').onsubmit = ev => { ev.preventDefault(); action('search', {keywords:$('#xy-keywords').value}); };
  $('#xy-open').onclick = () => action('open');
  $('#xy-check').onclick = () => action('check');
  $('#xy-stop').onclick = () => action('stop');
  $('#xy-refresh').onclick = () => refreshRecords().catch(error => notice(error.message));
  for (const id of ['xy-category','xy-scope','xy-query']) $('#' + id).addEventListener(id === 'xy-query' ? 'input' : 'change', () => {pageIndex = 0; render();});
  $('#xy-prev').onclick = () => {pageIndex--; render();};
  $('#xy-next').onclick = () => {pageIndex++; render();};
  $('#xy-export').onclick = () => {
    const payload = {exported_at:new Date().toISOString(), scope:'每个搜索词第一页；初筛结果不等于有效需求；历史核对可能已过时', records:filtered()};
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = '闲鱼筛选结果.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  async function poll() {
    try { await refresh(); }
    catch { $('#xy-message').textContent = '无法连接本地服务，请重新启动网页。'; $('#xy-start').disabled = true; }
    setTimeout(poll,2500);
  }
  poll();
})();

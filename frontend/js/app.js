(async () => {
  // ⚙ 现在是 <a href="/settings.html?from=home">，无需 JS 绑定
  document.getElementById('pick-folder').addEventListener('click', async () => {
    const btn = document.getElementById('pick-folder');
    btn.disabled = true;
    try {
      const r = await API.pickFolder();
      if (r.path) location.href = '/task.html?folder=' + encodeURIComponent(r.path);
    } catch (e) {
      alert('选择失败：' + e.message);
    } finally {
      btn.disabled = false;
    }
  });

  // 批量：累加选中的文件夹，到齐了点"开始批量"
  const batchFolders = new Set();

  function renderBatch() {
    const list = document.getElementById('batch-list');
    list.innerHTML = '';
    batchFolders.forEach(p => {
      const item = document.createElement('div');
      item.className = 'item';
      item.innerHTML = `<span>${escape(p)}</span>`;
      const rm = document.createElement('button');
      rm.textContent = '×';
      rm.title = '从批次中移除';
      rm.onclick = () => { batchFolders.delete(p); renderBatch(); };
      item.appendChild(rm);
      list.appendChild(item);
    });
    document.getElementById('batch-start').disabled = batchFolders.size === 0;
    document.getElementById('batch-clear').disabled = batchFolders.size === 0;
  }

  document.getElementById('batch-add').addEventListener('click', async () => {
    const btn = document.getElementById('batch-add');
    btn.disabled = true;
    try {
      const r = await API.pickFolder();
      if (r.path) {
        if (!batchFolders.has(r.path)) batchFolders.add(r.path);
        renderBatch();
      }
    } catch (e) {
      alert('选择失败：' + e.message);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById('batch-clear').addEventListener('click', () => {
    batchFolders.clear();
    renderBatch();
  });

  document.getElementById('batch-start').addEventListener('click', async () => {
    if (batchFolders.size === 0) return;
    const folders = Array.from(batchFolders);
    try {
      const r = await API.startBatchTranslate(folders);
      batchFolders.clear();
      renderBatch();
      location.href = '/batch.html?id=' + (r.first_task_id || '');
    } catch (e) {
      alert('启动失败：' + e.message);
    }
  });

  function escape(s) {
    return s.replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  let status;
  try {
    status = await API.status();
  } catch (e) {
    document.getElementById('loading-card')?.remove();
    document.getElementById('home-card').classList.remove('hidden');
    document.getElementById('engine-hint').textContent = '后端连接失败：' + e.message;
    return;
  }

  // 隐藏 loading，显示真实内容
  document.getElementById('loading-card')?.remove();

  // 历史 chip（容错：失败不影响主流程）
  try {
    const hist = await API.history();
    const chips = document.getElementById('recent-chips');
    (hist.recent || []).forEach(p => {
      const c = document.createElement('div');
      c.className = 'recent-chip';
      c.textContent = p;
      c.title = p + '（点击直接开始）';
      c.onclick = () => { location.href = '/task.html?folder=' + encodeURIComponent(p); };
      chips.appendChild(c);
    });
  } catch (_) { /* 静默 */ }

  const pickBtn = document.getElementById('pick-folder');
  const batchBtn = document.getElementById('batch-add');
  if (!status.engine_installed) {
    document.getElementById('engine-hint').textContent = '首次使用需要安装翻译引擎。';
    const installChip = document.createElement('a');
    installChip.className = 'primary';
    installChip.style.marginLeft = '8px';
    installChip.style.cursor = 'pointer';
    installChip.textContent = '去安装';
    installChip.href = '/install.html';
    pickBtn.parentNode.insertBefore(installChip, pickBtn.nextSibling);
    pickBtn.disabled = true;
    batchBtn.disabled = true;
  } else {
    document.getElementById('engine-hint').textContent = '';
  }

  if (!status.has_config) {
    // 首次使用：直接跳设置页
    location.href = '/settings.html?from=home';
  } else {
    document.getElementById('home-card').classList.remove('hidden');
    refreshQueue();
    setInterval(refreshQueue, 2000);
  }

  async function refreshQueue() {
    try {
      const q = await API.queue();
      const tasks = q.tasks || [];
      // 只看"未完结"的任务
      const unfinished = tasks.filter(t =>
        !['done', 'failed', 'cancelled'].includes(t.status));
      const wrap = document.getElementById('running-wrap');
      const list = document.getElementById('running-list');
      if (unfinished.length === 0) {
        if (wrap) wrap.style.display = 'none';
        return;
      }
      if (wrap) wrap.style.display = '';
      if (!list) return;

      // 按"正在跑 → 排队"排，再按入队先后
      const ordered = unfinished.sort((a, b) => {
        const w = s => ['starting','running'].includes(s) ? 0 : 1;
        return w(a.status) - w(b.status) || (a.batch_index - b.batch_index);
      });

      list.innerHTML = '';
      ordered.forEach(t => {
        const row = document.createElement('div');
        row.className = 'run-row';

        const pillCls = {
          running: 'status-running', starting: 'status-running', queued: 'status-queued'
        }[t.status] || 'status-queued';
        const pillText = { running: '进行中', starting: '启动', queued: '排队' }[t.status] || t.status;
        const pill = `<span class="status-pill ${pillCls}">${pillText}</span>`;

        let prog = '';
        if (t.total > 0) {
          prog = `${t.current}/${t.total}`;
        } else if (t.status === 'queued') {
          prog = '等待';
        }

        row.innerHTML = `
          <span class="run-folder" title="${escape(t.folder)}">${escape(t.folder)}</span>
          ${pill}
          <span class="run-progress">${prog}</span>
          <a href="/task.html?folder=${encodeURIComponent(t.folder)}&task=${t.task_id}">查看</a>
        `;

        if (['queued', 'starting', 'running'].includes(t.status)) {
          const cancel = document.createElement('button');
          cancel.textContent = '取消';
          cancel.title = '取消这个任务';
          cancel.onclick = async () => {
            if (!confirm(`取消任务：${t.folder}？`)) return;
            try { await API.cancelTranslate(t.task_id); } catch (_) {}
            refreshQueue();
          };
          row.appendChild(cancel);
        }

        list.appendChild(row);
      });
    } catch (e) { /* 静默 */ }
  }
})();
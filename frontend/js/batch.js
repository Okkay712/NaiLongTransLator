(function () {
  const list = document.getElementById('queue-list');
  const summary = document.getElementById('summary');

  // ⚙ 设置：带回来源参数，保存/返回后回到本批量页
  const settingsLink = document.getElementById('open-settings');
  if (settingsLink) {
    const id = new URLSearchParams(location.search).get('id');
    const q = new URLSearchParams();
    q.set('from', 'batch');
    if (id) q.set('id', id);
    settingsLink.href = '/settings.html?' + q.toString();
  }

  function escape(s) {
    return (s || '').replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function render() {
    API.queue().then(q => {
      const tasks = q.tasks || [];
      if (tasks.length === 0) {
        list.innerHTML = '<div class="muted">队列为空，回主页选文件夹吧。</div>';
        summary.textContent = '';
        return;
      }
      const done = tasks.filter(t => t.status === 'done').length;
      const failed = tasks.filter(t => t.status === 'failed').length;
      const cancelled = tasks.filter(t => t.status === 'cancelled').length;
      const running = tasks.filter(t => ['starting','running'].includes(t.status)).length;
      summary.textContent = `共 ${tasks.length} 个 · 进行中 ${running} · 完成 ${done} · 失败 ${failed} · 取消 ${cancelled}`;

      list.innerHTML = '';
      tasks.forEach(t => {
        const row = document.createElement('div');
        row.className = 'task-row';
        const pill = `<span class="status-pill status-${t.status}">${t.status}</span>`;
        let progbar = '';
        if (t.total > 0) {
          const pct = Math.min(100, Math.floor(t.current / t.total * 100));
          progbar = `<span class="muted" style="margin-left: 8px;">${t.current}/${t.total} (${pct}%)</span>`;
        }
        const link = `<a href="/task.html?folder=${encodeURIComponent(t.folder)}&task=${t.task_id}">日志</a>`;
        const cancelBtn = ['queued', 'starting', 'running'].includes(t.status)
          ? `<button data-id="${t.task_id}" data-action="cancel">取消</button>`
          : '';
        const openBtn = t.output_path
          ? `<button data-path="${escape(t.output_path)}" data-action="open">打开</button>`
          : '';

        row.innerHTML = `
          <div style="flex:1; min-width: 0;">
            <div class="label" title="${escape(t.folder)}">${escape(t.folder)}</div>
            ${pill}${progbar}
          </div>
          <div class="task-actions">
            ${link}${cancelBtn}${openBtn}
          </div>
        `;
        list.appendChild(row);
      });

      list.querySelectorAll('button[data-action="cancel"]').forEach(b => {
        b.addEventListener('click', async () => {
          await API.cancelTranslate(b.dataset.id);
          render();
        });
      });
      list.querySelectorAll('button[data-action="open"]').forEach(b => {
        b.addEventListener('click', async () => {
          await API.openPath(b.dataset.path);
        });
      });
    });
  }

  render();
  setInterval(render, 1500);
})();
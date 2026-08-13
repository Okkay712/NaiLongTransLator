(function () {
  const params = new URLSearchParams(location.search);
  const folder = params.get('folder') || '';
  const explicitTaskId = params.get('task') || null;

  const logEl = document.getElementById('log');
  const progText = document.getElementById('progress-text');
  const progFill = document.getElementById('progress-fill');
  const counterEl = document.getElementById('counter');
  const batchMeta = document.getElementById('batch-meta');
  const statusPill = document.getElementById('status-pill');
  const resultEl = document.getElementById('result');
  const startBtn = document.getElementById('start');
  const cancelBtn = document.getElementById('cancel');
  const titleEl = document.getElementById('title');
  const logSection = document.getElementById('log-section');

  // 预览图元素
  const origImg = document.getElementById('orig');
  const transImg = document.getElementById('trans');
  const origEmpty = document.getElementById('orig-empty');
  const transEmpty = document.getElementById('trans-empty');

  let currentTid = null;
  let pollTimer = null;
  // 多图循环：记录所有输入图和当前翻译到的索引
  let allInputFiles = [];
  let currentIndex = 0;  // 当前正在翻译第几张（0-based）

  titleEl.textContent = '翻译 - ' + (folder || '未选择');
  if (!folder) { location.href = '/'; return; }

  // ⚙ 设置：带回来源参数，保存/返回后能回到本任务页
  const settingsLink = document.getElementById('open-settings');
  if (settingsLink) {
    const q = new URLSearchParams();
    q.set('from', 'task');
    if (folder) q.set('folder', folder);
    if (explicitTaskId) q.set('task', explicitTaskId);
    settingsLink.href = '/settings.html?' + q.toString();
  }

  // 启动时折叠日志（"日志" 默认是关的；用户主动点开）
  if (logSection) logSection.open = false;

  function appendLog(text) {
    const d = document.createElement('div');
    d.textContent = text;
    logEl.appendChild(d);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function showImage(which, url) {
    const img = which === 'orig' ? origImg : transImg;
    const empty = which === 'orig' ? origEmpty : transEmpty;
    if (!img || !empty || !url) return;
    // 避免重复设置同一张图 src（img.src 是浏览器解析后的绝对 URL，与新 url 比较时直接用 includes 也够用）
    if (img.getAttribute('data-path') === url) return;
    img.setAttribute('data-path', url);
    img.src = url;
    img.style.display = 'block';
    empty.style.display = 'none';
  }

  async function loadInputPreview() {
    // 进入任务页时，加载所有输入图，第一张作为"原图"展示
    try {
      const r = await API.inputImages(folder);
      allInputFiles = (r && r.files) || [];
      currentIndex = 0;
      if (allInputFiles.length > 0) {
        showImage('orig', API.previewUrl(allInputFiles[0]));
      }
    } catch (e) {
      // 静默失败，不影响后续翻译流程
    }
  }
  loadInputPreview();

  function setStatus(status) {
    statusPill.className = 'pill ' + (
      status === 'done' ? 'done' :
      status === 'failed' ? 'failed' :
      status === 'cancelled' ? 'failed' :
      status === 'running' || status === 'starting' ? 'idle' :  // running 用 idle 蓝色样式
      'idle');
    statusPill.textContent = ({
      idle: '空闲', queued: '排队', starting: '启动', running: '进行中',
      done: '完成', failed: '失败', cancelled: '已取消', cancelling: '取消中'
    })[status] || status;
  }

  async function start() {
    startBtn.disabled = true;
    cancelBtn.disabled = false;
    resultEl.textContent = '';
    progText.textContent = '启动中...';
    progFill.style.width = '0%';
    counterEl.textContent = '0 / 0';
    logEl.innerHTML = '';
    // 新任务开始：清掉上一轮的译图
    if (transImg) {
      transImg.removeAttribute('data-path');
      transImg.src = '';
      transImg.style.display = 'none';
    }
    if (transEmpty) transEmpty.style.display = '';
    setStatus('queued');
    try {
      const r = await API.startTranslate({ folder });
      currentTid = r.first_task_id || r.task_id;
      appendLog('[前端] 已启动任务 ' + currentTid);
      runStream(currentTid);
      pollBatch();
    } catch (e) {
      resultEl.textContent = '启动失败：' + e.message;
      startBtn.disabled = false;
      cancelBtn.disabled = true;
      setStatus('failed');
    }
  }

  function runStream(tid) {
    const es = new EventSource('/api/stream/' + tid);
    es.addEventListener('log', e => {
      const data = JSON.parse(e.data);
      if (data.text) appendLog(data.text);
    });
    es.addEventListener('hello', e => {
      const data = JSON.parse(e.data);
      if (data.batch_total > 1) {
        batchMeta.textContent = `批量任务第 ${data.batch_index + 1} / ${data.batch_total} 个`;
      } else {
        batchMeta.textContent = '单文件夹翻译';
      }
    });
    es.addEventListener('status', e => {
      const data = JSON.parse(e.data);
      setStatus(data.status);
    });
    es.addEventListener('progress', e => {
      const data = JSON.parse(e.data);
      const cur = data.current || 0, total = data.total || 1;
      progText.textContent = `已翻译 ${cur} / ${total}`;
      counterEl.textContent = `${cur} / ${total}`;
      progFill.style.width = (cur / total * 100).toFixed(1) + '%';
      // 多图循环：进度推进时，左边提前显示下一张原图
      currentIndex = cur - 1;  // cur 是"已完成"数，下一张是 cur（0-based）
      if (currentIndex >= 0 && currentIndex < allInputFiles.length) {
        showImage('orig', API.previewUrl(allInputFiles[currentIndex]));
      }
    });
    es.addEventListener('image_saved', e => {
      const data = JSON.parse(e.data);
      // 译图：data.path 是引擎刚保存的文件（带后缀）
      if (data.path) showImage('trans', API.previewUrl(data.path));
      // 原图：service 端会按同名 stem 在输入目录找原图
      if (data.orig_path) showImage('orig', API.previewUrl(data.orig_path));
    });
    es.addEventListener('done', e => {
      const data = JSON.parse(e.data);
      es.close();
      cancelBtn.disabled = true;
      if (data.ok) {
        setStatus('done');
        progFill.style.width = '100%';
        progText.textContent = '翻译完成';
        counterEl.textContent = `已完成`;
        batchMeta.textContent = '全部完成';
        resultEl.innerHTML =
          `<button id="open-out" class="primary" style="margin-left:0;">打开输出目录</button>`;
        const openOut = document.getElementById('open-out');
        if (openOut && data.output_path) {
          openOut.addEventListener('click', () => API.openPath(data.output_path));
        }
        // 完成时自动展开日志，方便复盘
        if (logSection) logSection.open = true;
        // 弹窗通知：翻译完成 + 输出路径
        const outPath = data.output_path || '';
        setTimeout(() => {
          alert(outPath ? `已全部翻译完成，保存至：\n${outPath}` : '已全部翻译完成');
        }, 300);
      } else if (data.cancelled) {
        setStatus('cancelled');
        resultEl.textContent = '已取消';
        startBtn.disabled = false;
      } else {
        setStatus('failed');
        resultEl.textContent = '失败，退出码 ' + (data.rc ?? '?');
        startBtn.disabled = false;
        // 失败时强制展开日志，方便排查
        if (logSection) logSection.open = true;
      }
      pollBatch();
    });
    es.onerror = () => { try { es.close(); } catch (_) {} };
  }

  function pollBatch() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const q = await API.queue();
        const items = q.tasks || [];
        const unfinished = items.filter(t => !['done','failed','cancelled'].includes(t.status));
        if (unfinished.length > 0) {
          batchMeta.textContent =
            `队列中还剩 ${unfinished.length} 个 · 全部完成后这里会显示最终输出`;
        }
      } catch (_) { /* 静默 */ }
    }, 3000);
  }

  startBtn.addEventListener('click', start);
  cancelBtn.addEventListener('click', async () => {
    if (!currentTid) return;
    cancelBtn.disabled = true;
    try {
      await API.cancelTranslate(currentTid);
    } catch (e) {
      alert('取消失败：' + e.message);
    }
  });

  if (explicitTaskId) {
    startBtn.style.display = 'none';
    cancelBtn.disabled = false;
    runStream(explicitTaskId);
  }
})();
(function () {
  const logEl = document.getElementById('log');
  const backBtn = document.getElementById('back-home');
  function append(text) {
    const d = document.createElement('div');
    d.textContent = text;
    logEl.appendChild(d);
    logEl.scrollTop = logEl.scrollHeight;
  }
  append('[奶龙翻译器] 开始连接安装服务...');

  const es = new EventSource('/api/install/stream');
  es.addEventListener('log', e => {
    const data = JSON.parse(e.data);
    append(data.text || '');
  });
  es.addEventListener('done', e => {
    const data = JSON.parse(e.data);
    es.close();
    if (data.ok) {
      append('[奶龙翻译器] 安装完成 ✓');
      backBtn.disabled = false;
    } else {
      append('[奶龙翻译器] 安装失败：' + (data.error || ('退出码 ' + data.rc)));
    }
  });
  es.onerror = () => {
    append('[奶龙翻译器] 与服务的连接已断开，请重试。');
  };

  backBtn.addEventListener('click', () => { location.href = '/'; });
})();

// 简易 fetch 包装。所有 API 调用走这里，方便前端共用错误处理。
const API = (() => {
  async function get(path) {
    const r = await fetch(path, { cache: 'no-store' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(text || ('HTTP ' + r.status));
    }
    return r.json();
  }
  return {
    status: () => get('/api/status'),
    settings: () => get('/api/settings'),
    saveSettings: (payload) => post('/api/settings', payload),
    history: () => get('/api/history'),
    pickFolder: () => post('/api/pick-folder'),
    pickOutputDir: () => post('/api/pick-output-dir'),
    outputDefault: () => get('/api/output-default'),
    startTranslate: (payload) => post('/api/translate', payload),
    startBatchTranslate: (folders) => post('/api/translate', { folders }),
    cancelTranslate: (taskId) => post('/api/cancel/' + taskId),
    queue: () => get('/api/queue'),
    inputImages: (folder) => get('/api/input-images?folder=' + encodeURIComponent(folder)),
    // URL helper（不是 fetch），用于 img.src
    previewUrl: (path) => '/api/preview?path=' + encodeURIComponent(path),
    openPath: (path) => post('/api/open', { path }),
  };
})();

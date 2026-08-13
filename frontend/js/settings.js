// 设置页（settings.html）：读写配置，左上角返回，支持 ?from= 参数回到来源页。
//   ?from=home            → 回主页 /
//   ?from=task&folder=X&task=Y → 回 /task.html?folder=X&task=Y （正在进行的任务页）
//   ?from=batch&id=X      → 回 /batch.html?id=X
const Settings = (() => {
  // 解析来源参数，决定返回跳转地址
  function backUrl() {
    const p = new URLSearchParams(location.search);
    const from = p.get('from') || '';
    if (from === 'task') {
      const folder = p.get('folder') || '';
      const task = p.get('task') || '';
      let url = '/task.html';
      if (folder) url += '?folder=' + encodeURIComponent(folder);
      if (task) url += (url.includes('?') ? '&' : '?') + 'task=' + encodeURIComponent(task);
      return url;
    }
    if (from === 'batch') {
      const id = p.get('id') || '';
      return id ? '/batch.html?id=' + encodeURIComponent(id) : '/batch.html';
    }
    // 默认 home
    return '/';
  }

  async function open() {
    const cfg = await API.settings();
    const def = await API.outputDefault();
    document.getElementById('api_key').value = '';
    document.getElementById('api_key').placeholder = cfg.api_key
      ? '(已设置，留空保留原值)'
      : '例如 sk-...';
    document.getElementById('target_lang').value = cfg.target_lang;
    document.getElementById('font').value = cfg.font || '';
    document.getElementById('save_quality').value = cfg.save_quality || 95;
    document.getElementById('detector').value = cfg.detector || 'default';
    document.getElementById('ocr').value = cfg.ocr || '48px';
    document.getElementById('inpainter').value = cfg.inpainter || 'default';

    // 输出位置
    const mode = cfg.output_mode || 'custom';
    document.querySelectorAll('input[name="output_mode"]').forEach(r => {
      r.checked = (r.value === mode);
    });
    document.getElementById('output_dir').value = cfg.output_dir || '';
    document.getElementById('output_dir_default').textContent = def.path;

    updateOutputModeUI();
  }

  function updateOutputModeUI() {
    const mode = document.querySelector('input[name="output_mode"]:checked')?.value;
    const wrap = document.getElementById('output_dir_wrap');
    if (mode === 'custom') wrap.style.display = '';
    else wrap.style.display = 'none';
  }

  async function pickOutputDir() {
    try {
      const r = await API.pickOutputDir();
      if (r.path) document.getElementById('output_dir').value = r.path;
    } catch (e) {
      alert('选择失败：' + e.message);
    }
  }

  async function save() {
    const mode = document.querySelector('input[name="output_mode"]:checked')?.value
      || 'custom';
    const payload = {
      api_key: document.getElementById('api_key').value || '***',
      target_lang: document.getElementById('target_lang').value,
      font: document.getElementById('font').value,
      save_quality: parseInt(document.getElementById('save_quality').value, 10) || 95,
      detector: document.getElementById('detector').value,
      ocr: document.getElementById('ocr').value,
      inpainter: document.getElementById('inpainter').value,
      output_mode: mode,
      output_dir: document.getElementById('output_dir').value || '',
    };
    try {
      await API.saveSettings(payload);
      location.href = backUrl();
    } catch (e) {
      alert('保存失败：' + e.message);
    }
  }

  // 左上角返回按钮
  document.addEventListener('click', e => {
    if (e.target?.id === 'settings-back') {
      e.preventDefault();
      location.href = backUrl();
    }
  });

  // 选择"自定义输出"时展开路径选择行
  document.addEventListener('change', e => {
    if (e.target?.name === 'output_mode') Settings.updateOutputModeUI();
  });

  document.addEventListener('DOMContentLoaded', open);

  return { open, save, pickOutputDir, updateOutputModeUI, backUrl };
})();

/* 小水 · 出行决策助手（EdgeOne Makers 前端） */
(() => {
  const ENDPOINT = '/mall-agent';
  const LS_CID = 'xs_cid';
  const LS_SESSIONS = 'xs_sessions';
  const MAX_SESSIONS = 20;

  const $ = (id) => document.getElementById(id);
  const chatEl = $('chat');
  const welcomeEl = $('welcome');
  const inputEl = $('input');
  const sendBtn = $('sendBtn');
  const imgInput = $('imgInput');
  const attachPreview = $('attachPreview');
  const attachThumb = $('attachThumb');
  const mapPanel = $('mapPanel');
  const mapBody = $('mapBody');
  const historyList = $('historyList');

  let state = {
    cid: localStorage.getItem(LS_CID) || newId(),
    sessionId: newId(),
    messages: [],
    points: [],
    mapImage: '',
    pendingImage: '',
    busy: false,
  };
  localStorage.setItem(LS_CID, state.cid);

  function newId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'cid-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
  }

  /* ── Markdown 极简渲染 ───────────────── */
  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderText(text) {
    const lines = escapeHtml(text || '').split(/\r?\n/);
    let html = '';
    let inList = false;
    for (const raw of lines) {
      const line = raw.trim();
      if (/^[-*·]\s+/.test(line)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += '<li>' + inline(line.replace(/^[-*·]\s+/, '')) + '</li>';
        continue;
      }
      if (inList) { html += '</ul>'; inList = false; }
      if (!line) continue;
      html += '<p>' + inline(line) + '</p>';
    }
    if (inList) html += '</ul>';
    return html;
  }

  function inline(s) {
    return s
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>');
  }

  /* ── 消息渲染 ─────────────────────────── */
  function hideWelcome() {
    if (welcomeEl && welcomeEl.parentNode) welcomeEl.remove();
  }

  function appendMessage(role, content, image) {
    hideWelcome();
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + (role === 'user' ? 'user' : 'bot');

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '🙂' : '🧳';

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (image) {
      const img = document.createElement('img');
      img.src = image;
      img.alt = '上传的照片';
      bubble.appendChild(img);
    }
    const body = document.createElement('div');
    body.innerHTML = renderText(content);
    bubble.appendChild(body);

    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    scrollBottom();
    return bubble;
  }

  function appendTyping() {
    hideWelcome();
    const wrap = document.createElement('div');
    wrap.className = 'msg bot';
    wrap.id = 'typingMsg';
    wrap.innerHTML = '<div class="avatar">🧳</div>'
      + '<div class="bubble typing"><span></span><span></span><span></span></div>';
    chatEl.appendChild(wrap);
    scrollBottom();
  }

  function removeTyping() {
    const el = $('typingMsg');
    if (el) el.remove();
  }

  function scrollBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  /* ── 地图面板 ─────────────────────────── */
  const CAT_COLOR = { shopping: '#FF6B6B', hotel: '#4D96FF', sightseeing: '#2BB673' };
  const CAT_LABEL = { shopping: '商场', hotel: '酒店', sightseeing: '景点' };

  function renderMap(points, mapImage) {
    state.points = points || [];
    state.mapImage = mapImage || '';
    if (!state.points.length) return;

    const cards = state.points.slice(0, 12).map((p) => {
      const color = CAT_COLOR[p.category] || '#999';
      const label = CAT_LABEL[p.category] || '';
      const name = escapeHtml(p.name || '');
      const nameEnc = encodeURIComponent(p.name || '');
      const addr = escapeHtml(p.address || '地址未知');
      const marker = `https://uri.amap.com/marker?position=${p.lng},${p.lat}&name=${nameEnc}`;
      const nav = `https://uri.amap.com/navigation?to=${p.lng},${p.lat}&toname=${nameEnc}&mode=transit`;
      return `<div class="poi-card">
        <div class="poi-pin" style="background:${color}">${label}</div>
        <div class="poi-info">
          <div class="poi-name">${name}</div>
          <div class="poi-addr">${addr}</div>
        </div>
        <div class="poi-actions">
          <a href="${marker}" target="_blank" rel="noopener">📍 地图</a>
          <a href="${nav}" target="_blank" rel="noopener">🧭 导航</a>
        </div>
      </div>`;
    }).join('');

    mapBody.innerHTML = (state.mapImage
      ? `<img class="map-img" src="${state.mapImage}" alt="位置地图" /><div class="map-tip">共 ${state.points.length} 个结果，地图展示前 ${Math.min(state.points.length, 10)} 个</div>`
      : `<div class="map-tip">共 ${state.points.length} 个结果</div>`) + cards;

    mapPanel.classList.remove('hidden');
  }

  /* ── 发送 ─────────────────────────────── */
  async function send() {
    if (state.busy) return;
    const text = inputEl.value.trim();
    const image = state.pendingImage;
    if (!text && !image) return;

    state.busy = true;
    sendBtn.disabled = true;

    const shownText = text || '这张照片里是哪个景点？帮我看看';
    appendMessage('user', text || '（上传了一张照片）', image);
    state.messages.push({ role: 'user', content: shownText });

    inputEl.value = '';
    autoGrow();
    clearImage();
    appendTyping();

    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Makers-Conversation-Id': state.cid,
        },
        body: JSON.stringify({
          message: shownText,
          history: state.messages.slice(-9),
          image: image || undefined,
        }),
      });

      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}${detail ? '：' + detail.slice(0, 120) : ''}`);
      }

      const data = await res.json();
      removeTyping();
      const reply = data.reply || '抱歉，这次没生成出回复～';
      appendMessage('assistant', reply);
      state.messages.push({ role: 'assistant', content: reply });

      if (data.points && data.points.length) renderMap(data.points, data.map_image || '');
      saveSession();
    } catch (err) {
      removeTyping();
      const msg = `😵‍💫 请求失败了：${err.message}\n\n稍后再试一次，或刷新页面重开对话～`;
      appendMessage('assistant', msg);
    } finally {
      state.busy = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  /* ── 会话本地保存 ─────────────────────── */
  function loadSessions() {
    try { return JSON.parse(localStorage.getItem(LS_SESSIONS) || '[]'); }
    catch { return []; }
  }

  function saveSession() {
    if (!state.messages.length) return;
    const list = loadSessions().filter((s) => s.id !== state.sessionId);
    const firstUser = state.messages.find((m) => m.role === 'user');
    list.unshift({
      id: state.sessionId,
      title: (firstUser ? firstUser.content : '新对话').slice(0, 24),
      messages: state.messages.slice(-30),
      points: state.points.slice(0, 12),
      time: Date.now(),
    });
    localStorage.setItem(LS_SESSIONS, JSON.stringify(list.slice(0, MAX_SESSIONS)));
    renderHistory();
  }

  function renderHistory() {
    const list = loadSessions();
    if (!list.length) {
      historyList.innerHTML = '<div class="history-empty">暂无历史对话</div>';
      return;
    }
    historyList.innerHTML = list.map((s) =>
      `<div class="history-item ${s.id === state.sessionId ? 'active' : ''}" data-id="${s.id}">
         <span class="dot">●</span><span>${escapeHtml(s.title)}</span>
       </div>`).join('');
    historyList.querySelectorAll('.history-item').forEach((el) => {
      el.addEventListener('click', () => openSession(el.dataset.id));
    });
  }

  function openSession(id) {
    const s = loadSessions().find((x) => x.id === id);
    if (!s) return;
    state.sessionId = s.id;
    state.messages = s.messages || [];
    chatEl.innerHTML = '';
    state.messages.forEach((m) => appendMessage(m.role, m.content));
    if (s.points && s.points.length) renderMap(s.points, '');
    else { mapBody.innerHTML = '<div class="map-empty">这次对话没有位置数据</div>'; }
    renderHistory();
  }

  function newChat() {
    state.sessionId = newId();
    state.messages = [];
    state.points = [];
    state.mapImage = '';
    chatEl.innerHTML = '';
    chatEl.appendChild(buildWelcome());
    bindWelcome();
    mapBody.innerHTML = '<div class="map-empty">发送消息后，查询到的地点会在这里展示 🌍</div>';
    renderHistory();
    inputEl.focus();
  }

  function buildWelcome() {
    const div = document.createElement('div');
    div.className = 'welcome';
    div.innerHTML = `
      <div class="welcome-title">有什么我能帮你的吗？</div>
      <div class="welcome-sub">找商场 · 挑酒店 · 认景点 · 规划玩法</div>
      <div class="welcome-examples">
        <button class="example" data-text="北京有什么好逛的商场？我喜欢高端品牌">💎 北京有什么好逛的商场？</button>
        <button class="example" data-text="上海外滩附近性价比高的酒店推荐">🏨 上海外滩附近性价比酒店</button>
        <button class="example" data-text="成都两天怎么玩？帮我推荐景点">✈️ 成都两天怎么玩？</button>
        <button class="example" data-photo="1">📷 上传照片，帮我认认这是哪儿</button>
      </div>`;
    return div;
  }

  function bindWelcome() {
    document.querySelectorAll('.example').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.dataset.photo) { imgInput.click(); return; }
        fillAndSend(btn.dataset.text);
      });
    });
  }

  function fillAndSend(text) {
    if (state.busy) return;
    inputEl.value = text;
    send();
  }

  /* ── 图片处理 ─────────────────────────── */
  async function compress(file) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

    const img = await new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = reject;
      im.src = dataUrl;
    });

    const MAX = 1280;
    const scale = Math.min(1, MAX / Math.max(img.width, img.height));
    if (scale === 1 && dataUrl.length < 900 * 1024) return dataUrl;

    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  }

  imgInput.addEventListener('change', async () => {
    const file = imgInput.files && imgInput.files[0];
    imgInput.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      alert('请选择图片文件～');
      return;
    }
    try {
      state.pendingImage = await compress(file);
      attachThumb.src = state.pendingImage;
      attachPreview.hidden = false;
    } catch {
      alert('图片读取失败，换一张试试');
    }
  });

  function clearImage() {
    state.pendingImage = '';
    attachPreview.hidden = true;
    attachThumb.removeAttribute('src');
  }

  $('attachRemove').addEventListener('click', clearImage);

  /* ── 交互绑定 ─────────────────────────── */
  sendBtn.addEventListener('click', send);
  $('imgBtn').addEventListener('click', () => imgInput.click());

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send();
    }
  });

  function autoGrow() {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
  }
  inputEl.addEventListener('input', autoGrow);

  $('newChat').addEventListener('click', newChat);
  $('sideToggle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));
  $('mapToggle').addEventListener('click', () => mapPanel.classList.toggle('hidden'));
  $('mapClose').addEventListener('click', () => mapPanel.classList.add('hidden'));

  renderHistory();
  bindWelcome();
  inputEl.focus();
})();

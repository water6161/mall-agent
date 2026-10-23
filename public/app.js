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
  const mapCanvasWrap = $('mapCanvasWrap');
  const mapEmpty = $('mapEmpty');
  const mapCount = $('mapCount');
  const mapList = $('mapList');
  const historyList = $('historyList');

  let state = {
    cid: localStorage.getItem(LS_CID) || newId(),
    sessionId: newId(),
    messages: [],
    points: [],
    pendingImage: '',
    busy: false,
    isPlan: false,
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

  /* ── 收藏夹 ───────────────────────────── */
  const LS_FAVS = 'xs_favs';
  const favList = $('favList');
  const favKey = (p) => `${p.name || ''}|${p.lng || ''}|${p.lat || ''}`;

  function loadFavs() {
    try { return JSON.parse(localStorage.getItem(LS_FAVS) || '[]'); }
    catch { return []; }
  }

  function saveFavs(list) {
    localStorage.setItem(LS_FAVS, JSON.stringify(list.slice(0, 50)));
    renderFavs();
  }

  function isFav(p) {
    return loadFavs().some((f) => favKey(f) === favKey(p));
  }

  function toggleFav(p, btn) {
    const list = loadFavs();
    const k = favKey(p);
    const idx = list.findIndex((f) => favKey(f) === k);
    if (idx >= 0) {
      list.splice(idx, 1);
      if (btn) { btn.textContent = '🤍'; btn.title = '收藏'; }
    } else {
      list.unshift({
        name: p.name, address: p.address, rating: p.rating,
        lng: p.lng, lat: p.lat, category: p.category, time: Date.now(),
      });
      if (btn) { btn.textContent = '❤️'; btn.title = '取消收藏'; }
    }
    saveFavs(list);
  }

  function renderFavs() {
    const list = loadFavs();
    if (!list.length) {
      favList.innerHTML = '<div class="history-empty">点地点卡片上的 🤍 收藏</div>';
      return;
    }
    favList.innerHTML = list.map((f, i) => `
      <div class="history-item fav-item" data-i="${i}">
        <span class="dot">❤️</span>
        <span class="fav-name">${escapeHtml(f.name || '未命名')}</span>
        <button class="fav-del" data-i="${i}" title="删除">✕</button>
      </div>`).join('');
    favList.querySelectorAll('.fav-item').forEach((el) => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.fav-del')) return;
        const f = loadFavs()[Number(el.dataset.i)];
        if (!f) return;
        toggleMapPanel(true);
        const idx = state.points.findIndex((p) => favKey(p) === favKey(f));
        if (idx >= 0) focusPoint(idx);
        else {
          appendMessage('assistant',
            `❤️ ${f.name}：收藏于之前的对话。地址：${f.address || '未知'}`
            + (f.rating ? ` · ★ ${f.rating}` : '')
            + `\n\n重新查询这个地点就能在地图上看到它啦～`);
        }
      });
    });
    favList.querySelectorAll('.fav-del').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const list = loadFavs();
        list.splice(Number(el.dataset.i), 1);
        saveFavs(list);
        // 同步刷新卡片按钮状态
        mapList.querySelectorAll('.fav-btn').forEach((btn) => {
          const p = state.points[Number(btn.dataset.i)];
          if (p) btn.textContent = isFav(p) ? '❤️' : '🤍';
        });
      });
    });
  }

  /* ── 地图面板 ─────────────────────────── */
  const CAT_COLOR = { shopping: '#FF6B6B', hotel: '#4D96FF', sightseeing: '#2BB673' };
  const CAT_LABEL = { shopping: '商场', hotel: '酒店', sightseeing: '景点' };

  // 高德栅格瓦片（中文注记，与高德 POI 的 GCJ-02 坐标一致，无需纠偏）
  const TILE_URL = 'https://webrd0{s}.is.autonavi.com/appmaptile'
    + '?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}';

  let map = null;
  const markerByIndex = new Map();
  let activeIndex = -1;

  function ensureMap() {
    if (map) return map;
    if (!window.L) return null;
    map = L.map('mapCanvas', { zoomControl: true, attributionControl: false });
    L.tileLayer(TILE_URL, {
      subdomains: ['1', '2', '3', '4'],
      minZoom: 3,
      maxZoom: 18,
    }).addTo(map);
    map.setView([34.5, 108.9], 4);
    return map;
  }

  function invalidate() {
    if (map) map.invalidateSize();
  }

  function setActive(index) {
    activeIndex = index;
    mapList.querySelectorAll('.poi-card').forEach((el, i) => {
      el.classList.toggle('active', i === index);
    });
    markerByIndex.forEach((marker, i) => {
      const el = marker.getElement();
      if (!el) return;
      const pin = el.querySelector('.poi-marker');
      if (pin) pin.classList.toggle('active', i === index);
    });
  }

  function focusPoint(index) {
    const p = state.points[index];
    if (!p || !map) return;
    const lat = Number(p.lat), lng = Number(p.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    setActive(index);
    map.setView([lat, lng], 15, { animate: true });
    const marker = markerByIndex.get(index);
    if (marker) marker.openPopup();
    const card = mapList.querySelectorAll('.poi-card')[index];
    if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function buildCard(p, index) {
    const color = CAT_COLOR[p.category] || '#8a94a6';
    const label = CAT_LABEL[p.category] || '地点';
    const nameEnc = encodeURIComponent(p.name || '');
    const markerUrl = `https://uri.amap.com/marker?position=${p.lng},${p.lat}&name=${nameEnc}`;
    const navUrl = `https://uri.amap.com/navigation?to=${p.lng},${p.lat}&toname=${nameEnc}&mode=transit`;
    const addr = p.address || '地址未知';
    const extra = [];
    if (p.rating) extra.push(`★ ${p.rating}`);
    if (p.cost) extra.push(`人均 ¥${p.cost}`);
    const card = document.createElement('div');
    card.className = 'poi-card';
    card.innerHTML = `<div class="poi-pin" style="background:${color}">${label}</div>
      <div class="poi-info">
        <div class="poi-name">${escapeHtml(p.name || '未命名地点')}</div>
        <div class="poi-addr">${escapeHtml(addr)}${extra.length ? ' · ' + escapeHtml(extra.join(' · ')) : ''}</div>
        <div class="poi-links">
          <a href="${markerUrl}" target="_blank" rel="noopener">📍 高德查看</a>
          <a href="${navUrl}" target="_blank" rel="noopener">🧭 导航</a>
        </div>
      </div>
      <button class="fav-btn" data-i="${index}" title="${isFav(p) ? '取消收藏' : '收藏'}">${isFav(p) ? '❤️' : '🤍'}</button>`;
    card.querySelector('.fav-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFav(p, e.currentTarget);
    });
    card.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      focusPoint(index);
    });
    return card;
  }

  function resetMapPanel(text) {
    state.points = [];
    markerByIndex.clear();
    activeIndex = -1;
    if (map) map.remove();
    map = null;
    mapCanvasWrap.hidden = true;
    mapList.innerHTML = '';
    mapCount.hidden = true;
    mapEmpty.hidden = false;
    mapEmpty.textContent = text;
  }

  function renderMap(points, isPlan) {
    const valid = (points || []).filter((p) =>
      Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)));
    state.isPlan = !!isPlan && valid.length > 1;
    state.points = valid;
    markerByIndex.clear();
    activeIndex = -1;
    mapList.innerHTML = '';
    mapPanel.classList.remove('hidden');

    if (!valid.length) {
      if (map) map.remove();
      map = null;
      mapCanvasWrap.hidden = true;
      mapEmpty.hidden = false;
      mapEmpty.textContent = '这次没有查到带坐标的地点';
      mapCount.hidden = true;
      return;
    }

    mapEmpty.hidden = true;
    valid.forEach((p, i) => mapList.appendChild(buildCard(p, i)));
    mapCount.hidden = false;
    mapCount.textContent = `共 ${valid.length} 个地点 · 点卡片或标记可定位`;

    const instance = ensureMap();
    if (!instance) { mapCanvasWrap.hidden = true; return; }

    mapCanvasWrap.hidden = false;
    invalidate();

    const pts = valid.map((p) => [Number(p.lat), Number(p.lng)]);
    if (pts.length === 1) {
      instance.setView(pts[0], 15);
    } else {
      instance.fitBounds(L.latLngBounds(pts), { padding: [26, 26], maxZoom: 15 });
    }

    valid.forEach((p, i) => {
      const color = CAT_COLOR[p.category] || '#8a94a6';
      const icon = L.divIcon({
        className: 'poi-marker-wrap',
        html: `<div class="poi-marker" style="--c:${color}">${i + 1}</div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13],
        popupAnchor: [0, -14],
      });
      const marker = L.marker([Number(p.lat), Number(p.lng)], { icon })
        .addTo(instance)
        .bindPopup(`<div class="poi-popup"><b>${escapeHtml(p.name || '未命名地点')}</b>`
          + `<div>${escapeHtml(p.address || '地址未知')}</div></div>`);
      marker.on('click', () => {
        setActive(i);
        const card = mapList.querySelectorAll('.poi-card')[i];
        if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      });
      markerByIndex.set(i, marker);
    });

    // 行程模式：按顺序把地点连成虚线路线
    if (state.isPlan && pts.length > 1) {
      L.polyline(pts, {
        color: '#2BB673', weight: 3, dashArray: '7 9',
        opacity: 0.75, lineJoin: 'round',
      }).addTo(instance);
    }

    requestAnimationFrame(invalidate);
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

      if (data.points && data.points.length) renderMap(data.points, !!data.plan);
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
      isPlan: !!state.isPlan,
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
    if (s.points && s.points.length) renderMap(s.points, !!s.isPlan);
    else resetMapPanel('这次对话没有位置数据');
    renderHistory();
  }

  function newChat() {
    state.sessionId = newId();
    state.messages = [];
    state.points = [];
    chatEl.innerHTML = '';
    chatEl.appendChild(buildWelcome());
    bindWelcome();
    resetMapPanel('发送消息后，查询到的地点会在这里展示 🌍');
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
        <button class="example" data-text="帮我安排北京一日游行程">🗓️ 帮我安排北京一日游</button>
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

  /* ── 语音输入（Web Speech API） ────────── */
  const micBtn = $('micBtn');
  let recog = null, recogOn = false;

  function setupSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.lang = 'zh-CN';
    r.interimResults = true;
    r.continuous = false;
    let base = '';
    r.onstart = () => { base = inputEl.value; };
    r.onresult = (e) => {
      let txt = '';
      for (const res of e.results) txt += res[0].transcript;
      inputEl.value = (base ? base + ' ' : '') + txt;
      autoGrow();
    };
    r.onend = () => { recogOn = false; micBtn.classList.remove('recording'); };
    r.onerror = () => { recogOn = false; micBtn.classList.remove('recording'); };
    return r;
  }

  micBtn.addEventListener('click', () => {
    if (recogOn) { recog && recog.stop(); return; }
    if (!recog) recog = setupSpeech();
    if (!recog) {
      appendMessage('assistant', '🎤 这个浏览器不支持语音输入，建议用 Chrome 或 Edge 试试～');
      return;
    }
    try {
      recog.start();
      recogOn = true;
      micBtn.classList.add('recording');
    } catch { /* 重复启动忽略 */ }
  });

  /* ── 分享卡片（Canvas 生成 PNG） ──────── */
  function wrapText(ctx, text, maxWidth) {
    const lines = [];
    for (const raw of (text || '').split(/\r?\n/)) {
      let line = '';
      for (const ch of raw) {
        if (ctx.measureText(line + ch).width > maxWidth && line) {
          lines.push(line); line = ch;
        } else line += ch;
      }
      lines.push(line);
    }
    return lines;
  }

  function shareCard() {
    const lastBot = [...state.messages].reverse().find((m) => m.role === 'assistant');
    if (!lastBot && !state.points.length) {
      alert('还没有可分享的内容，先聊点什么吧～');
      return;
    }
    const W = 750, PAD = 56;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    // 先量高度
    const bodyText = (lastBot ? lastBot.content : '').slice(0, 600);
    ctx.font = '26px sans-serif';
    const bodyLines = wrapText(ctx, bodyText, W - PAD * 2);
    const poiLines = state.points.slice(0, 6)
      .map((p) => `${p.name}${p.rating ? ' ★' + p.rating : ''}`);
    const H = 200 + bodyLines.length * 40 + (poiLines.length ? poiLines.length * 40 + 90 : 0) + 90;
    canvas.width = W; canvas.height = H;

    // 背景 + 头部
    const grad = ctx.createLinearGradient(0, 0, W, 220);
    grad.addColorStop(0, '#2BB673'); grad.addColorStop(1, '#1E8FA8');
    ctx.fillStyle = grad; ctx.fillRect(0, 0, W, 200);
    ctx.fillStyle = '#f6f8fb'; ctx.fillRect(0, 200, W, H - 200);

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 44px sans-serif';
    ctx.fillText('🧳 小水 · 出行决策助手', PAD, 92);
    ctx.font = '24px sans-serif';
    ctx.globalAlpha = 0.9;
    ctx.fillText(state.isPlan ? '我的行程安排' : '我的出行发现', PAD, 140);
    ctx.globalAlpha = 1;

    // 正文
    ctx.fillStyle = '#2a3342'; ctx.font = '26px sans-serif';
    bodyLines.forEach((line, i) => ctx.fillText(line, PAD, 250 + i * 40));

    // 地点清单
    let y = 250 + bodyLines.length * 40;
    if (poiLines.length) {
      y += 30;
      ctx.fillStyle = '#8a94a6'; ctx.font = '22px sans-serif';
      ctx.fillText('📍 相关地点', PAD, y); y += 44;
      ctx.fillStyle = '#2a3342'; ctx.font = '24px sans-serif';
      poiLines.forEach((line) => { ctx.fillText('· ' + line, PAD, y); y += 40; });
    }

    // 页脚
    ctx.fillStyle = '#b0b8c4'; ctx.font = '22px sans-serif';
    ctx.fillText('由「小水」生成 · 识景点 / 找商场 / 排行程', PAD, H - 40);

    const a = document.createElement('a');
    a.download = 'xiaoshui-share.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
  }

  $('shareBtn').addEventListener('click', shareCard);

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
  function toggleMapPanel(show) {
    const shouldShow = show === undefined ? mapPanel.classList.contains('hidden') : show;
    mapPanel.classList.toggle('hidden', !shouldShow);
    if (shouldShow) requestAnimationFrame(invalidate);
  }

  $('mapToggle').addEventListener('click', () => toggleMapPanel());
  $('mapClose').addEventListener('click', () => toggleMapPanel(false));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !mapPanel.classList.contains('hidden')) toggleMapPanel(false);
  });

  renderHistory();
  renderFavs();
  bindWelcome();
  inputEl.focus();
})();

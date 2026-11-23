'use strict';
/* 철따라 — 제철 버킷리스트 PWA (no framework, offline) */

// ---------- 날짜 ----------
const PERIOD = { early: [1, 10, '초'], mid: [11, 20, '중'], late: [21, 31, '말'] };
const DAY = 864e5;
function pad(n) { return String(n).padStart(2, '0'); }
function ymd(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function getToday() {
  try {
    const q = new URLSearchParams(location.search).get('date');
    const m = q && /^(\d{4})-(\d{2})-(\d{2})$/.exec(q);
    if (m) {
      const d = new Date(+m[1], +m[2] - 1, +m[3]);
      if (d.getFullYear() === +m[1] && d.getMonth() === +m[2] - 1 && d.getDate() === +m[3]) return d;
    }
  } catch (e) {}
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}
const TODAY = getToday();
const YEAR = TODAY.getFullYear();
function dim(y, m) { return new Date(y, m, 0).getDate(); }
function diffDays(a, b) { return Math.round((a - b) / DAY); }
function startOf(y, s) { return new Date(y, s.month - 1, PERIOD[s.period][0]); }
function endOf(y, e) { return new Date(y, e.month - 1, e.period === 'late' ? dim(y, e.month) : PERIOD[e.period][1]); }
function pkey(p) { return p.month * 3 + ['early', 'mid', 'late'].indexOf(p.period); }
function wraps(it) { return pkey(it.end) < pkey(it.start); }
function periodText(it) {
  const f = (p) => p.month + '월 ' + PERIOD[p.period][2];
  const a = f(it.start), b = f(it.end);
  return a === b ? a : a + ' ~ ' + b;
}
function seasonOfMonth(m) { return m >= 3 && m <= 5 ? 'spring' : m >= 6 && m <= 8 ? 'summer' : m >= 9 && m <= 11 ? 'autumn' : 'winter'; }
const SEASONS = [
  { id: 'spring', name: '봄', label: '3–5월', months: [3, 4, 5] },
  { id: 'summer', name: '여름', label: '6–8월', months: [6, 7, 8] },
  { id: 'autumn', name: '가을', label: '9–11월', months: [9, 10, 11] },
  { id: 'winter', name: '겨울', label: '12–2월', months: [12, 1, 2] },
];
// state: now | soon | later ; daysLeft (now), daysUntil (not now)
function statusOf(it, today) {
  const y = today.getFullYear();
  let next = null;
  for (let yy = y - 1; yy <= y + 1; yy++) {
    const s = startOf(yy, it.start), e = endOf(wraps(it) ? yy + 1 : yy, it.end);
    if (s <= today && today <= e) return { state: 'now', daysLeft: diffDays(e, today), start: s, end: e };
    if (s > today && (!next || s < next)) next = s;
  }
  const du = diffDays(next, today);
  return { state: du <= 14 ? 'soon' : 'later', daysUntil: du, start: next };
}

// ---------- 저장소 (설정=localStorage, 기록=IndexedDB, 실패 시 메모리) ----------
const memLS = {};
function lsGet(k, def) {
  try { const v = localStorage.getItem(k); if (v !== null) return JSON.parse(v); } catch (e) {}
  return k in memLS ? memLS[k] : def;
}
function lsSet(k, v) {
  memLS[k] = v;
  try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
}
const store = { db: null, bucket: new Map(), records: new Map(), persistent: false };
function openDB() {
  return new Promise((res) => {
    try {
      if (!window.indexedDB) return res(null);
      const r = indexedDB.open('cheolttara', 1);
      r.onupgradeneeded = () => {
        const d = r.result;
        d.createObjectStore('bucket', { keyPath: 'id' });
        d.createObjectStore('records', { keyPath: 'key' });
      };
      r.onsuccess = () => res(r.result);
      r.onerror = () => res(null);
      r.onblocked = () => res(null);
    } catch (e) { res(null); }
  });
}
function idbAll(name) {
  return new Promise((res) => {
    try {
      const rq = store.db.transaction(name, 'readonly').objectStore(name).getAll();
      rq.onsuccess = () => res(rq.result || []);
      rq.onerror = () => res([]);
    } catch (e) { res([]); }
  });
}
function idbOp(name, fn) {
  return new Promise((res) => {
    try {
      if (!store.db) return res(false);
      const tx = store.db.transaction(name, 'readwrite');
      fn(tx.objectStore(name));
      tx.oncomplete = () => res(true);
      tx.onerror = tx.onabort = () => res(false);
    } catch (e) { res(false); }
  });
}
async function initStore() {
  try { store.db = await openDB(); } catch (e) { store.db = null; }
  if (store.db) {
    store.persistent = true;
    (await idbAll('bucket')).forEach((b) => store.bucket.set(b.id, b));
    (await idbAll('records')).forEach((r) => store.records.set(r.key, r));
  }
}
function setBucket(id, on) {
  if (on) {
    const b = { id, addedAt: ymd(TODAY) };
    store.bucket.set(id, b);
    idbOp('bucket', (s) => s.put(b));
  } else {
    store.bucket.delete(id);
    idbOp('bucket', (s) => s.delete(id));
  }
}
function putRecord(r) { store.records.set(r.key, r); return idbOp('records', (s) => s.put(r)); }
function delRecord(key) { store.records.delete(key); return idbOp('records', (s) => s.delete(key)); }
const recKey = (id, y) => id + ':' + y;
const doneRec = (id) => store.records.get(recKey(id, YEAR));

// ---------- 상태 ----------
let ITEMS = [];
let BYID = {};
const ui = { tab: 'home', filter: 'all', year: YEAR };
const CATS = { food: '🍓 음식', nature: '🌸 자연', event: '🎉 행사' };

const $ = (s, r) => (r || document).querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const urls = [];
function blobUrl(b) { try { const u = URL.createObjectURL(b); urls.push(u); return u; } catch (e) { return ''; } }
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), 2200);
}

// ---------- 공통 조각 ----------
function badges(it, st) {
  let h = '';
  if (st.state === 'now' && st.daysLeft <= 14) h += '<span class="badge end">곧 끝나요</span>';
  if (st.state === 'soon') h += '<span class="badge soon">곧 시작해요</span>';
  if (doneRec(it.id)) h += '<span class="badge done">해냈어요</span>';
  return h;
}
function metaText(it, st) {
  let m = periodText(it);
  if (it.region !== '전국') m += ' · ' + it.region;
  if (st.state === 'now') m += ' · D-' + st.daysLeft + ' 종료';
  else if (st.state === 'soon') m += ' · ' + st.daysUntil + '일 뒤 시작';
  return m;
}
function itemCard(it, st) {
  const inB = store.bucket.has(it.id);
  return `<div class="card-wrap" style="position:relative"><button class="card" data-open="${it.id}">
    <span class="em">${it.emoji}</span>
    <span class="body"><span class="name">${esc(it.name)} ${badges(it, st)}</span>
    <span class="sum" style="display:block">${esc(it.summary)}</span>
    <span class="meta">${esc(metaText(it, st))}</span></span></button>
    <button class="heart" data-heart="${it.id}" aria-pressed="${inB}" aria-label="${esc(it.name)} ${inB ? '버킷리스트에서 빼기' : '버킷리스트에 담기'}">${inB ? '♥' : '♡'}</button></div>`;
}
function withStatus(list) { return list.map((it) => ({ it, st: statusOf(it, TODAY) })); }

// ---------- 화면: 이번 철 ----------
function viewHome() {
  const f = ui.filter;
  const all = withStatus(ITEMS).filter((x) => f === 'all' || x.it.category === f);
  const now = all.filter((x) => x.st.state === 'now').sort((a, b) => a.st.daysLeft - b.st.daysLeft || a.it.name.localeCompare(b.it.name, 'ko'));
  const soon = all.filter((x) => x.st.state === 'soon').sort((a, b) => a.st.daysUntil - b.st.daysUntil);
  const chips = [['all', '전체'], ['food', CATS.food], ['nature', CATS.nature], ['event', CATS.event]]
    .map(([k, l]) => `<button class="chip" data-filter="${k}" aria-pressed="${f === k}">${l}</button>`).join('');
  let h = `<div class="chips" role="group" aria-label="분류">${chips}</div>`;
  h += `<h2>지금 제철 <small>${now.length}개</small></h2>`;
  h += now.length ? now.map((x) => itemCard(x.it, x.st)).join('') : '<div class="empty"><div class="big">🍃</div>지금 제철인 항목이 없어요</div>';
  if (soon.length) {
    h += `<h2>곧 시작해요 <small>14일 안</small></h2>` + soon.map((x) => itemCard(x.it, x.st)).join('');
  }
  return h;
}

// ---------- 화면: 버킷리스트 ----------
function bucketCard(it, st) {
  const rec = doneRec(it.id);
  let h = `<div style="position:relative"><button class="card" data-open="${it.id}">
    <span class="em">${it.emoji}</span>
    <span class="body"><span class="name">${esc(it.name)} ${badges(it, st)}</span>
    <span class="meta">${esc(metaText(it, st))}</span></span></button>
    <button class="heart" data-heart="${it.id}" aria-pressed="true" aria-label="${esc(it.name)} 버킷리스트에서 빼기">♥</button>`;
  if (rec) {
    h += `<div class="stampline" style="margin:-4px 0 10px"><span class="stampmark">${esc(rec.date.slice(5).replace('-', '/'))}</span>
      ${rec.photo ? `<img data-photo="${esc(rec.key)}" alt="${esc(it.name)} 사진">` : ''}
      <div class="st"><b>${esc(rec.date)}</b> 해냈어요${rec.memo ? '<br>' + esc(rec.memo) : ''}</div>
      <button class="btn ghost" style="margin-left:auto;min-height:40px;padding:0 12px;font-size:14px" data-undo="${it.id}">취소</button></div>`;
  } else {
    h += `<div class="actions" style="margin:-4px 0 12px"><button class="btn" data-done="${it.id}">✔ 해냈어요</button></div>`;
  }
  return h + '</div>';
}
function viewBucket() {
  const list = [...store.bucket.keys()].map((id) => BYID[id]).filter(Boolean).map((it) => ({ it, st: statusOf(it, TODAY) }));
  if (!list.length) return '<div class="empty"><div class="big">🧺</div>아직 담아둔 항목이 없어요.<br>‘이번 철’에서 ♡를 눌러 담아보세요.</div>';
  const groups = [
    ['지금 제철', list.filter((x) => x.st.state === 'now').sort((a, b) => a.st.daysLeft - b.st.daysLeft)],
    ['곧 시작', list.filter((x) => x.st.state === 'soon').sort((a, b) => a.st.daysUntil - b.st.daysUntil)],
    ['지난 철', list.filter((x) => x.st.state === 'later').sort((a, b) => a.st.daysUntil - b.st.daysUntil)],
  ];
  return groups.filter((g) => g[1].length).map(([t, l]) => `<h2>${t} <small>${l.length}개</small></h2>` + l.map((x) => bucketCard(x.it, x.st)).join('')).join('');
}

// ---------- 화면: 도장판 ----------
function viewStamps() {
  const years = new Set([YEAR - 2, YEAR - 1, YEAR]);
  store.records.forEach((r) => years.add(r.year));
  const ys = [...years].sort((a, b) => b - a);
  if (!years.has(ui.year)) ui.year = YEAR;
  const recs = new Map();
  store.records.forEach((r) => { if (r.year === ui.year) recs.set(r.id, r); });
  let h = `<div class="yearbar"><label for="yearSel"><b>연도</b></label>
    <select id="yearSel">${ys.map((y) => `<option value="${y}"${y === ui.year ? ' selected' : ''}>${y}년</option>`).join('')}</select>
    <span style="margin-left:auto;color:var(--sub);font-size:14px">모은 도장 <b id="stampTotal">${recs.size}</b>개</span></div>`;
  SEASONS.forEach((s) => {
    const its = ITEMS.filter((it) => s.months.includes(it.start.month))
      .sort((a, b) => s.months.indexOf(a.start.month) - s.months.indexOf(b.start.month) || pkey(a.start) - pkey(b.start));
    const got = its.filter((it) => recs.has(it.id)).length;
    h += `<section class="board ${s.id}" data-season-board="${s.id}"><h3>${s.name} <small style="font-weight:500;color:var(--sub);font-size:12px">${s.label}</small><span class="prog">${s.name} ${got}/${its.length}</span></h3><div class="grid">` +
      its.map((it) => `<button class="stamp${recs.has(it.id) ? ' on' : ''}" data-open="${it.id}" aria-label="${esc(it.name)}${recs.has(it.id) ? ' 도장 찍음' : ''}"><span class="circ">${it.emoji}</span><span class="nm">${esc(it.name)}</span></button>`).join('') +
      '</div></section>';
  });
  h += `<button class="btn block" id="makeCard" style="margin-top:8px">🎴 올해의 제철 카드 만들기</button>`;
  return h;
}

// ---------- 화면: 알림 ----------
function alertList() {
  const out = [];
  store.bucket.forEach((b) => {
    const it = BYID[b.id]; if (!it) return;
    const st = statusOf(it, TODAY);
    if (st.state === 'now' && st.daysLeft <= 14 && !doneRec(it.id)) out.push({ it, kind: 'end', d: st.daysLeft });
    else if (st.state === 'soon') out.push({ it, kind: 'start', d: st.daysUntil });
  });
  return out.sort((a, b) => a.d - b.d);
}
const dtxt = (d) => (d === 0 ? 'D-day' : 'D-' + d);
function alertMsg(a) { return `담아둔 '${a.it.name}'가 ${a.kind === 'end' ? '곧 끝나요' : '곧 시작해요'}`; }
function viewAlerts() {
  const list = alertList();
  const on = !!lsGet('notifyOnOpen', false);
  let h = `<div class="toggle"><div><b>앱을 열 때 알림 보내기</b><div style="font-size:13px;color:var(--sub)">담아둔 항목이 곧 끝나거나 시작하면 알려줘요</div></div>
    <button class="switch" id="notifySwitch" role="switch" aria-checked="${on}" aria-label="앱을 열 때 알림 보내기"></button></div>
    <div class="note" id="notifyNote">ℹ️ 이 버전에서는 앱을 열지 않은 상태의 백그라운드 푸시 알림은 지원하지 않아요. 앱을 열 때만 알림을 보내드려요.</div>`;
  h += `<h2>곧 확인할 항목 <small>14일 안</small></h2>`;
  h += list.length ? list.map((a) => `<button class="alert ${a.kind}" data-open="${a.it.id}" style="width:100%;text-align:left">
      <span class="em">${a.it.emoji}</span><span>${a.kind === 'end' ? `담아둔 '${esc(a.it.name)}'가 곧 끝나요` : `담아둔 '${esc(a.it.name)}'가 곧 시작해요`}</span>
      <span class="dd">· ${dtxt(a.d)}</span></button>`).join('')
    : '<div class="empty"><div class="big">🔕</div>14일 안에 시작하거나 끝나는 담아둔 항목이 없어요</div>';
  return h;
}
async function notifyOnOpen() {
  try {
    if (!lsGet('notifyOnOpen', false) || !('Notification' in window) || Notification.permission !== 'granted') return;
    const sent = lsGet('notifiedLog', {});
    const today = ymd(TODAY);
    const list = alertList().filter((a) => sent[a.it.id] !== today);
    if (!list.length) return;
    let reg = null;
    try { reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : null; } catch (e) {}
    for (const a of list) {
      const opts = { body: `${dtxt(a.d)} · ${periodText(a.it)}`, icon: 'icons/icon-192.png', tag: 'cheolttara-' + a.it.id };
      try {
        if (reg && reg.showNotification) await reg.showNotification(alertMsg(a), opts);
        else new Notification(alertMsg(a), opts);
        sent[a.it.id] = today;
      } catch (e) {}
    }
    lsSet('notifiedLog', sent);
  } catch (e) {}
}
async function toggleNotify() {
  const on = !!lsGet('notifyOnOpen', false);
  const note = $('#notifyNote');
  if (on) { lsSet('notifyOnOpen', false); return render(); }
  if (!('Notification' in window)) { toast('이 브라우저는 알림을 지원하지 않아요'); return; }
  let perm = Notification.permission;
  try { if (perm === 'default') perm = await Notification.requestPermission(); } catch (e) {}
  if (perm === 'granted') { lsSet('notifyOnOpen', true); render(); toast('앱을 열 때 알림을 보낼게요'); notifyOnOpen(); }
  else { lsSet('notifyOnOpen', false); render(); toast('알림 권한이 꺼져 있어요. 브라우저 설정에서 허용해 주세요'); }
}

// ---------- 시트 ----------
function openSheet(html) {
  closeSheet();
  const o = document.createElement('div');
  o.className = 'overlay'; o.id = 'overlay';
  o.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="grab"></div>${html}</div>`;
  o.addEventListener('click', (e) => { if (e.target === o) closeSheet(); });
  $('#sheetRoot').appendChild(o);
  return o;
}
function closeSheet() { const o = $('#overlay'); if (o) o.remove(); }
function hydratePhotos(root) {
  root.querySelectorAll('img[data-photo]').forEach((img) => {
    const r = store.records.get(img.dataset.photo);
    if (r && r.photo) img.src = blobUrl(r.photo);
  });
}
function detailSheet(id) {
  const it = BYID[id]; if (!it) return;
  const st = statusOf(it, TODAY), inB = store.bucket.has(id), rec = doneRec(id);
  const when = st.state === 'now' ? `지금 제철 · 종료까지 D-${st.daysLeft}` : st.state === 'soon' ? `${st.daysUntil}일 뒤 시작` : '지금은 철이 아니에요';
  const o = openSheet(`<div style="display:flex;gap:14px;align-items:center"><span class="big">${it.emoji}</span><div><h3>${esc(it.name)}</h3>
    <div>${badges(it, st)}</div></div></div>
    <div class="row"><b>${esc(CATS[it.category] || '')} · ${esc(it.subcategory)}</b>${esc(it.summary)}</div>
    <div class="row"><b>시기</b>${esc(periodText(it))} (${esc(it.region)}) · ${when}</div>
    <div class="row tipbox"><b>즐기는 팁</b>${esc(it.tip)}</div>
    ${rec ? `<div class="stampline"><span class="stampmark">${esc(rec.date.slice(5).replace('-', '/'))}</span>${rec.photo ? `<img data-photo="${esc(rec.key)}" alt="">` : ''}<div class="st"><b>${esc(rec.date)}</b> 해냈어요${rec.memo ? '<br>' + esc(rec.memo) : ''}</div></div>` : ''}
    <div class="actions"><button class="btn${inB ? ' ghost' : ''}" id="sheetHeart">${inB ? '♥ 담았어요 (빼기)' : '♡ 버킷리스트에 담기'}</button>
    ${rec ? '' : '<button class="btn ghost" id="sheetDone">✔ 해냈어요</button>'}
    <button class="btn ghost" id="sheetClose">닫기</button></div>`);
  hydratePhotos(o);
  $('#sheetHeart').onclick = () => { setBucket(id, !inB); render(); detailSheet(id); };
  const d = $('#sheetDone'); if (d) d.onclick = () => doneSheet(id);
  $('#sheetClose').onclick = closeSheet;
}

// 사진 리사이즈 (최대 1000px JPEG)
function resizePhoto(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const s = Math.min(1, 1000 / Math.max(img.naturalWidth, img.naturalHeight));
        const c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(img.naturalWidth * s)); c.height = Math.max(1, Math.round(img.naturalHeight * s));
        const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
        c.toBlob((b) => { URL.revokeObjectURL(url); b ? resolve(b) : reject(new Error('toBlob')); }, 'image/jpeg', 0.85);
      } catch (e) { reject(e); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('img')); };
    img.src = url;
  });
}
function doneSheet(id) {
  const it = BYID[id]; if (!it) return;
  const o = openSheet(`<h3>${it.emoji} ${esc(it.name)} 해냈어요!</h3>
    <div class="field"><label for="photoIn">사진 (선택)</label><input type="file" id="photoIn" accept="image/*"><img id="photoPrev" class="preview" alt="" hidden></div>
    <div class="field"><label for="memoIn">한 줄 메모 (선택)</label><input type="text" id="memoIn" maxlength="50" placeholder="오늘의 기억을 한 줄로"><div class="counter"><span id="cnt">0</span>/50</div></div>
    <div class="actions"><button class="btn" id="doneSave">도장 찍기 · ${ymd(TODAY)}</button><button class="btn ghost" id="doneCancel">취소</button></div>`);
  let photo = null, busy = null;
  $('#memoIn').oninput = (e) => { $('#cnt').textContent = e.target.value.length; };
  $('#photoIn').onchange = (e) => {
    const f = e.target.files && e.target.files[0]; photo = null;
    if (!f) { $('#photoPrev').hidden = true; return; }
    busy = resizePhoto(f).then((b) => { photo = b; const p = $('#photoPrev'); if (p) { p.src = blobUrl(b); p.hidden = false; } })
      .catch(() => toast('사진을 불러오지 못했어요'));
  };
  $('#doneCancel').onclick = closeSheet;
  $('#doneSave').onclick = async () => {
    const btn = $('#doneSave'); btn.disabled = true;
    if (busy) await busy;
    const memo = $('#memoIn').value.slice(0, 50).trim();
    if (!store.bucket.has(id)) setBucket(id, true);
    const ok = await putRecord({ key: recKey(id, YEAR), id, year: YEAR, date: ymd(TODAY), memo, photo });
    closeSheet(); render();
    toast(ok || !store.persistent ? '도장을 찍었어요! 🎉' : '저장에 문제가 있어 이번 방문에만 기억해요');
  };
}

// ---------- 공유 카드 ----------
const EMOJI_FONT = '"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
const TEXT_FONT = 'Pretendard,"Apple SD Gothic Neo","Noto Sans KR","Noto Sans CJK KR",sans-serif';
const ACCENTS = { spring: '#d6577a', summer: '#2f8a56', autumn: '#c96a12', winter: '#3b78b8' };
function loadImg(blob) {
  return new Promise((res) => {
    const u = URL.createObjectURL(blob), i = new Image();
    i.onload = () => { res(i); setTimeout(() => URL.revokeObjectURL(u), 1000); };
    i.onerror = () => res(null);
    i.src = u;
  });
}
async function renderCard(year) {
  const W = 1080, H = 1350, c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'), acc = ACCENTS[seasonOfMonth(TODAY.getMonth() + 1)];
  const recs = [...store.records.values()].filter((r) => r.year === year && BYID[r.id])
    .sort((a, b) => a.date.localeCompare(b.date));
  g.fillStyle = '#fbf8f3'; g.fillRect(0, 0, W, H);
  g.fillStyle = acc; g.fillRect(0, 0, W, 14);
  g.strokeStyle = acc; g.lineWidth = 6; g.globalAlpha = .35; g.strokeRect(36, 36, W - 72, H - 72); g.globalAlpha = 1;
  g.textAlign = 'center'; g.textBaseline = 'alphabetic';
  g.fillStyle = acc; g.font = `800 96px ${TEXT_FONT}`; g.fillText('철따라', W / 2, 180);
  g.fillStyle = '#2b2622'; g.font = `700 56px ${TEXT_FONT}`; g.fillText(`${year}년 나의 제철 카드`, W / 2, 262);
  g.font = `600 44px ${TEXT_FONT}`; g.fillStyle = acc;
  g.fillText(`제철 도장 ${recs.length}개 / ${ITEMS.length}개`, W / 2, 332);
  // 이모지 격자
  const emojis = recs.map((r) => BYID[r.id].emoji).slice(0, 40);
  const cols = 10, cell = 88, gx = (W - cols * cell) / 2;
  g.font = `56px ${EMOJI_FONT}`; g.fillStyle = '#000'; g.textBaseline = 'middle';
  if (!emojis.length) { g.font = `500 40px ${TEXT_FONT}`; g.fillStyle = '#7a7068'; g.fillText('아직 찍은 도장이 없어요', W / 2, 450); }
  emojis.forEach((e, i) => { g.fillText(e, gx + (i % cols) * cell + cell / 2, 430 + Math.floor(i / cols) * cell + cell / 2); });
  if (recs.length > 40) { g.font = `500 32px ${TEXT_FONT}`; g.fillStyle = '#7a7068'; g.fillText(`외 ${recs.length - 40}개`, W / 2, 800); }
  // 사진 최대 4장
  const withPhoto = recs.filter((r) => r.photo).slice(-4);
  const imgs = (await Promise.all(withPhoto.map((r) => loadImg(r.photo)))).filter(Boolean);
  const ps = 230, gap = 20, total = imgs.length * ps + (imgs.length - 1) * gap, px = (W - total) / 2, py = 860;
  imgs.forEach((im, i) => {
    const x = px + i * (ps + gap), s = Math.min(im.naturalWidth, im.naturalHeight), sx = (im.naturalWidth - s) / 2, sy = (im.naturalHeight - s) / 2;
    g.save(); g.beginPath(); g.roundRect ? g.roundRect(x, py, ps, ps, 24) : g.rect(x, py, ps, ps); g.clip();
    g.drawImage(im, sx, sy, s, s, x, py, ps, ps); g.restore();
  });
  g.textBaseline = 'alphabetic'; g.fillStyle = '#7a7068'; g.font = `500 34px ${TEXT_FONT}`;
  g.fillText('계절 따라 하나씩, 제철 버킷리스트', W / 2, H - 90);
  return c;
}
async function cardSheet() {
  let canvas;
  try { canvas = await renderCard(ui.year); } catch (e) { toast('카드를 만들지 못했어요'); return; }
  const o = openSheet(`<h3>${ui.year}년 제철 카드</h3><div class="field"><canvas id="cardOut" class="cardprev"></canvas></div>
    <div class="actions"><button class="btn" id="cardShare">공유하기</button><button class="btn ghost" id="cardClose">닫기</button></div>`);
  const out = $('#cardOut'); out.width = canvas.width; out.height = canvas.height; out.getContext('2d').drawImage(canvas, 0, 0);
  out.dataset.ready = '1';
  $('#cardClose').onclick = closeSheet;
  $('#cardShare').onclick = async () => {
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/png'));
    if (!blob) return toast('이미지를 만들지 못했어요');
    const file = new File([blob], `cheolttara-${ui.year}.png`, { type: 'image/png' });
    try {
      if (navigator.canShare && navigator.canShare({ files: [file] }) && navigator.share) {
        await navigator.share({ files: [file], title: '철따라', text: `${ui.year}년 나의 제철 카드` }); return;
      }
    } catch (e) { if (e && e.name === 'AbortError') return; }
    const a = document.createElement('a'); a.href = blobUrl(blob); a.download = file.name;
    document.body.appendChild(a); a.click(); a.remove(); toast('이미지를 저장했어요');
  };
}

// ---------- 렌더/이벤트 ----------
const TITLES = { home: '이번 철', bucket: '내 버킷리스트', stamps: '도장판', alerts: '알림' };
function render() {
  const season = seasonOfMonth(TODAY.getMonth() + 1);
  document.body.dataset.season = season;
  document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === ui.tab)));
  $('#title').textContent = ui.tab === 'home' ? '철따라' : TITLES[ui.tab];
  $('#subtitle').textContent = ui.tab === 'home' ? `${TODAY.getMonth() + 1}월 ${TODAY.getDate()}일 · ${SEASONS.find((s) => s.id === season).name}, 지금 이 철에 담아요` : '철따라';
  const v = $('#view');
  v.innerHTML = { home: viewHome, bucket: viewBucket, stamps: viewStamps, alerts: viewAlerts }[ui.tab]();
  hydratePhotos(v);
  $('#alertDot').hidden = alertList().length === 0;
}
function bind() {
  document.addEventListener('click', (e) => {
    const t = e.target.closest('button,select'); if (!t) return;
    const d = t.dataset;
    if (d.tab) { ui.tab = d.tab; closeSheet(); render(); window.scrollTo(0, 0); }
    else if (d.filter) { ui.filter = d.filter; render(); }
    else if (d.heart) {
      const on = !store.bucket.has(d.heart); setBucket(d.heart, on); render();
      toast(on ? '버킷리스트에 담았어요' : '버킷리스트에서 뺐어요');
    }
    else if (d.open) detailSheet(d.open);
    else if (d.done) doneSheet(d.done);
    else if (d.undo) { delRecord(recKey(d.undo, YEAR)); render(); toast('도장을 되돌렸어요'); }
    else if (t.id === 'notifySwitch') toggleNotify();
    else if (t.id === 'makeCard') cardSheet();
  });
  document.addEventListener('change', (e) => { if (e.target.id === 'yearSel') { ui.year = +e.target.value; render(); } });
}

async function init() {
  bind();
  try {
    const res = await fetch('data/seasonal_items.json');
    ITEMS = await res.json();
    BYID = Object.fromEntries(ITEMS.map((i) => [i.id, i]));
  } catch (e) {
    $('#view').innerHTML = '<div class="empty"><div class="big">😢</div>데이터를 불러오지 못했어요.<br>잠시 후 다시 열어주세요.</div>';
    return;
  }
  await initStore();
  render();
  document.body.dataset.ready = '1';
  if (!store.persistent) toast('저장소를 쓸 수 없어 이번 방문에만 기억해요');
  notifyOnOpen();
  try { if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {}); } catch (e) {}
}
init();

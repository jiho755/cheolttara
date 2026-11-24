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
    const b = store.bucket.get(id) || { id, addedAt: ymd(TODAY) };
    if (id.startsWith('fest-')) { // 축제는 나중에 festivals.json 에서 빠져도 보이도록 정보를 함께 저장
      const f = FESTBYID[id.slice(5)];
      if (f) Object.assign(b, { title: f.title, start: f.start, end: f.end, addr: f.addr, sido: f.sido });
    }
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
let PLACES = [];
let PLACEBYID = {};
let FESTS = [];
let FESTBYID = {};
let FEST_META = { updated: null, source: '' };
const REGIONS = [
  ['전체', null],
  ['수도권', ['서울', '경기', '인천']],
  ['강원', ['강원']],
  ['충청', ['대전', '세종', '충북', '충남']],
  ['전라', ['광주', '전북', '전남']],
  ['경상', ['부산', '대구', '울산', '경북', '경남']],
  ['제주', ['제주']],
];
const FEST_PAGE = 10, KEEP_DAYS = 180;
const ui = { tab: 'home', mi: 0, region: '전체', festLimit: FEST_PAGE, year: YEAR };
const CATS = { food: '🍓 음식', nature: '🌸 자연', event: '🎉 행사' };

const $ = (s, r) => (r || document).querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const urls = [];
function blobUrl(b) { try { const u = URL.createObjectURL(b); urls.push(u); return u; } catch (e) { return ''; } }
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), 2200);
}

// ---------- 날짜·월 ----------
function parseYmd(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}
const fmtMD = (d) => (d.getMonth() + 1) + '/' + d.getDate();
function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
function monthList() {
  const out = [];
  for (let i = 0; i < 12; i++) {
    const f = new Date(TODAY.getFullYear(), TODAY.getMonth() + i, 1);
    out.push({ y: f.getFullYear(), m: f.getMonth() + 1, first: f, last: new Date(f.getFullYear(), f.getMonth() + 1, 0) });
  }
  return out;
}
function monthLabel(mo, i) { return mo.m + '월' + (i > 0 && mo.m === 1 ? ' ’' + String(mo.y).slice(2) : ''); }
// seasonal item 이 m월에 걸치는가 (해를 넘기는 항목 포함)
function inMonth(it, m) {
  const s = it.start.month, e = it.end.month;
  return s <= e ? m >= s && m <= e : m >= s || m <= e;
}

// ---------- 종류별 정보 (카드·버킷·알림 공통) ----------
const kindOf = (id) => (id.startsWith('fest-') ? 'fest' : id.startsWith('place-') ? 'place' : 'item');
function festFor(id) {
  const cid = id.slice(5);
  if (FESTBYID[cid]) return FESTBYID[cid];
  const b = store.bucket.get(id) || {};
  const r = [...store.records.values()].find((x) => x.id === id) || {};
  const title = b.title || r.title;
  if (!title) return null;
  return { id: cid, title, start: b.start || '', end: b.end || '', addr: b.addr || '', sido: b.sido || '', image: '', tel: '', mapx: null, mapy: null };
}
function sigungu(f) {
  const w = (f.addr || '').split(/\s+/);
  return w.length > 1 ? w[1] : (f.sido || '');
}
function doneBadge(id) { return doneRec(id) ? '<span class="badge done">해냈어요</span>' : ''; }
function seasonalInfo(it, timing) {
  const st = statusOf(it, TODAY);
  let b = '', meta = periodText(it);
  if (it.region !== '전국') meta += ' · ' + it.region;
  if (timing) {
    if (st.state === 'now' && st.daysLeft <= 14) b += '<span class="badge end">곧 끝나요</span>';
    if (st.state === 'soon') b += '<span class="badge soon">곧 시작해요</span>';
    if (st.state === 'now') meta += ' · D-' + st.daysLeft + ' 종료';
    else if (st.state === 'soon') meta += ' · ' + st.daysUntil + '일 뒤 시작';
  }
  const origin = it.category === 'food' && it.origin ? '📍 ' + it.origin : '';
  const spots = it.category === 'nature' && Array.isArray(it.spots) ? it.spots.filter((x) => PLACEBYID[x]) : [];
  return { id: it.id, kind: 'item', emoji: it.emoji, name: it.name, sum: it.summary, meta: [meta], extra: origin || (spots.length ? '명소 ' + spots.length + '곳' : ''),
    badges: b + doneBadge(it.id), state: st.state, d: st.state === 'now' ? st.daysLeft : st.daysUntil, period: periodText(it) };
}
function placeStatus(p) {
  const cur = TODAY.getMonth() + 1;
  if (p.months.includes(cur)) return { state: 'now', d: diffDays(new Date(TODAY.getFullYear(), cur, 0), TODAY) };
  let best = null;
  p.months.forEach((m) => {
    for (let y = TODAY.getFullYear(); y <= TODAY.getFullYear() + 1; y++) {
      const s = new Date(y, m - 1, 1);
      if (s > TODAY && (!best || s < best)) best = s;
    }
  });
  const du = best ? diffDays(best, TODAY) : 999;
  return { state: du <= 14 ? 'soon' : 'later', d: du };
}
function placeInfo(p, timing) {
  const st = placeStatus(p);
  let b = '';
  if (timing && st.state === 'soon') b += '<span class="badge soon">곧 시작해요</span>';
  return { id: p.id, kind: 'place', emoji: '📍', name: p.name, sum: p.summary, meta: [`${p.sido} ${p.sigungu} · ${p.when}`], extra: '',
    badges: b + doneBadge(p.id), state: st.state, d: st.d, period: p.when };
}
function festInfo(f, timing) {
  const s = parseYmd(f.start), e = parseYmd(f.end) || s;
  let state = 'past', d = 0, b = '', tail = '';
  if (s && e) {
    if (e < TODAY) { state = 'past'; tail = '종료'; }
    else if (s <= TODAY) { state = 'now'; d = diffDays(e, TODAY); tail = '진행 중'; if (timing && d <= 7) b += '<span class="badge end">곧 끝나요</span>'; }
    else { d = diffDays(s, TODAY); state = d <= 14 ? 'soon' : 'upcoming'; tail = 'D-' + d; if (timing && d <= 14) b += '<span class="badge soon">곧 시작해요</span>'; }
  }
  const range = s ? (fmtMD(s) + (e && e > s ? ' ~ ' + fmtMD(e) : '')) : '';
  const place = sigungu(f);
  return { id: 'fest-' + f.id, kind: 'fest', emoji: '🎉', thumb: f.image || '', name: f.title, sum: '', meta: [range, [place, tail].filter(Boolean).join(' · ')].filter(Boolean),
    extra: '', badges: b + doneBadge('fest-' + f.id), state, d, period: range };
}
function infoOf(id, timing) {
  const k = kindOf(id);
  if (k === 'fest') { const f = festFor(id); return f ? festInfo(f, timing) : null; }
  if (k === 'place') { const p = PLACEBYID[id]; return p ? placeInfo(p, timing) : null; }
  const it = BYID[id];
  return it ? seasonalInfo(it, timing) : null;
}

// ---------- 공통 조각 ----------
function heartBtn(info, inB) {
  return `<button class="heart" data-heart="${esc(info.id)}" aria-pressed="${inB}" aria-label="${esc(info.name)} ${inB ? '버킷리스트에서 빼기' : '버킷리스트에 담기'}">${inB ? '♥' : '♡'}</button>`;
}
function emBox(info) {
  return info.thumb
    ? `<span class="em thumb"><img src="${esc(info.thumb)}" loading="lazy" alt="" data-fallback="${esc(info.emoji)}"></span>`
    : `<span class="em">${info.emoji}</span>`;
}
function infoCard(info, opt) {
  const o = opt || {};
  const inB = store.bucket.has(info.id);
  return `<div class="card-wrap" style="position:relative"><button class="card" data-open="${esc(info.id)}">
    ${emBox(info)}
    <span class="body"><span class="name">${esc(info.name)} ${info.badges}</span>
    ${o.summary !== false && info.sum ? `<span class="sum" style="display:block">${esc(info.sum)}</span>` : ''}
    <span class="meta">${info.meta.map(esc).join('<br>')}${info.extra ? (info.meta.length ? ' · ' : '') + '<b class="extra">' + esc(info.extra) + '</b>' : ''}</span></span></button>
    ${o.heart === false ? '' : heartBtn(info, inB)}</div>`;
}

// ---------- 화면: 이번 달 ----------
function regionOk(sido) {
  const r = REGIONS.find((x) => x[0] === ui.region);
  return !r || !r[1] || r[1].includes(sido);
}
function festsOfMonth(mo) {
  return FESTS.filter((f) => f._s <= mo.last && f._e >= mo.first && regionOk(f.sido))
    .sort((a, b) => {
      const oa = a._s <= TODAY && a._e >= TODAY ? 0 : 1, ob = b._s <= TODAY && b._e >= TODAY ? 0 : 1;
      return oa - ob || a._s - b._s || a.title.localeCompare(b.title, 'ko');
    });
}
function updatedText() {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(FEST_META.updated || '');
  return m ? +m[1] + '/' + +m[2] : '아직 없음';
}
function viewHome() {
  const months = monthList(), mo = months[ui.mi] || months[0], timing = ui.mi === 0;
  let h = `<div class="chips months" role="group" aria-label="월 선택">` + months.map((x, i) =>
    `<button class="chip mchip" data-month="${i}" aria-pressed="${i === ui.mi}">${esc(monthLabel(x, i))}</button>`).join('') + '</div>';
  h += `<div class="chips regions" role="group" aria-label="지역">` + REGIONS.map(([n]) =>
    `<button class="chip rchip" data-region="${n}" aria-pressed="${n === ui.region}">${n}</button>`).join('') + '</div>';

  // 1. 축제·행사
  const fests = festsOfMonth(mo);
  const events = ITEMS.filter((it) => it.category === 'event' && inMonth(it, mo.m));
  h += `<section data-sec="fest"><h2>🎉 축제·행사 <small>${fests.length}개</small></h2>`;
  if (fests.length) {
    h += fests.slice(0, ui.festLimit).map((f) => infoCard(festInfo(f, timing))).join('');
    if (fests.length > ui.festLimit) h += `<button class="btn ghost block" id="festMore" style="margin-bottom:10px">더 보기 (${fests.length - ui.festLimit}개)</button>`;
  } else {
    const far = mo.first > addDays(TODAY, KEEP_DAYS);
    h += (FESTS.length && !far && ui.region !== '전체')
      ? '<div class="note" data-testid="festEmpty">이 지역에는 이 달에 확인된 축제가 아직 없어요. 다른 지역도 눌러 보세요.</div>'
      : '<div class="note" data-testid="festEmpty">축제 일정은 보통 1~2달 전에 확정돼요. 가까워지면 자동으로 채워져요.</div>';
  }
  if (events.length) h += `<h3 class="subh">절기·세시풍속</h3>` + events.map((it) => infoCard(seasonalInfo(it, timing))).join('');
  h += '</section>';

  // 2. 가볼 만한 곳
  const places = PLACES.filter((p) => p.months.includes(mo.m) && regionOk(p.sido)).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  if (places.length) h += `<section data-sec="place"><h2>📍 가볼 만한 곳 <small>${places.length}곳</small></h2>` + places.map((p) => infoCard(placeInfo(p, timing))).join('') + '</section>';

  // 3. 제철 음식, 4. 자연 (전국)
  const foods = ITEMS.filter((it) => it.category === 'food' && inMonth(it, mo.m));
  const natures = ITEMS.filter((it) => it.category === 'nature' && inMonth(it, mo.m));
  if (foods.length) h += `<section data-sec="food"><h2>🍓 제철 음식 <small>${foods.length}개</small></h2>` + foods.map((it) => infoCard(seasonalInfo(it, timing))).join('') + '</section>';
  if (natures.length) h += `<section data-sec="nature"><h2>🌸 자연 <small>${natures.length}개</small></h2>` + natures.map((it) => infoCard(seasonalInfo(it, timing))).join('') + '</section>';
  h += `<p class="foot" id="festFoot">축제 정보 업데이트: ${esc(updatedText())} · 자료: 한국관광공사</p>`;
  return h;
}

// ---------- 화면: 버킷리스트 ----------
function bucketCard(info) {
  const id = info.id, rec = doneRec(id);
  let h = `<div style="position:relative"><button class="card" data-open="${esc(id)}">
    ${emBox(info)}
    <span class="body"><span class="name">${esc(info.name)} ${info.badges}</span>
    <span class="meta">${info.meta.map(esc).join('<br>')}</span></span></button>
    <button class="heart" data-heart="${esc(id)}" aria-pressed="true" aria-label="${esc(info.name)} 버킷리스트에서 빼기">♥</button>`;
  if (rec) {
    h += `<div class="stampline" style="margin:-4px 0 10px"><span class="stampmark">${esc(rec.date.slice(5).replace('-', '/'))}</span>
      ${rec.photo ? `<img data-photo="${esc(rec.key)}" alt="${esc(info.name)} 사진">` : ''}
      <div class="st"><b>${esc(rec.date)}</b> 해냈어요${rec.memo ? '<br>' + esc(rec.memo) : ''}</div>
      <button class="btn ghost" style="margin-left:auto;min-height:40px;padding:0 12px;font-size:14px" data-undo="${esc(id)}">취소</button></div>`;
  } else {
    h += `<div class="actions" style="margin:-4px 0 12px"><button class="btn" data-done="${esc(id)}">✔ 해냈어요</button></div>`;
  }
  return h + '</div>';
}
function viewBucket() {
  const list = [...store.bucket.keys()].map((id) => infoOf(id, true)).filter(Boolean);
  if (!list.length) return '<div class="empty"><div class="big">🧺</div>아직 담아둔 항목이 없어요.<br>‘이번 달’에서 ♡를 눌러 담아보세요.</div>';
  const by = (st, key) => list.filter((x) => st.includes(x.state)).sort((a, b) => (key === 'left' ? a.d - b.d : a.d - b.d));
  const groups = [
    ['지금 제철·진행 중', by(['now'], 'left')],
    ['곧 시작', by(['soon'])],
    ['예정', by(['upcoming'])],
    ['지난 철', by(['later', 'past'])],
  ];
  return groups.filter((g) => g[1].length).map(([t, l]) => `<h2>${t} <small>${l.length}개</small></h2>` + l.map(bucketCard).join('')).join('');
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
  const visited = [...recs.values()].filter((r) => kindOf(r.id) !== 'item').sort((a, b) => a.date.localeCompare(b.date));
  h += `<section class="board visited" data-visited-board="1"><h3>다녀온 곳 <span class="prog">${visited.length}곳</span></h3>`;
  h += visited.length
    ? '<div class="grid">' + visited.map((r) => {
      const info = infoOf(r.id, false), nm = info ? info.name : (r.title || r.id), em = info ? info.emoji : (kindOf(r.id) === 'fest' ? '🎉' : '📍');
      return `<button class="stamp on" data-open="${esc(r.id)}" aria-label="${esc(nm)} 도장 찍음"><span class="circ">${em}</span><span class="nm">${esc(nm)}</span></button>`;
    }).join('') + '</div>'
    : '<div class="empty" style="padding:14px 6px">아직 다녀온 곳이 없어요.<br>명소나 축제에서 ‘해냈어요’를 눌러 보세요.</div>';
  h += '</section>';
  h += `<button class="btn block" id="makeCard" style="margin-top:8px">🎴 올해의 제철 카드 만들기</button>`;
  return h;
}

// ---------- 화면: 알림 ----------
const FEST_ALERT_DAYS = 3;
function alertList() {
  const out = [];
  store.bucket.forEach((b) => {
    const info = infoOf(b.id, false); if (!info) return;
    const done = !!doneRec(b.id);
    if (info.kind === 'item') {
      if (info.state === 'now' && info.d <= 14 && !done) out.push({ info, kind: 'end', d: info.d });
      else if (info.state === 'soon') out.push({ info, kind: 'start', d: info.d });
    } else if (info.kind === 'fest') {
      if (info.state === 'now' && info.d <= FEST_ALERT_DAYS && !done) out.push({ info, kind: 'end', d: info.d });
      else if (info.state === 'soon' && info.d <= FEST_ALERT_DAYS) out.push({ info, kind: 'start', d: info.d });
    }
  });
  return out.sort((a, b) => a.d - b.d);
}
const dtxt = (d) => (d === 0 ? 'D-day' : 'D-' + d);
function alertMsg(a) { return `담아둔 '${a.info.name}'가 ${a.kind === 'end' ? '곧 끝나요' : '곧 시작해요'}`; }
function viewAlerts() {
  const list = alertList();
  const on = !!lsGet('notifyOnOpen', false);
  const canNotify = 'Notification' in window; // Android WebView 에는 Notification 이 없음
  let h = `<div class="toggle"><div><b>앱을 열 때 알림 보내기</b><div style="font-size:13px;color:var(--sub)">${canNotify ? '담아둔 항목이 곧 끝나거나 시작하면 알려줘요' : '앱에서는 지원하지 않아요'}</div></div>
    <button class="switch" id="notifySwitch" role="switch" aria-checked="${on && canNotify}" aria-label="앱을 열 때 알림 보내기"${canNotify ? '' : ' disabled style="opacity:.4"'}></button></div>
    <div class="note" id="notifyNote">ℹ️ 이 버전에서는 앱을 열지 않은 상태의 백그라운드 푸시 알림은 지원하지 않아요. 앱을 열 때만 알림을 보내드려요.</div>`;
  h += `<h2>곧 확인할 항목 <small>제철 14일 · 축제 3일 안</small></h2>`;
  h += list.length ? list.map((a) => `<button class="alert ${a.kind}" data-open="${esc(a.info.id)}" style="width:100%;text-align:left">
      <span class="em">${a.info.emoji}</span><span>${a.kind === 'end' ? `담아둔 '${esc(a.info.name)}'가 곧 끝나요` : `담아둔 '${esc(a.info.name)}'가 곧 시작해요`}</span>
      <span class="dd">· ${dtxt(a.d)}</span></button>`).join('')
    : '<div class="empty"><div class="big">🔕</div>곧 시작하거나 끝나는 담아둔 항목이 없어요</div>';
  return h;
}
async function notifyOnOpen() {
  try {
    if (!lsGet('notifyOnOpen', false) || !('Notification' in window) || Notification.permission !== 'granted') return;
    const sent = lsGet('notifiedLog', {});
    const today = ymd(TODAY);
    const list = alertList().filter((a) => sent[a.info.id] !== today);
    if (!list.length) return;
    let reg = null;
    try { reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : null; } catch (e) {}
    for (const a of list) {
      const opts = { body: `${dtxt(a.d)} · ${a.info.period}`, icon: 'icons/icon-192.png', tag: 'cheolttara-' + a.info.id };
      try {
        if (reg && reg.showNotification) await reg.showNotification(alertMsg(a), opts);
        else new Notification(alertMsg(a), opts);
        sent[a.info.id] = today;
      } catch (e) {}
    }
    lsSet('notifiedLog', sent);
  } catch (e) {}
}
async function toggleNotify() {
  const on = !!lsGet('notifyOnOpen', false);
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
const naverMap = (q) => 'https://map.naver.com/p/search/' + encodeURIComponent(q);
const mapBtn = (q) => `<a class="btn ghost" id="sheetMap" href="${esc(naverMap(q))}" target="_blank" rel="noopener noreferrer">🗺️ 지도 보기</a>`;
const row = (label, html) => (html ? `<div class="row"><b>${esc(label)}</b>${html}</div>` : '');
const tipRow = (tip) => (tip ? `<div class="row tipbox"><b>즐기는 팁</b>${esc(tip)}</div>` : '');
// 공통 시트 틀: 제목·본문·도장 표시·담기/해냈어요/닫기
function entrySheet(info, body, mapHtml, credit) {
  const id = info.id, inB = store.bucket.has(id), rec = doneRec(id);
  const o = openSheet(`<div style="display:flex;gap:14px;align-items:center"><span class="big">${info.emoji}</span><div><h3>${esc(info.name)}</h3>
    <div>${info.badges}</div></div></div>${body}
    ${rec ? `<div class="stampline"><span class="stampmark">${esc(rec.date.slice(5).replace('-', '/'))}</span>${rec.photo ? `<img data-photo="${esc(rec.key)}" alt="">` : ''}<div class="st"><b>${esc(rec.date)}</b> 해냈어요${rec.memo ? '<br>' + esc(rec.memo) : ''}</div></div>` : ''}
    <div class="actions"><button class="btn${inB ? ' ghost' : ''}" id="sheetHeart">${inB ? '♥ 담았어요 (빼기)' : '♡ 버킷리스트에 담기'}</button>
    ${rec ? '' : '<button class="btn ghost" id="sheetDone">✔ 해냈어요</button>'}
    ${mapHtml || ''}
    <button class="btn ghost" id="sheetClose">닫기</button></div>${credit ? `<p class="foot" style="text-align:left">${esc(credit)}</p>` : ''}`);
  hydratePhotos(o);
  $('#sheetHeart').onclick = () => { setBucket(id, !inB); render(); detailSheet(id); };
  const d = $('#sheetDone'); if (d) d.onclick = () => doneSheet(id);
  $('#sheetClose').onclick = closeSheet;
}
function telRow(tel) {
  if (!tel) return '';
  const m = /\+?[\d][\d\- ]{5,}/.exec(tel);
  const num = m ? m[0].trim().replace(/[^\d+\-]/g, '') : '';
  return row('전화', esc(tel) + (num ? ` · <a href="tel:${esc(num)}">전화 걸기</a>` : ''));
}
function festSheet(id) {
  const f = festFor(id); if (!f) return;
  const info = festInfo(f, true), s = parseYmd(f.start), e = parseYmd(f.end);
  const range = s ? f.start + (e && f.end !== f.start ? ' ~ ' + f.end : '') : '';
  const body = (f.image ? `<img class="hero" src="${esc(f.image)}" loading="lazy" alt="" data-fallback="">` : '') +
    row('기간', esc(range) + (info.state === 'now' ? ' · 진행 중' : info.state === 'past' ? ' · 종료' : s ? ' · D-' + info.d : '')) +
    row('주소', esc(f.addr)) + telRow(f.tel);
  entrySheet(info, body, mapBtn(f.title), '자료: 한국관광공사');
}
function placeSheet(id) {
  const p = PLACEBYID[id]; if (!p) return;
  const info = placeInfo(p, true);
  const rel = (p.related || []).map((r) => BYID[r]).filter(Boolean);
  const body = row('가기 좋은 때', esc(p.when) + ' · ' + esc(p.sido + ' ' + p.sigungu)) + row('소개', esc(p.summary)) + tipRow(p.tip) +
    (rel.length ? `<div class="row"><b>관련 제철</b><div class="chiprow">${rel.map((r) => `<button class="chip" data-open="${esc(r.id)}">${r.emoji} ${esc(r.name)}</button>`).join('')}</div></div>` : '');
  entrySheet(info, body, mapBtn(p.name + ' ' + p.sigungu));
}
function itemSheet(id) {
  const it = BYID[id]; if (!it) return;
  const info = seasonalInfo(it, true), st = statusOf(it, TODAY);
  const when = st.state === 'now' ? `지금 제철 · 종료까지 D-${st.daysLeft}` : st.state === 'soon' ? `${st.daysUntil}일 뒤 시작` : '지금은 철이 아니에요';
  const spots = it.category === 'nature' && Array.isArray(it.spots) ? it.spots.map((x) => PLACEBYID[x]).filter(Boolean) : [];
  const body = `<div class="row"><b>${esc(CATS[it.category] || '')} · ${esc(it.subcategory)}</b>${esc(it.summary)}</div>
    <div class="row"><b>시기</b>${esc(periodText(it))} (${esc(it.region)}) · ${when}</div>` +
    (it.category === 'food' && it.origin ? row('유명 산지', '📍 ' + esc(it.origin)) : '') +
    (it.category === 'food' && Array.isArray(it.dishes) && it.dishes.length ? `<div class="row"><b>추천 요리</b><div class="chiprow">${it.dishes.map((d) => `<span class="tag">🍽️ ${esc(d)}</span>`).join('')}</div></div>` : '') +
    tipRow(it.tip) +
    (spots.length ? `<div class="row"><b>가볼 만한 명소</b></div>` + spots.map((p) => infoCard(placeInfo(p, false), { heart: false })).join('') : '');
  entrySheet(info, body);
}
function detailSheet(id) {
  const k = kindOf(id);
  if (k === 'fest') festSheet(id); else if (k === 'place') placeSheet(id); else itemSheet(id);
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
  const info = infoOf(id, false); if (!info) return;
  const o = openSheet(`<h3>${info.emoji} ${esc(info.name)} 해냈어요!</h3>
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
    const rec = { key: recKey(id, YEAR), id, year: YEAR, date: ymd(TODAY), memo, photo };
    if (info.kind !== 'item') rec.title = info.name; // 축제·명소는 이름도 함께 저장
    const ok = await putRecord(rec);
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
  const recs = [...store.records.values()].filter((r) => r.year === year && (BYID[r.id] || kindOf(r.id) !== 'item'))
    .sort((a, b) => a.date.localeCompare(b.date));
  const recEmoji = (r) => (BYID[r.id] ? BYID[r.id].emoji : kindOf(r.id) === 'fest' ? '🎉' : '📍');
  const seasonalDone = recs.filter((r) => BYID[r.id]).length, visitedN = recs.length - seasonalDone;
  g.fillStyle = '#fbf8f3'; g.fillRect(0, 0, W, H);
  g.fillStyle = acc; g.fillRect(0, 0, W, 14);
  g.strokeStyle = acc; g.lineWidth = 6; g.globalAlpha = .35; g.strokeRect(36, 36, W - 72, H - 72); g.globalAlpha = 1;
  g.textAlign = 'center'; g.textBaseline = 'alphabetic';
  g.fillStyle = acc; g.font = `800 96px ${TEXT_FONT}`; g.fillText('철따라', W / 2, 180);
  g.fillStyle = '#2b2622'; g.font = `700 56px ${TEXT_FONT}`; g.fillText(`${year}년 나의 제철 카드`, W / 2, 262);
  g.font = `600 44px ${TEXT_FONT}`; g.fillStyle = acc;
  g.fillText(`제철 도장 ${seasonalDone}개 / ${ITEMS.length}개`, W / 2, 332);
  if (visitedN) { g.font = `600 36px ${TEXT_FONT}`; g.fillStyle = '#7a7068'; g.fillText(`다녀온 곳 ${visitedN}곳`, W / 2, 382); }
  // 이모지 격자
  const emojis = recs.map(recEmoji).slice(0, 40);
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
    if (window.CheolttaraAndroid && typeof window.CheolttaraAndroid.saveImage === 'function') { // Android 앱: 갤러리에 저장 (토스트는 앱이 띄움)
      try { window.CheolttaraAndroid.saveImage(canvas.toDataURL('image/png').split(',')[1], `철따라-${ui.year}.png`); } catch (e) { toast('이미지를 저장하지 못했어요'); }
      return;
    }
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
const TITLES = { home: '이번 달', bucket: '내 버킷리스트', stamps: '도장판', alerts: '알림' };
function render() {
  const season = seasonOfMonth(TODAY.getMonth() + 1);
  document.body.dataset.season = season;
  document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === ui.tab)));
  $('#title').textContent = ui.tab === 'home' ? '철따라' : TITLES[ui.tab];
  $('#subtitle').textContent = ui.tab === 'home' ? `${TODAY.getMonth() + 1}월 ${TODAY.getDate()}일 · ${SEASONS.find((s) => s.id === season).name}, 지금 이 철에 담아요` : '철따라';
  const v = $('#view');
  v.innerHTML = { home: viewHome, bucket: viewBucket, stamps: viewStamps, alerts: viewAlerts }[ui.tab]();
  hydratePhotos(v);
  if (ui.tab === 'home') { // 선택한 월이 보이도록 띠 가로 위치 맞추기
    const strip = $('.months', v), sel = strip && $('[aria-pressed=true]', strip);
    if (sel) strip.scrollLeft = Math.max(0, sel.offsetLeft - strip.clientWidth / 2 + sel.offsetWidth / 2);
    const rs = $('.regions', v), rsel = rs && $('[aria-pressed=true]', rs);
    if (rsel) rs.scrollLeft = Math.max(0, rsel.offsetLeft - rs.clientWidth / 2 + rsel.offsetWidth / 2);
  }
  $('#alertDot').hidden = alertList().length === 0;
}
function bind() {
  document.addEventListener('click', (e) => {
    const t = e.target.closest('button,select'); if (!t) return;
    const d = t.dataset;
    if (d.tab) { ui.tab = d.tab; closeSheet(); render(); window.scrollTo(0, 0); }
    else if (d.month !== undefined) { ui.mi = +d.month; ui.festLimit = FEST_PAGE; render(); }
    else if (d.region) { ui.region = d.region; lsSet('region', d.region); ui.festLimit = FEST_PAGE; render(); }
    else if (t.id === 'festMore') { ui.festLimit += FEST_PAGE; render(); }
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
  // 외부 이미지 로딩 실패 시 자리표시 (error 이벤트는 버블링되지 않아 capture 로 받는다)
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (!img || img.tagName !== 'IMG' || img.dataset.fallback === undefined) return;
    const fb = img.dataset.fallback, p = img.parentNode;
    if (fb && p) p.textContent = fb; else img.remove();
  }, true);
}
async function loadJson(url, def) {
  try {
    const res = await fetch(url);
    if (!res.ok) return def;
    return await res.json();
  } catch (e) { return def; }
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
  // 명소·축제는 없어도 앱이 동작해야 한다
  const places = await loadJson('data/places.json', []);
  PLACES = (Array.isArray(places) ? places : []).filter((p) => p && p.id && Array.isArray(p.months));
  PLACEBYID = Object.fromEntries(PLACES.map((p) => [p.id, p]));
  const fj = await loadJson('data/festivals.json', {});
  FEST_META = { updated: (fj && fj.updated) || null, source: (fj && fj.source) || '' };
  FESTS = ((fj && Array.isArray(fj.items)) ? fj.items : []).map((f) => ({ ...f, _s: parseYmd(f.start), _e: parseYmd(f.end) || parseYmd(f.start) }))
    .filter((f) => f && f.id && f.title && f._s);
  FESTBYID = Object.fromEntries(FESTS.map((f) => [String(f.id), f]));
  const savedRegion = lsGet('region', '전체');
  if (REGIONS.some((r) => r[0] === savedRegion)) ui.region = savedRegion;
  await initStore();
  render();
  document.body.dataset.ready = '1';
  if (!store.persistent) toast('저장소를 쓸 수 없어 이번 방문에만 기억해요');
  notifyOnOpen();
  try { if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {}); } catch (e) {}
}
init();

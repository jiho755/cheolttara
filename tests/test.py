"""철따라 v2 UI 테스트 (Playwright, 390x844). 실행: python3 tests/test.py

- 저장소를 임시 폴더로 복사하고, tests/fixtures 로 scripts/fetch_festivals.py 를 돌려 만든 축제 데이터를 넣어 서빙한다 (포트 8765).
- 커밋된 data/festivals.json(빈 초기값)은 원본 폴더 그대로 8766 으로 서빙해 '축제 없음' 상태를 확인한다.
- 끝나면 원본 data/festivals.json 이 바뀌지 않았는지 확인한다.
"""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'screens') + '/'
os.makedirs(OUT, exist_ok=True)
FEST_PATH = os.path.join(ROOT, 'data', 'festivals.json')
EMPTY_FESTIVALS = {"updated": None, "source": "한국관광공사 TourAPI", "items": []}
with open(FEST_PATH, encoding='utf-8') as f:
    ORIGINAL_FEST = f.read()

# ---- 임시 사본 + 픽스처로 축제 데이터 생성
TMP = tempfile.mkdtemp(prefix='cheolttara-test-')
SITE = os.path.join(TMP, 'site')
shutil.copytree(ROOT, SITE, ignore=shutil.ignore_patterns('.git', 'screens', '__pycache__', 'tests', 'docs'))
FIX = os.path.join(ROOT, 'tests', 'fixtures')
rc = subprocess.call([sys.executable, '-I', os.path.join(ROOT, 'scripts', 'fetch_festivals.py'),
                      '--fixture', os.path.join(FIX, 'searchFestival2_page1.json'), os.path.join(FIX, 'searchFestival2_page2.json'),
                      '--today', '2026-11-24', '--out', os.path.join(SITE, 'data', 'festivals.json')])
assert rc == 0, 'fixture festivals generation failed'
with open(os.path.join(SITE, 'data', 'festivals.json'), encoding='utf-8') as f:
    FEST = json.load(f)
assert len(FEST['items']) == 17

A = 'http://localhost:8765/'   # 축제 데이터 있음
B = 'http://localhost:8766/'   # 원본 (축제 비어 있음)
srvs = [subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '-d', d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for port, d in ((8765, SITE), (8766, ROOT))]
time.sleep(1)

results = []
def check(name, cond, extra=''):
    results.append((name, bool(cond), extra)); print(('PASS' if cond else 'FAIL'), name, extra)

buf = io.BytesIO(); Image.new('RGB', (80, 80), (230, 150, 120)).save(buf, 'PNG'); PNG = buf.getvalue()
def image_route(route):
    if '141002' in route.request.url:   # 일부러 깨진 이미지 -> 자리표시 확인
        route.fulfill(status=200, content_type='image/png', body=b'not-an-image')
    else:
        route.fulfill(status=200, content_type='image/png', body=PNG)

def new_page(b, base, date, tag=None, route_items=None):
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, locale='ko-KR')
    ctx.grant_permissions(['notifications'])
    ctx.route('https://tong.visitkorea.or.kr/**', image_route)
    pg = ctx.new_page(); errs = []
    pg.on('console', lambda m, e=errs: e.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda x, e=errs: e.append(str(x)))
    if route_items:
        def h(route):
            data = route.fetch().json(); route_items(data); route.fulfill(json=data)
        pg.route('**/data/seasonal_items.json', h)
    url = f'{base}?date={date}'
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]')
    return ctx, pg, errs, url

def names(pg, sec):
    sel = '[data-open^="fest-"]' if sec == 'fest' else ''
    return pg.locator(f'[data-sec={sec}] .card{sel} .name').evaluate_all(
        "els=>els.map(e=>[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim())")
def open_ids(pg):
    return pg.locator('#view .card[data-open]').evaluate_all('els=>els.map(e=>e.dataset.open)')

try:
  with sync_playwright() as p:
    b = p.chromium.launch()

    # ============ 날짜별 기본 흐름 (v1 흐름 + v2 월 보기) ============
    for date in ['2026-11-24', '2026-04-05', '2026-07-20']:
        tag = date
        ctx, pg, errs, url = new_page(b, A, date)
        # --- 월 띠
        nm = pg.locator('[data-month]').count(); check(f'{tag} month strip 12', nm == 12, str(nm))
        labels = pg.locator('[data-month]').all_inner_texts()
        cur = int(date[5:7])
        check(f'{tag} first month = this month, selected', labels[0] == f'{cur}월' and pg.get_attribute('[data-month="0"]', 'aria-pressed') == 'true', str(labels))
        if cur >= 2:
            check(f'{tag} year marker on January', any('1월 ’' in l for l in labels), str(labels))
        check(f'{tag} home sections', all(pg.locator(f'[data-sec={s}]').count() == 1 for s in ('fest', 'food', 'nature')))
        check(f'{tag} bottom tab 이번 달', pg.locator('.tab[data-tab=home]').inner_text().strip().endswith('이번 달'))
        before = open_ids(pg)
        check(f'{tag} home items render', len(before) > 0, f'{len(before)} cards')
        pg.screenshot(path=OUT + f'{tag}_1home.png', full_page=True)
        pg.click('[data-month="4"]')
        after = open_ids(pg)
        check(f'{tag} switching month changes sections', pg.get_attribute('[data-month="4"]', 'aria-pressed') == 'true' and after != before, f'{len(before)}->{len(after)}')
        pg.screenshot(path=OUT + f'{tag}_1home_month5.png')
        pg.click('[data-month="0"]')
        check(f'{tag} timing badge only on this month', pg.locator('.badge.end,.badge.soon').count() > 0 if date == '2026-04-05' else True)
        pg.click('[data-month="3"]'); check(f'{tag} no timing badges on other month', pg.locator('#view .badge.end, #view .badge.soon').count() == 0)
        pg.click('[data-month="0"]')
        # --- 상세 시트
        first = pg.locator('[data-sec=food] .card[data-open]').first
        iid = first.get_attribute('data-open')
        first.click(); pg.wait_for_selector('.sheet')
        check(f'{tag} detail sheet tip', pg.locator('.tipbox').count() == 1)
        pg.wait_for_timeout(300); pg.screenshot(path=OUT + f'{tag}_2detail.png')
        pg.click('#sheetHeart'); pg.click('#sheetClose')
        h2 = pg.locator('[data-sec=nature] [data-heart]').first; h2.click()
        pg.click('[data-tab=bucket]')
        nb = pg.locator('#view .card').count(); check(f'{tag} bucket has 2', nb == 2, str(nb))
        pg.screenshot(path=OUT + f'{tag}_3bucket.png')
        pg.click(f'[data-done="{iid}"]'); pg.wait_for_selector('#doneSave')
        pg.fill('#memoIn', '맛있었다 ' + '가' * 60)
        v = pg.input_value('#memoIn'); check(f'{tag} memo max 50', len(v) == 50, str(len(v)))
        pg.wait_for_timeout(300); pg.screenshot(path=OUT + f'{tag}_4donesheet.png')
        pg.click('#doneSave'); pg.wait_for_selector('.stampline')
        check(f'{tag} done stamp shown', pg.locator(f'[data-undo="{iid}"]').count() == 1)
        pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
        check(f'{tag} persists after reload', pg.locator(f'[data-undo="{iid}"]').count() == 1 and pg.locator('#view .card').count() == 2)
        # --- 도장판
        pg.click('[data-tab=stamps]')
        check(f'{tag} 4 season boards', pg.locator('[data-season-board]').count() == 4)
        on = pg.locator('[data-season-board] .stamp.on').count(); check(f'{tag} stamp on season board', on == 1, str(on))
        progs = pg.locator('[data-season-board] .prog').all_inner_texts()
        check(f'{tag} progress format', all('/' in t for t in progs) and any(t.split()[1].startswith('1/') for t in progs), str(progs))
        total = sum(int(t.split('/')[1]) for t in progs); check(f'{tag} boards cover 100', total == 100, str(total))
        check(f'{tag} 다녀온 곳 board', '다녀온 곳' in pg.locator('[data-visited-board]').inner_text())
        pg.screenshot(path=OUT + f'{tag}_6stamps.png', full_page=True)
        pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]')
        info = pg.evaluate("()=>{const c=document.querySelector('#cardOut');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let nb=0;for(let i=0;i<d.length;i+=4*97){if(d[i]!==251||d[i+1]!==248)nb++}return [c.width,c.height,nb]}")
        check(f'{tag} share card 1080x1350 drawn', info[0] == 1080 and info[1] == 1350 and info[2] > 50, str(info))
        data = pg.evaluate("()=>document.querySelector('#cardOut').toDataURL('image/png')")
        open(OUT + f'{tag}_7card.png', 'wb').write(base64.b64decode(data.split(',')[1]))
        with pg.expect_download() as dl: pg.click('#cardShare')
        check(f'{tag} card download fallback', dl.value.suggested_filename.endswith('.png'))
        pg.click('#cardClose')
        pg.click('[data-tab=alerts]'); pg.screenshot(path=OUT + f'{tag}_8alerts.png')
        check(f'{tag} alerts note', pg.locator('#notifyNote').inner_text().find('백그라운드') >= 0)
        pg.click('#notifySwitch'); pg.wait_for_timeout(500)
        check(f'{tag} notify denied -> stays off', pg.get_attribute('#notifySwitch', 'aria-checked') == 'false')
        pg.click('[data-tab=bucket]'); pg.click(f'[data-undo="{iid}"]')
        check(f'{tag} undo works', pg.locator(f'[data-done="{iid}"]').count() == 1)
        check(f'{tag} no console errors', not errs, str(errs))
        ctx.close()

    # ============ 11/24: 축제·지역·명소·시트·버킷·도장 ============
    ctx, pg, errs, url = new_page(b, A, '2026-11-24')
    nov = names(pg, 'fest')
    check('11/24 festivals in Nov = 5', len(nov) == 5, str(nov))
    check('11/24 ongoing first, then by start', nov[0] in ('인천 차이나타운 겨울 거리', '대구 빛 축제') and nov[-1] in ('부산 불꽃 크리스마스', '춘천 눈꽃 마을 축제'), str(nov))
    check('11/24 한 festival badge 곧 끝나요 (ends in 4 days)', pg.locator('[data-open="fest-141002"] .badge.end').count() == 1)
    check('11/24 festival footer', '축제 정보 업데이트: ' in pg.inner_text('#festFoot') and '한국관광공사' in pg.inner_text('#festFoot'), pg.inner_text('#festFoot'))
    check('11/24 절기·세시풍속 subheading', pg.locator('[data-sec=fest] .subh:has-text("절기·세시풍속")').count() == 1)
    pg.wait_for_timeout(300)
    em = pg.locator('[data-open="fest-141002"] .em').inner_text().strip()
    check('11/24 broken thumbnail -> 🎉 placeholder', em == '🎉', em)
    check('11/24 thumbnail img for good image', pg.locator('[data-open="fest-141001"] .em img').count() == 1)
    pg.screenshot(path=OUT + 'v2_festival_home.png', full_page=True)
    # 지역 칩
    pg.click('[data-region="강원"]')
    check('region 강원: festivals filtered', names(pg, 'fest') == ['춘천 눈꽃 마을 축제'], str(names(pg, 'fest')))
    pl = names(pg, 'place'); check('region 강원: places filtered', '철원 평야 철새지' in pl and '내장산 단풍' not in pl, str(pl))
    fo = pg.locator('[data-sec=food] .card').count(); check('region does not filter food', fo > 0)
    pg.screenshot(path=OUT + 'v2_region_gangwon.png')
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]')
    check('region persisted after reload', pg.get_attribute('[data-region="강원"]', 'aria-pressed') == 'true' and names(pg, 'fest') == ['춘천 눈꽃 마을 축제'])
    pg.click('[data-region="수도권"]')
    check('region 수도권', sorted(names(pg, 'fest')) == sorted(['서울빛초롱축제', '인천 차이나타운 겨울 거리']), str(names(pg, 'fest')))
    pg.click('[data-region="제주"]')
    check('region 제주 empty-festival message in Nov', '이 지역' in pg.inner_text('[data-testid=festEmpty]'))
    pg.click('[data-region="전체"]')
    # 12월: 더 보기
    pg.click('[data-month="1"]')
    c1 = pg.locator('[data-sec=fest] .card').count()
    check('Dec: first 10 + 더 보기', pg.locator('[data-sec=fest] .card[data-open^="fest-"]').count() == 10 and pg.locator('#festMore').count() == 1, str(c1))
    pg.click('#festMore')
    check('Dec: 더 보기 shows rest', pg.locator('#festMore').count() == 0 and pg.locator('[data-sec=fest] .card[data-open^="fest-"]').count() == 11, str(pg.locator('[data-sec=fest] .card[data-open^="fest-"]').count()))
    pg.click('[data-month="0"]')
    # 축제 시트
    pg.click('[data-open="fest-141001"]'); pg.wait_for_selector('.sheet')
    link = pg.locator('.sheet a#sheetMap')
    href = link.get_attribute('href')
    check('festival sheet 지도 보기 → naver map', href == 'https://map.naver.com/p/search/' + urllib.parse.quote('서울빛초롱축제', safe=''), href)
    check('festival sheet link opens new tab', link.get_attribute('target') == '_blank')
    st = pg.inner_text('.sheet')
    check('festival sheet fields', '2026-11-06 ~ 2026-12-05' in st and '서울특별시 종로구' in st and '02-123-4567' in st and '한국관광공사' in st)
    check('festival sheet tel link', pg.locator('.sheet a[href="tel:02-123-4567"]').count() == 1)
    check('festival sheet image', pg.locator('.sheet img.hero').count() == 1)
    pg.wait_for_timeout(300); pg.screenshot(path=OUT + 'v2_festival_sheet.png')
    pg.click('#sheetClose')
    pg.click('[data-open="fest-141002"]'); pg.wait_for_selector('.sheet'); pg.wait_for_timeout(300)
    check('festival sheet broken hero image removed', pg.locator('.sheet img.hero').count() == 0)
    pg.click('#sheetClose')
    # 명소 시트
    pcard = pg.locator('[data-sec=place] .card[data-open]').first
    pid = pcard.get_attribute('data-open'); pcard.click(); pg.wait_for_selector('.sheet')
    plink = pg.get_attribute('.sheet a#sheetMap', 'href')
    check('place sheet works (tip + naver link)', pg.locator('.tipbox').count() == 1 and plink.startswith('https://map.naver.com/p/search/'), plink)
    pg.wait_for_timeout(300); pg.screenshot(path=OUT + 'v2_place_sheet.png')
    chips = pg.locator('.sheet .chiprow [data-open]')
    if chips.count():
        cid = chips.first.get_attribute('data-open'); chips.first.click(); pg.wait_for_selector('.sheet')
        check('place related chip opens item sheet', pg.locator('.sheet h3').inner_text().strip() == pg.evaluate(f"BYID['{cid}'].name"))
    pg.click('#sheetClose')
    # 버킷: 축제 + 명소, 도장
    pg.click('[data-open="fest-141001"]'); pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.locator(f'[data-heart="{pid}"]').first.click()
    pg.click('[data-tab=bucket]')
    check('bucket has festival + place', pg.locator('#view .card').count() == 2 and pg.locator('[data-open="fest-141001"]').count() == 1 and pg.locator(f'[data-open="{pid}"]').count() == 1)
    pg.screenshot(path=OUT + 'v2_bucket.png')
    for sid in ('fest-141001', pid):
        pg.click(f'[data-done="{sid}"]'); pg.wait_for_selector('#doneSave'); pg.fill('#memoIn', '다녀왔어요'); pg.click('#doneSave'); pg.wait_for_selector(f'[data-undo="{sid}"]')
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
    check('festival + place bucket & stamps persist after reload', pg.locator('[data-undo]').count() == 2 and pg.locator('#view .card').count() == 2)
    stored = pg.evaluate("async()=>{const o=await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const g=q.result.transaction('bucket').objectStore('bucket').getAll();g.onsuccess=()=>res(g.result)}});return o.find(x=>x.id==='fest-141001')}")
    check('festival bucket stores title/start/end/addr', stored and stored.get('title') == '서울빛초롱축제' and stored.get('start') == '2026-11-06' and stored.get('end') == '2026-12-05' and '종로구' in stored.get('addr', ''), str(stored))
    pg.click('[data-tab=stamps]')
    vb = pg.locator('[data-visited-board]')
    check('도장판 shows 다녀온 곳 with 2 stamps', '다녀온 곳' in vb.inner_text() and vb.locator('.stamp.on').count() == 2 and '2곳' in vb.inner_text(), vb.inner_text().replace('\n', ' '))
    check('season boards unaffected by visited stamps', pg.locator('[data-season-board] .stamp.on').count() == 0)
    pg.evaluate('window.scrollTo(0,document.body.scrollHeight)'); pg.screenshot(path=OUT + 'v2_stamps_visited.png')
    pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]'); pg.screenshot(path=OUT + 'v2_card.png'); pg.click('#cardClose')
    check('11/24 no console errors (festival flow)', not errs, str(errs))
    ctx.close()

    # ============ 축제 알림 (시작 3일 전 / 종료 3일 전) ============
    ctx, pg, errs, url = new_page(b, A, '2026-11-26')   # 춘천 눈꽃(141002) 11/28 종료 → D-2
    pg.click('[data-heart="fest-141002"]'); pg.click('[data-tab=alerts]')
    t = pg.locator('.alert.end').all_inner_texts()
    check('festival end alert (D-2)', len(t) == 1 and '곧 끝나요' in t[0] and 'D-2' in t[0], str(t))
    check('alert dot shown', not pg.locator('#alertDot').is_hidden())
    pg.click('.alert.end'); pg.wait_for_selector('.sheet'); check('alert opens festival sheet', pg.locator('#sheetMap').count() == 1)
    ctx.close()
    ctx, pg, errs, url = new_page(b, A, '2026-11-30')   # 전주 한지(141003) 12/03 시작 → D-3, 수원(141004) 12/01 → D-1
    pg.click('[data-open="fest-141003"]') if pg.locator('[data-open="fest-141003"]').count() else (pg.click('[data-month="1"]'), pg.click('[data-open="fest-141003"]'))
    pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.click('[data-tab=alerts]'); t = pg.locator('.alert.start').all_inner_texts()
    check('festival start alert (D-3)', len(t) == 1 and '곧 시작해요' in t[0] and 'D-3' in t[0], str(t))
    ctx.close()
    ctx, pg, errs, url = new_page(b, A, '2026-11-24')   # 시작까지 7일(12/03) → 알림 없음
    pg.click('[data-month="1"]'); pg.click('[data-heart="fest-141003"]'); pg.click('[data-tab=alerts]')
    check('festival not alerted when start > 3 days away', pg.locator('.alert').count() == 0)
    ctx.close()

    # ============ 축제 비어 있음 (커밋된 초기 데이터) ============
    ctx, pg, errs, url = new_page(b, B, '2026-11-24')
    msg = pg.inner_text('[data-testid=festEmpty]')
    check('empty festivals → guidance message', '축제 일정은 보통 1~2달 전에 확정돼요' in msg, msg)
    check('empty festivals: other sections still render', pg.locator('[data-sec=food] .card').count() > 0 and pg.locator('[data-sec=place] .card').count() > 0)
    check('empty festivals: footer', '아직 없음' in pg.inner_text('#festFoot'))
    pg.click('[data-month="11"]'); check('empty festivals: far month message', pg.locator('[data-testid=festEmpty]').count() == 1)
    pg.screenshot(path=OUT + 'v2_empty_festivals.png')
    check('no console errors (empty festivals)', not errs, str(errs))
    ctx.close()
    # 축제 있어도 수집 범위 밖 달: 04-05 기준 4월은 축제 없음 → 안내 문구
    ctx, pg, errs, url = new_page(b, A, '2026-04-05')
    check('month without festivals → guidance message (04-05)', pg.locator('[data-testid=festEmpty]').count() == 1)
    ctx.close()

    # ============ 데이터 확장 필드 (origin/dishes/spots) 표시 & 없을 때 허용 ============
    def inject(items):
        for it in items:
            if it['category'] == 'food':
                it['origin'] = '포항 구룡포'; it['dishes'] = ['과메기 쌈', '과메기 무침']
            if it['category'] == 'nature':
                it['spots'] = ['place-naejangsan', 'place-없는곳']
    ctx, pg, errs, url = new_page(b, A, '2026-11-24', route_items=inject)
    check('food card shows origin', '📍 포항 구룡포' in pg.locator('[data-sec=food] .card').first.inner_text())
    check('nature card shows 명소 N곳 (unknown ids ignored)', '명소 1곳' in pg.locator('[data-sec=nature] .card').first.inner_text())
    pg.locator('[data-sec=food] .card[data-open]').first.click(); pg.wait_for_selector('.sheet')
    s = pg.inner_text('.sheet'); check('food sheet origin + dishes', '포항 구룡포' in s and '과메기 쌈' in s and '과메기 무침' in s)
    pg.click('#sheetClose')
    pg.locator('[data-sec=nature] .card[data-open]').first.click(); pg.wait_for_selector('.sheet')
    check('nature sheet shows spot card', pg.locator('.sheet .card[data-open="place-naejangsan"]').count() == 1)
    pg.click('.sheet .card[data-open="place-naejangsan"]'); pg.wait_for_selector('.sheet #sheetMap')
    check('spot card opens place sheet', '내장산' in pg.inner_text('.sheet h3'))
    pg.screenshot(path=OUT + 'v2_spot_sheet.png')
    check('no console errors (extended fields)', not errs, str(errs))
    ctx.close()

    # ============ v1 저장 데이터 호환 ============
    ctx, pg, errs, url = new_page(b, B, '2026-04-05')
    pg.evaluate("""async()=>{await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const tx=q.result.transaction(['bucket','records'],'readwrite');
      tx.objectStore('bucket').put({id:'food-strawberry',addedAt:'2026-04-01'});tx.objectStore('bucket').put({id:'nature-cherry-blossom',addedAt:'2026-04-01'});
      tx.objectStore('records').put({key:'food-strawberry:2026',id:'food-strawberry',year:2026,date:'2026-04-03',memo:'옛 기록',photo:null});tx.oncomplete=()=>res()}})}""")
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
    check('v1 bucket data loads', pg.locator('[data-open="food-strawberry"]').count() == 1 and pg.locator('[data-open="nature-cherry-blossom"]').count() == 1)
    check('v1 stamp record loads', pg.locator('[data-undo="food-strawberry"]').count() == 1 and '옛 기록' in pg.inner_text('#view'))
    pg.click('[data-tab=stamps]')
    check('v1 stamp on board, visited board empty', pg.locator('[data-season-board] .stamp.on').count() == 1 and pg.locator('[data-visited-board] .stamp').count() == 0)
    check('no console errors (v1 compat)', not errs, str(errs))
    ctx.close()

    # ============ 사진 흐름 + 오프라인 SW ============
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None); pg.on('pageerror', lambda x: errs.append(str(x)))
    Image.new('RGB', (2400, 1600), (200, 120, 90)).save('/tmp/big.jpg')
    pg.goto(A + '?date=2026-04-05'); pg.wait_for_selector('body[data-ready="1"]')
    check('곧 끝나요 badge exists (04-05)', pg.locator('.badge.end').count() > 0)
    pg.locator('[data-sec=nature] [data-heart]').first.click(); pg.click('[data-tab=bucket]')
    pg.locator('[data-done]').first.click(); pg.set_input_files('#photoIn', '/tmp/big.jpg'); pg.wait_for_selector('#photoPrev:not([hidden])')
    pg.click('#doneSave'); pg.wait_for_selector('.stampline img')
    dims = pg.evaluate("async()=>{const r=await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const g=q.result.transaction('records').objectStore('records').getAll();g.onsuccess=()=>res(g.result)}});const bm=await createImageBitmap(r[0].photo);return [bm.width,bm.height,r[0].photo.type]}")
    check('photo resized <=1000 JPEG', max(dims[:2]) == 1000 and dims[2] == 'image/jpeg', str(dims))
    pg.click('[data-tab=stamps]'); pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]'); pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + 'photo_flow.png')
    pg.wait_for_timeout(1000); pg.reload(); pg.wait_for_timeout(1500)
    keys = pg.evaluate("async()=>await caches.keys()"); check('service worker cache v2', keys == ['cheolttara-v2'], str(keys))
    cached = pg.evaluate("async()=>(await (await caches.open('cheolttara-v2')).keys()).map(r=>new URL(r.url).pathname)")
    check('SW precaches places + festivals data', '/data/places.json' in cached and '/data/festivals.json' in cached, str(cached))
    check('SW never caches external images', all(not u.startswith('http') for u in cached) and not any('visitkorea' in u for u in cached))
    ctx.set_offline(True)
    try:
        pg.goto(A + '?date=2026-04-05', timeout=8000); pg.wait_for_selector('body[data-ready="1"]', timeout=8000)
        check('offline load via SW', pg.locator('#view .card').count() > 0)
    except Exception as e: check('offline load via SW', False, str(e)[:100])
    check('no console errors (photo/offline flow)', not errs, str(errs))

    # ============ 알림 (권한 스텁) ============
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda x: errs.append(str(x)))
    pg.add_init_script('''
      window.__notes=JSON.parse(sessionStorage.getItem('n')||'[]');
      const rec=(t,o)=>{window.__notes.push([t,o&&o.tag]);sessionStorage.setItem('n',JSON.stringify(window.__notes))};
      function N(t,o){rec(t,o)} N.permission='default'; N.requestPermission=async()=>{N.permission='granted';return 'granted'};
      window.Notification=N;
      if(window.ServiceWorkerRegistration) ServiceWorkerRegistration.prototype.showNotification=async function(t,o){rec(t,o)};
    ''')
    u = A + '?date=2026-04-05'
    pg.goto(u); pg.wait_for_selector('body[data-ready="1"]')
    pg.click('[data-heart="nature-forsythia"]')
    pg.click('[data-tab=alerts]'); pg.click('#notifySwitch'); pg.wait_for_timeout(800)
    check('notify toggle on (stub granted)', pg.get_attribute('#notifySwitch', 'aria-checked') == 'true')
    n1 = pg.evaluate('window.__notes.length'); check('notification shown on enable', n1 >= 1, str(pg.evaluate('window.__notes')))
    pg.goto(u); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_timeout(500)
    n2 = pg.evaluate('window.__notes.length'); check('at most once per item per day', n2 == n1, f'{n1}->{n2}')
    check('no page errors (notify flow)', not errs, str(errs))
    b.close()
finally:
    for s in srvs: s.terminate()
    shutil.rmtree(TMP, ignore_errors=True)

with open(FEST_PATH, encoding='utf-8') as f:
    check('committed data/festivals.json untouched (empty initial object)', f.read() == ORIGINAL_FEST and json.loads(ORIGINAL_FEST) == EMPTY_FESTIVALS)
fails = [r[0] for r in results if not r[1]]
print(f'{len(results) - len(fails)}/{len(results)} passed')
print('FAILS:', fails)
sys.exit(1 if fails else 0)

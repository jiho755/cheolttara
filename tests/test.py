"""철따라 v2 UI 테스트 (Playwright, 390x844). 실행: python3 tests/test.py

- 저장소를 임시 폴더로 복사하고, tests/fixtures 로 scripts/fetch_festivals.py 를 돌려 만든 축제 데이터를 넣어 서빙한다 (포트 8765).
- 8765: 축제 데이터만 있는 사본 (culture_seoul.json·culture_kr.json 은 빈 초기값으로 덮어씀 -> 공연·전시 섹션 숨김).
- 8767: 위 사본 + tests/fixtures/seoul_culture_*.json 으로 scripts/fetch_culture_seoul.py 를 돌려 만든 서울 문화행사 데이터.
- 8766: 축제·문화행사 모두 빈 초기 객체인 사본 ('축제 없음' 상태 확인).
- 8768: 8767 사본 + tests/fixtures/kr_culture_*.xml 로 scripts/fetch_culture_kr.py 를 돌려 만든 전국 문화행사 데이터.
- 끝나면 원본 data/festivals.json, data/culture_seoul.json, data/culture_kr.json 이 바뀌지 않았는지 확인하고, culture_kr.json 은 빈 초기 객체여야 한다.
"""
import base64
import re
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
CULT_PATH = os.path.join(ROOT, 'data', 'culture_seoul.json')
KR_PATH = os.path.join(ROOT, 'data', 'culture_kr.json')
EMPTY_FESTIVALS = {"updated": None, "source": "한국관광공사 TourAPI", "items": []}
EMPTY_CULTURE = {"updated": None, "source": "서울특별시 문화행사 정보 (공공누리 제1유형)", "items": []}
with open(FEST_PATH, encoding='utf-8') as f:
    ORIGINAL_FEST = f.read()
EMPTY_KR = {"updated": None, "source": "한국문화정보원 한눈에보는문화정보", "items": []}
with open(CULT_PATH, encoding='utf-8') as f:
    ORIGINAL_CULT = f.read()
with open(KR_PATH, encoding='utf-8') as f:
    ORIGINAL_KR = f.read()

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
for _p, _o in (('culture_seoul.json', EMPTY_CULTURE), ('culture_kr.json', EMPTY_KR)):   # 실제 파일은 자동 갱신되므로 사본은 빈 초기값으로 고정
    with open(os.path.join(SITE, 'data', _p), 'w', encoding='utf-8') as f:
        json.dump(_o, f, ensure_ascii=False)

SITE_C = os.path.join(TMP, 'site_culture')      # 축제 + 서울 문화행사
shutil.copytree(SITE, SITE_C)
rc = subprocess.call([sys.executable, '-I', os.path.join(ROOT, 'scripts', 'fetch_culture_seoul.py'),
                      '--fixture', os.path.join(FIX, 'seoul_culture_page1.json'), os.path.join(FIX, 'seoul_culture_page2.json'),
                      '--today', '2026-11-24', '--out', os.path.join(SITE_C, 'data', 'culture_seoul.json')])
assert rc == 0, 'fixture culture generation failed'
with open(os.path.join(SITE_C, 'data', 'culture_seoul.json'), encoding='utf-8') as f:
    CULT = json.load(f)
assert len(CULT['items']) == 21
SITE_K = os.path.join(TMP, 'site_kr')           # 축제 + 서울 + 전국 문화행사
shutil.copytree(SITE_C, SITE_K)
KRF = lambda n: os.path.join(FIX, n)
rc = subprocess.call([sys.executable, '-I', os.path.join(ROOT, 'scripts', 'fetch_culture_kr.py'),
                      '--fixture', 'A=' + KRF('kr_culture_A_page1.xml'), 'A=' + KRF('kr_culture_A_page2.xml'), 'B=' + KRF('kr_culture_B_page1.xml'),
                      'C=' + KRF('kr_culture_C_page1.xml'), '--today', '2026-11-24', '--out', os.path.join(SITE_K, 'data', 'culture_kr.json')])
assert rc == 0, 'fixture kr culture generation failed'
with open(os.path.join(SITE_K, 'data', 'culture_kr.json'), encoding='utf-8') as f:
    KR = json.load(f)
assert len(KR['items']) == 12
SITE_E = os.path.join(TMP, 'site_empty')        # 축제도 비어 있는 사본
shutil.copytree(SITE, SITE_E)
with open(os.path.join(SITE_E, 'data', 'festivals.json'), 'w', encoding='utf-8') as f:
    json.dump(EMPTY_FESTIVALS, f, ensure_ascii=False)

A = 'http://localhost:8765/'   # 축제 데이터 있음, 문화행사 비어 있음
B = 'http://localhost:8766/'   # 축제·문화행사 모두 비어 있음
C = 'http://localhost:8767/'   # 축제 + 서울 문화행사 (전국 파일은 비어 있음)
K = 'http://localhost:8768/'   # 축제 + 서울 + 전국 문화행사
srvs = [subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '-d', d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for port, d in ((8765, SITE), (8766, SITE_E), (8767, SITE_C), (8768, SITE_K))]
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
    ctx.route('https://culture.seoul.go.kr/**', image_route)
    ctx.route('https://cdn.example.kr/**', image_route)
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
    sel = ':is([data-open^="fest-"],[data-open^="seoul-"],[data-open^="kc-"])' if sec == 'fest' else ''
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
    check('11/24 footer: 축제 date, 공연·전시 아직 없음, credits', re.fullmatch(r'축제 \d+/\d+ · 서울 공연·전시 아직 없음 · 전국 공연·전시 아직 없음 · 자료: 한국관광공사, 서울특별시, 한국문화정보원', pg.inner_text('#festFoot')) is not None, pg.inner_text('#festFoot'))
    check('11/24 no 공연·전시 section when culture file is empty', pg.locator('[data-sec=culture]').count() == 0)
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

    # ============ v3: 서울 공연·전시 (C 사이트, 2026-11-24) ============
    def cnames(pg):
        return names(pg, 'culture')
    def cult_id(title):
        return pg.evaluate("t=>Object.values(CULTBYID).find(c=>c.title===t).id", title)
    ctx, pg, errs, url = new_page(b, C, '2026-11-24')
    pg.wait_for_selector('[data-sec=culture]')
    check('culture: section visible for 전체, below festival section',
          pg.evaluate("()=>{const a=document.querySelector('[data-sec=fest]'),c=document.querySelector('[data-sec=culture]');return !!(a.compareDocumentPosition(c)&Node.DOCUMENT_POSITION_FOLLOWING)}"))
    check('culture: heading has 서울 small label', '공연·전시' in pg.inner_text('[data-sec=culture] h2') and pg.inner_text('[data-sec=culture] h2 small') == '서울')
    check('culture: filter chips', pg.locator('[data-sec=culture] .cchip').all_inner_texts() == ['추천', '무료', '전시', '공연', '체험', '아이와 함께'] and pg.get_attribute('[data-cfilter=rec]', 'aria-pressed') == 'true')
    rec = cnames(pg)
    check('culture 추천: free first, in-month first, shorter first; 8 + 더 보기', rec == ['국악 한마당', '현대무용 신작 갈라', '어린이 겨울 영화제', '골목 투어 걷기', '가족 도자기 만들기 체험', '가을 서울 사진전', '마지막 날 연극', '겨울밤의 소극장 연극'] and pg.locator('#cultMore').count() == 1 and '1개' in pg.inner_text('#cultMore'), str(rec))
    check('culture: no festival-group item in culture section', '신촌 겨울 거리 축제' not in rec)
    pg.click('#cultMore')
    check('culture 더 보기 shows rest', pg.locator('#cultMore').count() == 0 and len(cnames(pg)) == 9 and cnames(pg)[-1] == '빛의 정원 미디어아트전', str(cnames(pg)))
    card = pg.locator('[data-sec=culture] .card', has_text='가을 서울 사진전')
    ctext = card.inner_text()
    check('culture card: title, "구 · 장소", period, 무료 badge', '종로구 · 서울시립미술관 서소문본관' in ctext and '10/20 ~ 12/20' in ctext and '무료' in ctext, ctext.replace('\n', ' | '))
    check('culture card: 진행 중 / 곧 끝나요 / D-n badges',
          '진행 중' in card.inner_text() and pg.locator('[data-sec=culture] .card', has_text='마지막 날 연극').locator('.badge.end').count() == 1
          and pg.locator('[data-sec=culture] .card', has_text='국악 한마당').locator('.badge.soon').inner_text() == 'D-4')
    check('culture card: thumbnail, 🎭 placeholder when no image',
          card.locator('.em img').count() == 1 and pg.locator('[data-sec=culture] .card', has_text='빛의 정원').locator('.em').inner_text().strip() == '🎭')
    pg.screenshot(path=OUT + 'v3_culture_home.png', full_page=True)
    # 필터 칩
    pg.click('[data-cfilter=free]'); fr = cnames(pg)
    check('culture filter 무료', len(fr) == 6 and '마지막 날 연극' not in fr and '빛의 정원 미디어아트전' not in fr and pg.get_attribute('[data-cfilter=free]', 'aria-pressed') == 'true', str(fr))
    pg.click('[data-cfilter=exhibit]'); check('culture filter 전시', cnames(pg) == ['가을 서울 사진전', '빛의 정원 미디어아트전'], str(cnames(pg)))
    pg.click('[data-cfilter=show]'); sh = cnames(pg); check('culture filter 공연', len(sh) == 5 and '국악 한마당' in sh and '가족 도자기 만들기 체험' not in sh, str(sh))
    pg.click('[data-cfilter=experience]'); check('culture filter 체험', cnames(pg) == ['가족 도자기 만들기 체험'], str(cnames(pg)))
    pg.click('[data-cfilter=kids]'); kd = cnames(pg)
    check('culture filter 아이와 함께 (target keywords)', len(kd) == 7 and '어린이 겨울 영화제' in kd and '가족 도자기 만들기 체험' in kd and '겨울밤의 소극장 연극' not in kd and '현대무용 신작 갈라' not in kd, str(kd))
    pg.click('[data-cfilter=rec]')
    # 달 바꾸기: 12월 (진행 중이 아닌 달이라 D-n 등) 와 필터가 유지되는지
    pg.click('[data-month="1"]')
    dec = cnames(pg)
    check('culture Dec: overlaps December only, 8 + 더 보기', len(dec) == 8 and '마지막 날 연극' not in dec and '국악 한마당' not in dec and pg.locator('#cultMore').count() == 1, str(dec))
    pg.click('[data-month="0"]')
    # 상세 시트
    pg.click('[data-sec=culture] [data-open]:has-text("가을 서울 사진전")'); pg.wait_for_selector('.sheet')
    st = pg.inner_text('.sheet')
    check('culture sheet fields', all(x in st for x in ('전시/미술', '2026-10-20 ~ 2026-12-20', '10:00~20:00', '서울시립미술관 서소문본관 (종로구)', '누구나')) and '서울특별시(공공누리 제1유형)' in st, st.replace('\n', ' | '))
    lk = pg.locator('.sheet a#sheetLink')
    check('culture sheet 자세히 보기 link (new tab)', lk.inner_text().strip() == '자세히 보기' and lk.get_attribute('href').startswith('https://culture.seoul.go.kr/culture/') and lk.get_attribute('target') == '_blank' and 'noopener' in lk.get_attribute('rel'), str(lk.get_attribute('href')))
    mp = pg.locator('.sheet a#sheetMap')
    check('culture sheet 지도 보기 link → naver map by place', mp.get_attribute('href') == 'https://map.naver.com/p/search/' + urllib.parse.quote('서울시립미술관 서소문본관', safe='') and mp.get_attribute('target') == '_blank', str(mp.get_attribute('href')))
    check('culture sheet image + 담기 + 해냈어요', pg.locator('.sheet img.hero').count() == 1 and pg.locator('#sheetHeart').count() == 1 and pg.locator('#sheetDone').count() == 1)
    pg.wait_for_timeout(300); pg.screenshot(path=OUT + 'v3_culture_sheet.png')
    pg.click('#sheetClose')
    # 링크 없고 좌표 없는 항목 (12월): 금천 거리 공연은 기관 링크, 지도는 place 로 검색
    pg.click('[data-month="1"]'); pg.click('[data-cfilter=free]')
    while pg.locator('#cultMore').count(): pg.click('#cultMore')
    pg.click('[data-sec=culture] [data-open]:has-text("금천 거리 공연")'); pg.wait_for_selector('.sheet')
    check('culture sheet without coordinates: link falls back to 기관 링크, map still by place',
          pg.get_attribute('.sheet a#sheetLink', 'href') == 'https://www.geumcheon.go.kr/' and pg.get_attribute('.sheet a#sheetMap', 'href').endswith(urllib.parse.quote('금천구청 광장', safe='')))
    pg.click('#sheetClose'); pg.click('[data-cfilter=rec]'); pg.click('[data-month="0"]')
    # 서울 축제는 축제·행사 섹션에 합쳐지고 관광공사와 같은 제목은 버린다
    fn = names(pg, 'fest')
    check('seoul festival merged into 축제·행사 (Nov = 5 tour + 1 seoul)', len(fn) == 6 and '신촌 겨울 거리 축제' in fn, str(fn))
    check('duplicate seoul festival dropped (same title after normalisation)', fn.count('서울빛초롱축제') == 1 and '서울 빛초롱축제' not in fn and pg.evaluate("()=>!Object.values(CULTBYID).some(c=>c.title==='서울 빛초롱축제')"), str(fn))
    check('seoul festival not in culture section', pg.locator('[data-sec=culture] .card', has_text='신촌').count() == 0)
    sid = cult_id('신촌 겨울 거리 축제')
    check('seoul festival card in fest section has 🎉 / free badge', pg.locator(f'[data-sec=fest] [data-open="{sid}"] .badge.free').count() == 1 and pg.locator(f'[data-sec=fest] [data-open="{sid}"]').inner_text().find('서대문구 · 신촌 연세로') >= 0)
    pg.click('[data-month="1"]'); pg.click('#festMore') if pg.locator('#festMore').count() else None
    check('Dec: 서울 겨울 책 축제 listed among festivals', '서울 겨울 책 축제' in names(pg, 'fest'), str(names(pg, 'fest')))
    pg.click('[data-month="0"]')
    # 지역 칩
    pg.click('[data-region="수도권"]')
    check('region 수도권: culture section visible, seoul festival listed', pg.locator('[data-sec=culture]').count() == 1 and sorted(names(pg, 'fest')) == sorted(['서울빛초롱축제', '인천 차이나타운 겨울 거리', '신촌 겨울 거리 축제']), str(names(pg, 'fest')))
    pg.click('[data-region="강원"]')
    check('region 강원: culture section hidden (seoul only), no seoul festival', pg.locator('[data-sec=culture]').count() == 0 and names(pg, 'fest') == ['춘천 눈꽃 마을 축제'], str(names(pg, 'fest')))
    pg.click('[data-region="경상"]'); check('region 경상: culture section hidden', pg.locator('[data-sec=culture]').count() == 0)
    pg.click('[data-region="전체"]')
    check('region 전체: culture section back', pg.locator('[data-sec=culture]').count() == 1)
    check('footer shows all dates and credits', re.fullmatch(r'축제 \d+/\d+ · 서울 공연·전시 \d+/\d+ · 전국 공연·전시 아직 없음 · 자료: 한국관광공사, 서울특별시, 한국문화정보원', pg.inner_text('#festFoot')) is not None, pg.inner_text('#festFoot'))
    # 버킷·도장 (서울 항목)
    pg.click('[data-sec=culture] [data-open]:has-text("국악 한마당")'); pg.wait_for_selector('.sheet')
    kid = pg.evaluate("()=>document.querySelector('[data-sec=culture] [data-open]').dataset.open")
    pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.click('[data-tab=bucket]')
    check('bucket has seoul item', pg.locator(f'#view [data-open="{kid}"]').count() == 1 and kid.startswith('seoul-'))
    pg.click(f'[data-done="{kid}"]'); pg.wait_for_selector('#doneSave'); pg.fill('#memoIn', '좋았다'); pg.click('#doneSave'); pg.wait_for_selector(f'[data-undo="{kid}"]')
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
    check('seoul bucket + stamp persist after reload', pg.locator(f'[data-undo="{kid}"]').count() == 1 and pg.locator('#view .card').count() == 1)
    stored = pg.evaluate("async()=>{const o=await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const g=q.result.transaction('bucket').objectStore('bucket').getAll();g.onsuccess=()=>res(g.result)}});return o.find(x=>x.id.startsWith('seoul-'))}")
    check('seoul bucket stores title/start/end/place/gu', stored and stored.get('title') == '국악 한마당' and stored.get('start') == '2026-11-28' and stored.get('end') == '2026-11-28' and stored.get('place') == '국립국악원 우면당' and stored.get('gu') == '종로구', str(stored))
    pg.click('[data-tab=stamps]')
    vb = pg.locator('[data-visited-board]')
    check('도장판 다녀온 곳 includes seoul item', vb.locator('.stamp.on').count() == 1 and '국악 한마당' in vb.inner_text() and '1곳' in vb.inner_text(), vb.inner_text().replace('\n', ' '))
    pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]'); pg.click('#cardClose')
    check('culture flow: no console errors', not errs, str(errs))
    ctx.close()

    # 알림: 서울 항목도 축제와 같은 규칙 (시작 3일 전)
    ctx, pg, errs, url = new_page(b, C, '2026-11-25')   # 국악 한마당 11/28 → D-3
    pg.locator('[data-sec=culture] .card-wrap', has_text='국악 한마당').locator('[data-heart]').click()
    pg.click('[data-tab=alerts]'); t = pg.locator('.alert.start').all_inner_texts()
    check('seoul item start alert (D-3)', len(t) == 1 and '국악 한마당' in t[0] and 'D-3' in t[0], str(t))
    ctx.close()
    ctx, pg, errs, url = new_page(b, C, '2026-11-24')   # 마지막 날 연극 오늘 종료 → D-0 끝나요
    pg.locator('[data-sec=culture] .card-wrap', has_text='마지막 날 연극').locator('[data-heart]').click()
    pg.click('[data-tab=alerts]'); t = pg.locator('.alert.end').all_inner_texts()
    check('seoul item end alert (D-day)', len(t) == 1 and '마지막 날 연극' in t[0] and 'D-day' in t[0], str(t))
    pg.click('.alert.end'); pg.wait_for_selector('.sheet'); check('alert opens seoul sheet', pg.locator('#sheetLink').count() == 1)
    ctx.close()

    # 첫 화면을 막지 않는다: culture_seoul.json 응답이 늦어도 축제·명소가 먼저 그려지고, 도착하면 섹션이 채워진다
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR')
    ctx.route('https://tong.visitkorea.or.kr/**', image_route); ctx.route('https://culture.seoul.go.kr/**', image_route)
    pg = ctx.new_page(); errs = []; held = []
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None); pg.on('pageerror', lambda x: errs.append(str(x)))
    pg.route('**/data/culture_seoul.json', lambda route: held.append(route))
    pg.goto(C + '?date=2026-11-24'); pg.wait_for_selector('body[data-ready="1"]')
    pg.wait_for_selector('[data-sec=fest] .card'); pg.wait_for_selector('[data-sec=place] .card')
    check('first paint not blocked by culture file', len(held) == 1 and pg.locator('[data-sec=culture]').count() == 0 and pg.locator('[data-sec=fest] .card').count() > 0, str(len(held)))
    held[0].continue_()
    pg.wait_for_selector('[data-sec=culture] .card')
    check('culture section fills in after load', pg.locator('[data-sec=culture] .card').count() == 8 and pg.get_attribute('body', 'data-culture') == '1')
    check('no console errors (late culture load)', not errs, str(errs))
    ctx.close()

    # 문화행사 파일이 없거나 깨져도 앱은 그대로
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda x: errs.append(str(x)))
    pg.route('**/data/culture_seoul.json', lambda route: route.fulfill(status=200, content_type='application/json', body='{broken'))
    pg.goto(C + '?date=2026-11-24'); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_timeout(500)
    check('broken culture file: no section, festivals fine, no page errors', pg.locator('[data-sec=culture]').count() == 0 and pg.locator('[data-sec=fest] .card').count() > 0 and not errs, str(errs))
    ctx.close()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda x: errs.append(str(x)))
    pg.route('**/data/culture_seoul.json', lambda route: route.fulfill(status=404, body='no'))
    pg.goto(C + '?date=2026-11-24'); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_timeout(500)
    check('missing culture file: section hidden, no page errors', pg.locator('[data-sec=culture]').count() == 0 and not errs, str(errs))
    ctx.close()
    # 빈 초기 파일 (A 사이트): 섹션 숨김, 오류 없음
    ctx, pg, errs, url = new_page(b, A, '2026-11-24'); pg.wait_for_timeout(500)
    check('empty culture file: section hidden, no console errors', pg.locator('[data-sec=culture]').count() == 0 and pg.locator('[data-sec=fest] .card').count() > 0 and not errs, str(errs))
    ctx.close()

    # ============ v3.1: 전국 공연·전시 (K 사이트 = 서울 + 전국, 2026-11-24) ============
    def kr_row_ids(pg, sec):
        return pg.locator(f'[data-sec={sec}] .card[data-open^="kc-"]').count()
    ctx, pg, errs, url = new_page(b, K, '2026-11-24')
    pg.wait_for_selector('body[data-culture="1"]'); pg.wait_for_selector('[data-sec=culture]')
    check('kr: 전체 label is 전국', pg.inner_text('[data-sec=culture] h2 small') == '전국')
    check('kr: footer shows all three update dates + credits', re.fullmatch(r'축제 \d+/\d+ · 서울 공연·전시 \d+/\d+ · 전국 공연·전시 \d+/\d+ · 자료: 한국관광공사, 서울특별시, 한국문화정보원', pg.inner_text('#festFoot')) is not None, pg.inner_text('#festFoot'))
    pg.click('[data-region="강원"]')
    check('kr: section visible for 강원 with the kr item only', pg.locator('[data-sec=culture]').count() == 1 and cnames(pg) == ['가을 사진전'] and pg.inner_text('[data-sec=culture] h2 small') == '강원', str(cnames(pg)))
    pg.click('[data-region="충청"]'); check('kr: 충청 shows 대전·천안 items', sorted(cnames(pg)) == ['도자기 만들기 체험', '주말 교실'], str(cnames(pg)))
    pg.click('[data-region="경상"]'); check('kr: 경상 shows 부산 musical', cnames(pg) == ['뮤지컬 <라이온>'], str(cnames(pg)))
    pg.click('[data-region="전라"]'); check('kr: section hidden when the region has no items this month', pg.locator('[data-sec=culture]').count() == 0)
    pg.click('[data-region="제주"]'); check('kr: 제주 hidden in Nov (제주 item starts 12/10)', pg.locator('[data-sec=culture]').count() == 0)
    pg.click('[data-month="1"]'); check('kr: 제주 shown in Dec', cnames(pg) == ['일련번호 없는 무용'], str(cnames(pg)))
    pg.click('[data-month="0"]')
    pg.click('[data-region="수도권"]')
    sudo = cnames(pg)
    check('kr: 수도권 mixes seoul and kr (경기 item), 강원 item excluded', '마지막 날 연극' in sudo and '가을 사진전' not in sudo and '뮤지컬 <라이온>' not in sudo and kr_row_ids(pg, 'culture') == 1, str(sudo))
    pg.click('[data-region="전체"]')
    # 교차 출처 중복 제거 (제목 정규화 + 시작일)
    allc = []
    pg.click('[data-month="1"]')
    while pg.locator('#cultMore').count(): pg.click('#cultMore')
    dec = cnames(pg)
    check('kr dedupe: same title+start as a seoul item is dropped (가을 서울 사진전 once)', dec.count('가을 서울 사진전') == 1 and pg.locator('[data-sec=culture] .card[data-open^="kc-"]', has_text='가을 서울 사진전').count() == 0, str(dec))
    check('kr dedupe: same title but different start is kept (국악 한마당 seoul 11/28 + kr 12/01; Dec shows the kr one)', dec.count('국악 한마당') == 1 and pg.locator('[data-sec=culture] [data-open^="kc-"]', has_text='국악 한마당').count() == 1 and pg.evaluate("()=>Object.values(CULTBYID).filter(c=>c.title==='국악 한마당').length") == 2, str(dec))
    check('kr: Dec culture has kr items (kc-)', kr_row_ids(pg, 'culture') >= 3, str(kr_row_ids(pg, 'culture')))
    pg.click('[data-month="0"]')
    fn = names(pg, 'fest')
    check('kr festival-group item merged into 축제·행사 (청주 지역 행사, kc-)', '청주 지역 행사' in fn and pg.locator('[data-sec=fest] [data-open^="kc-"]').count() == 1 and '청주 지역 행사' not in cnames(pg), str(fn))
    check('kr festival duplicate of tour festival dropped (서울 빛초롱 축제)', fn.count('서울빛초롱축제') == 1 and '서울 빛초롱 축제' not in fn and '서울 빛초롱축제' not in fn, str(fn))
    pg.click('[data-region="충청"]')
    check('kr festival respects region chips (충청 -> 청주)', names(pg, 'fest')[0] == '청주 지역 행사' and pg.locator('[data-sec=fest] [data-open^="kc-"]').count() == 1)
    pg.click('[data-region="강원"]'); check('kr festival hidden in 강원', pg.locator('[data-sec=fest] [data-open^="kc-"]').count() == 0)
    pg.click('[data-region="전체"]')
    # 무료 필터는 free null 을 무시
    pg.click('[data-cfilter=free]')
    check('kr: 무료 filter ignores free=null items', kr_row_ids(pg, 'culture') == 0 and len(cnames(pg)) == 6, str(cnames(pg)))
    pg.click('[data-cfilter=rec]')
    check('kr cards have no 무료 badge', pg.locator('[data-sec=culture] .card[data-open^="kc-"] .badge.free').count() == 0)
    card = pg.locator('[data-sec=culture] .card[data-open^="kc-"]', has_text='뮤지컬 <라이온>')
    check('kr card shows "시도 구 · 장소" and period', '부산 해운대구 · 해운대문화회관' in card.inner_text() and '11/20 ~ 11/30' in card.inner_text(), card.inner_text().replace('\n', ' | '))
    pg.screenshot(path=OUT + 'v31_kr_home.png', full_page=True)
    # 상세 시트: 비어 있는 행 숨김, 링크는 http(s) 일 때만
    pg.click('[data-region="강원"]'); pg.click('[data-sec=culture] [data-open^="kc-"]'); pg.wait_for_selector('.sheet')
    labels = pg.locator('.sheet .row > b').all_inner_texts()
    st = pg.inner_text('.sheet')
    check('kr sheet: only filled rows (분류·기간·장소), no 시간/대상/요금', labels == ['분류', '기간', '장소'], str(labels))
    check('kr sheet: values + credit', '전시' in st and '2026-10-01 ~ 2026-12-31' in st and '춘천미술관 (강원 춘천시)' in st and '자료: 한국문화정보원' in st and '서울특별시' not in st, st.replace('\n', ' | '))
    lk = pg.locator('.sheet a#sheetLink')
    check('kr sheet: 자세히 보기 for https link (new tab)', lk.count() == 1 and lk.get_attribute('href') == 'https://www.culture.go.kr/detail/1001' and lk.get_attribute('target') == '_blank' and 'noopener' in lk.get_attribute('rel'))
    check('kr sheet: 지도 보기 by place', pg.get_attribute('.sheet a#sheetMap', 'href') == 'https://map.naver.com/p/search/' + urllib.parse.quote('춘천미술관', safe=''))
    check('kr sheet: image (http->https) shown', pg.locator('.sheet img.hero').count() == 1 and pg.get_attribute('.sheet img.hero', 'src') == 'https://cdn.example.kr/p/1001.jpg')
    pg.wait_for_timeout(300); pg.screenshot(path=OUT + 'v31_kr_sheet.png')
    pg.click('#sheetClose')
    pg.click('[data-region="경상"]'); pg.click('[data-sec=culture] [data-open^="kc-"]'); pg.wait_for_selector('.sheet')
    check('kr sheet without link: no 자세히 보기, 지도 보기 still there', pg.locator('.sheet a#sheetLink').count() == 0 and pg.locator('.sheet a#sheetMap').count() == 1)
    pg.click('#sheetClose')
    # 버킷·도장 (kc-)
    pg.click('[data-region="강원"]'); kcid = pg.evaluate("()=>document.querySelector('[data-sec=culture] [data-open]').dataset.open")
    pg.click('[data-sec=culture] [data-open^="kc-"]'); pg.wait_for_selector('.sheet'); pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.click('[data-tab=bucket]')
    check('kr bucket has kc- item', kcid == 'kc-1001' and pg.locator(f'#view [data-open="{kcid}"]').count() == 1)
    pg.click(f'[data-done="{kcid}"]'); pg.wait_for_selector('#doneSave'); pg.fill('#memoIn', '좋았다'); pg.click('#doneSave'); pg.wait_for_selector(f'[data-undo="{kcid}"]')
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
    check('kr bucket + stamp persist after reload', pg.locator(f'[data-undo="{kcid}"]').count() == 1 and pg.locator('#view .card').count() == 1)
    stored = pg.evaluate("async()=>{const o=await new Promise(res=>{const q=indexedDB.open('cheolttara');q.onsuccess=()=>{const g=q.result.transaction('bucket').objectStore('bucket').getAll();g.onsuccess=()=>res(g.result)}});return o.find(x=>x.id.startsWith('kc-'))||null}")
    check('kr bucket stores title/start/end/place/gu/sido', stored and stored.get('title') == '가을 사진전' and stored.get('start') == '2026-10-01' and stored.get('end') == '2026-12-31' and stored.get('place') == '춘천미술관' and stored.get('gu') == '춘천시' and stored.get('sido') == '강원', str(stored))
    pg.click('[data-tab=stamps]'); vb = pg.locator('[data-visited-board]')
    check('도장판 다녀온 곳 includes kc- item', vb.locator('.stamp.on').count() == 1 and '가을 사진전' in vb.inner_text() and '1곳' in vb.inner_text(), vb.inner_text().replace('\n', ' '))
    pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]'); pg.click('#cardClose')
    check('kr flow: no console errors', not errs, str(errs))
    ctx.close()
    # 담아둔 kc- 항목이 이후 데이터에서 빠져도(전국 파일이 비어도) 버킷에서 보인다
    ctx, pg, errs, url = new_page(b, K, '2026-11-24'); pg.wait_for_selector('body[data-culture="1"]')
    pg.click('[data-region="경상"]'); pg.click('[data-sec=culture] [data-open^="kc-"] >> nth=0')
    pg.wait_for_selector('.sheet'); pg.click('#sheetHeart'); pg.click('#sheetClose')
    pg.route('**/data/culture_kr.json', lambda route: route.fulfill(json={"updated": None, "source": "x", "items": []}))
    pg.goto(url); pg.wait_for_selector('body[data-ready="1"]'); pg.click('[data-tab=bucket]')
    check('kr bucket item survives an emptied kr file (title from saved bucket)', pg.locator('#view .card[data-open^="kc-"]').count() == 1 and '뮤지컬' in pg.inner_text('#view'), pg.inner_text('#view')[:80])
    check('no console errors (kr bucket fallback)', not errs, str(errs))
    ctx.close()
    # 알림: kc- 항목도 같은 규칙 (시작 3일 전)
    ctx, pg, errs, url = new_page(b, K, '2026-11-28')   # 청주 지역 행사(festival) 11/28 시작 -> 진행 중, 국악 한마당(kr) 12/01 = D-3
    pg.wait_for_selector('body[data-culture="1"]')
    pg.click('[data-month="1"]'); pg.locator('[data-sec=culture] .card-wrap:has([data-open^="kc-"])', has_text='국악 한마당').locator('[data-heart]').click()
    pg.click('[data-tab=alerts]'); t = pg.locator('.alert.start').all_inner_texts()
    check('kr item start alert (D-3)', len(t) == 1 and '국악 한마당' in t[0] and 'D-3' in t[0], str(t))
    ctx.close()
    # 전국 파일이 없거나 깨져도 서울 자료는 그대로
    for label, handler in (('missing', lambda route: route.fulfill(status=404, body='no')), ('broken', lambda route: route.fulfill(status=200, content_type='application/json', body='{broken')),
                           ('wrong shape', lambda route: route.fulfill(json={"items": "x"}))):
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []
        pg.on('pageerror', lambda x, e=errs: e.append(str(x)))
        pg.route('**/data/culture_kr.json', handler)
        pg.goto(K + '?date=2026-11-24'); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_selector('[data-sec=culture]'); pg.wait_for_timeout(300)
        check(f'{label} kr file: seoul section intact, no page errors', pg.locator('[data-sec=culture] .card').count() == 8 and pg.locator('[data-open^="kc-"]').count() == 0 and not errs, str(errs))
        ctx.close()
    # 서울 파일이 비어 있고 전국만 있어도 동작 (라벨 전국)
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda x: errs.append(str(x))); pg.route('https://cdn.example.kr/**', image_route)
    pg.route('**/data/culture_seoul.json', lambda route: route.fulfill(json=EMPTY_CULTURE))
    pg.goto(K + '?date=2026-11-24'); pg.wait_for_selector('[data-sec=culture]')
    check('kr only (seoul file empty): section works, label 전국', pg.inner_text('[data-sec=culture] h2 small') == '전국' and kr_row_ids(pg, 'culture') >= 1 and not errs, str(errs))
    ctx.close()
    # 전국 파일 늦게 도착: 첫 화면과 서울 섹션을 막지 않는다
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []; held = []
    pg.on('pageerror', lambda x: errs.append(str(x))); pg.route('https://cdn.example.kr/**', image_route)
    pg.route('**/data/culture_kr.json', lambda route: held.append(route))
    pg.goto(K + '?date=2026-11-24'); pg.wait_for_selector('body[data-ready="1"]'); pg.wait_for_selector('[data-sec=culture] .card')
    check('late kr file: first paint + seoul section not blocked', len(held) == 1 and pg.locator('[data-sec=fest] .card').count() > 0 and pg.locator('[data-open^="kc-"]').count() == 0)
    held[0].continue_(); pg.wait_for_function("()=>document.querySelector('[data-sec=fest] [data-open^=\"kc-\"]')")
    check('late kr file: merged in once it arrives, no errors', pg.locator('[data-sec=fest] [data-open^="kc-"]').count() == 1 and not errs, str(errs))
    ctx.close()
    # 빈 전국 파일 (C 사이트): 오류 없음, 서울 자료는 그대로
    ctx, pg, errs, url = new_page(b, C, '2026-11-24'); pg.wait_for_selector('[data-sec=culture]'); pg.wait_for_timeout(300)
    check('empty kr file: no console errors, seoul section intact, no kc- items', not errs and pg.locator('[data-sec=culture] .card').count() == 8 and pg.locator('[data-open^="kc-"]').count() == 0, str(errs))
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
    check('empty festivals: footer', pg.inner_text('#festFoot') == '축제 아직 없음 · 서울 공연·전시 아직 없음 · 전국 공연·전시 아직 없음 · 자료: 한국관광공사, 서울특별시, 한국문화정보원', pg.inner_text('#festFoot'))
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
    keys = pg.evaluate("async()=>await caches.keys()"); check('service worker cache v5', keys == ['cheolttara-v5'], str(keys))
    cached = pg.evaluate("async()=>(await (await caches.open('cheolttara-v5')).keys()).map(r=>new URL(r.url).pathname)")
    check('SW precaches places + festivals + both culture files', '/data/places.json' in cached and '/data/festivals.json' in cached and '/data/culture_seoul.json' in cached and '/data/culture_kr.json' in cached, str(cached))
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
    # ============ Android 브리지 스텁 / Notification 없음 ============
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='ko-KR'); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda x: errs.append(str(x)))
    pg.add_init_script('''
      delete window.Notification;
      window.__saved=[]; window.CheolttaraAndroid={saveImage:function(b,n){window.__saved.push([b,n]);return true}};
    ''')
    pg.goto(A + '?date=2026-04-05'); pg.wait_for_selector('body[data-ready="1"]')
    pg.click('[data-tab=stamps]'); pg.click('#makeCard'); pg.wait_for_selector('#cardOut[data-ready="1"]')
    pg.click('#cardShare'); pg.wait_for_timeout(500)
    sv = pg.evaluate('window.__saved')
    check('android bridge: saveImage called with base64 png', len(sv) == 1 and len(sv[0][0]) > 1000 and not sv[0][0].startswith('data:') and sv[0][1].endswith('.png'), str([(len(x[0]), x[1]) for x in sv]))
    pg.click('#cardClose'); pg.click('[data-tab=alerts]')
    check('android: notify switch disabled when no Notification', pg.is_disabled('#notifySwitch') and '앱에서는 지원하지 않아요' in pg.locator('#view .toggle').inner_text())
    check('no page errors (android bridge)', not errs, str(errs))
    b.close()
finally:
    for s in srvs: s.terminate()
    shutil.rmtree(TMP, ignore_errors=True)

with open(FEST_PATH, encoding='utf-8') as f:
    check('committed data/festivals.json untouched', f.read() == ORIGINAL_FEST)
with open(CULT_PATH, encoding='utf-8') as f:
    check('committed data/culture_seoul.json untouched', f.read() == ORIGINAL_CULT)
with open(KR_PATH, encoding='utf-8') as f:
    check('committed data/culture_kr.json untouched and still the empty initial object', f.read() == ORIGINAL_KR and json.loads(ORIGINAL_KR) == EMPTY_KR)
fails = [r[0] for r in results if not r[1]]
print(f'{len(results) - len(fails)}/{len(results)} passed')
print('FAILS:', fails)
sys.exit(1 if fails else 0)

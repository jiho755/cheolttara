#!/usr/bin/env python3
"""한국문화정보원 '한눈에보는문화정보조회서비스'(data.go.kr 15138937, cultureinfo/period2)에서
전국 공연·전시·행사·체험 목록을 받아 data/culture_kr.json 을 만든다.

표준 라이브러리만 사용한다.
  TOUR_API_KEY=<디코딩 키> python3 scripts/fetch_culture_kr.py
  python3 scripts/fetch_culture_kr.py --fixture tests/fixtures/kr_culture_A_page1.xml --out /tmp/c.json   (네트워크 없이 테스트)
  --fixture 는 'B=파일' 처럼 serviceTp 접두를 붙일 수 있다 (없으면 A).

응답은 XML 이며 요소 이름을 확정하지 못해 대소문자·별칭을 관대하게 읽는다.
수집 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1로 끝난다.
키는 URL 에 들어가므로 URL·키는 어디에도 출력하지 않는다. 대신 serviceTp 마다 응답의 '구조'(태그 이름만)를 한 번 출력한다.
"""
import argparse
import hashlib
import importlib.util
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINT = 'https://apis.data.go.kr/B553457/cultureinfo/period2'
SOURCE = '한국문화정보원 한눈에보는문화정보'
KST = timezone(timedelta(hours=9))
SERVICE_TPS = ('A', 'B', 'C')      # A 공연/전시, B 행사/축제, C 교육/체험
ROWS = 100
ROWS_PARAM = 'numOfrows'           # 소문자 r 주의
PAGE_PARAM = 'PageNo'              # 동작하지 않으면 여기만 바꾸면 된다 (pageNo 등)
TIMEOUT = 25
RETRIES = 1
RETRY_DELAY = 2
MAX_PAGES = 30                     # serviceTp 마다
KEEP_AHEAD_DAYS = 120
MAX_SPAN_DAYS = 365
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), 'data', 'culture_kr.json')

# 필드 별칭 (모두 소문자)
ALIASES = {
    'seq': ('seq', 'serviceseq', 'contentid', 'id'),
    'title': ('title', 'subject'),
    'start': ('startdate', 'strtdate', 'start', 'startdt', 'begindate', 'eventstartdate'),
    'end': ('enddate', 'end', 'enddt', 'finishdate', 'eventenddate'),
    'place': ('place', 'placename', 'eventsite', 'location'),
    'realm': ('realmname', 'realm', 'category', 'realmnm'),
    'area': ('area', 'areaname', 'sido', 'areanm'),
    'sigungu': ('sigungu', 'signgu', 'sigunguname', 'sigungunm'),
    'image': ('thumbnail', 'imgurl', 'image', 'imageurl', 'thumbnailurl', 'mainimg'),
    'gpsx': ('gpsx', 'mapx', 'lot', 'longitude', 'lng'),
    'gpsy': ('gpsy', 'mapy', 'lat', 'latitude'),
}
LINK_ALIASES = ('url', 'homepage', 'homepageurl', 'linkurl', 'link', 'detailurl', 'siteurl', 'relateurl', 'pageurl', 'hmpgaddr')
IMAGE_HINT = re.compile(r'img|image|thumb|file|photo|pic', re.I)

ITEM_TAGS = ('item', 'perforlist')   # 구 API 는 perforList
EXHIBIT_WORDS = ('전시', '미술')
SHOW_WORDS = ('연극', '뮤지컬', '오페라', '음악', '콘서트', '클래식', '국악', '무용', '공연', '독주', '독창', '영화', '발레')


class FetchError(Exception):
    pass


def _load_festivals():
    spec = importlib.util.spec_from_file_location('_fetch_festivals_for_sido', os.path.join(HERE, 'fetch_festivals.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


normalize_sido = _load_festivals().normalize_sido


# ---------- 변환 ----------
def s(v):
    return re.sub(r'\s+', ' ', str(v if v is not None else '')).strip()


def fmt_date(v):
    """'20261124' / '2026-11-24' / '2026.11.24 ...' -> '2026-11-24' (잘못된 값이면 None)."""
    m = re.search(r'(\d{4})\D?(\d{2})\D?(\d{2})', str(v or ''))
    if not m:
        return None
    try:
        date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return '%s-%s-%s' % m.groups()


def to_float(v):
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f != 0 else None


def fix_coords(lat, lng):
    """위도 33~39, 경도 124~132 로 판별하고 뒤바뀐 경우 교정. 판별 불가면 (None, None)."""
    a, b = to_float(lat), to_float(lng)
    if a is None or b is None:
        return None, None
    if 33 <= a <= 39 and 124 <= b <= 132:
        return a, b
    if 33 <= b <= 39 and 124 <= a <= 132:
        return b, a
    return None, None


def https_image(v):
    v = s(v)
    if v.startswith('http://'):
        v = 'https://' + v[len('http://'):]
    return v if v.startswith('https://') else ''


def group_of(realm, tp):
    r = s(realm)
    if '축제' in r or '행사' in r:
        return 'festival'
    if tp == 'B':
        return 'festival'
    if '교육' in r or '체험' in r:
        return 'experience'
    if tp == 'C':
        return 'experience'
    if any(w in r for w in EXHIBIT_WORDS):
        return 'exhibit'
    if any(w in r for w in SHOW_WORDS):
        return 'show'
    return 'etc'


def pick(f, name):
    for a in ALIASES[name]:
        v = s(f.get(a))
        if v:
            return v
    return ''


def find_link(f, image=''):
    """http(s) URL 이 들어 있는 필드를 찾는다. 알려진 링크 필드 우선, 그다음 이미지 필드가 아닌 아무 필드나."""
    def ok(v):
        return bool(re.match(r'^https?://', v, re.I))
    for a in LINK_ALIASES:
        v = s(f.get(a))
        if ok(v):
            return v
    for k, v in f.items():
        v = s(v)
        if ok(v) and not IMAGE_HINT.search(k) and v != image and v.replace('http://', 'https://', 1) != image:
            return v
    return ''


def make_id(f, title, start, place):
    seq = re.sub(r'[^0-9A-Za-z_-]', '', pick(f, 'seq'))
    if seq:
        return 'kc-' + seq
    key = '%s|%s|%s' % (title, start or '', place)
    return 'kc-' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]


def map_item(f, tp):
    """소문자 키 dict -> 앱 형식. 제목/시작일이 없으면 None."""
    title = pick(f, 'title')
    start = fmt_date(pick(f, 'start'))
    if not title or not start:
        return None
    end = fmt_date(pick(f, 'end')) or start
    if end < start:
        end = start
    place, realm = pick(f, 'place'), pick(f, 'realm')
    area, gu = pick(f, 'area'), pick(f, 'sigungu')
    lat, lng = fix_coords(pick(f, 'gpsy'), pick(f, 'gpsx'))
    image = https_image(pick(f, 'image'))
    return {
        'id': make_id(f, title, start, place),
        'cat': realm,
        'group': group_of(realm, tp),
        'title': title,
        'start': start,
        'end': end,
        'gu': gu,
        'sido': normalize_sido(('%s %s' % (area, gu)).strip(), '', area),
        'place': place,
        'target': '',
        'fee': '',
        'free': None,
        'time': '',
        'image': image,
        'link': find_link(f, image),
        'lat': lat,
        'lng': lng,
    }


# ---------- 응답 해석 ----------
def local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def parse_page(raw):
    """XML 바이트 -> (items: [소문자 키 dict], totalCount, 구조 요약 dict). 오류 응답이면 FetchError."""
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    raw = raw.lstrip(b'\xef\xbb\xbf \t\r\n')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise FetchError('response is not valid XML')
    tags = {}
    for el in root.iter():
        t = local(el.tag)
        if t:
            tags.setdefault(t.lower(), t)
    summary = {'root': local(root.tag), 'tags': sorted(tags.values()), 'item_children': []}
    if local(root.tag).lower() == 'openapi_serviceresponse':
        info = {}
        for el in root.iter():
            if el.text and el.text.strip():
                info[local(el.tag).lower()] = el.text.strip()
        raise FetchError('API error: %s %s' % (info.get('returnreasoncode') or info.get('errmsg', ''),
                                              info.get('returnauthmsg') or info.get('errmsg', '')))
    code = msg = None
    total = 0
    for el in root.iter():
        t = local(el.tag).lower()
        v = (el.text or '').strip()
        if t == 'resultcode' and code is None:
            code = v
        elif t == 'resultmsg' and msg is None:
            msg = v
        elif t == 'totalcount' and not total:
            try:
                total = int(float(v))
            except ValueError:
                total = 0
    if code is not None and code not in ('00', '0000', '0', ''):
        if code in ('03', '3', '0003'):   # NODATA
            return [], 0, summary
        raise FetchError('API error: %s %s' % (code, msg or ''))
    items = []
    for el in root.iter():
        if local(el.tag).lower() not in ITEM_TAGS:
            continue
        f = {}
        for ch in el:
            k = local(ch.tag).lower()
            v = (ch.text or '').strip()
            if k and (k not in f or (v and not f[k])):
                f[k] = v
        if not summary['item_children']:
            summary['item_children'] = [local(ch.tag) for ch in el]
        if f:
            items.append(f)
    return items, total, summary


def print_diag(tp, status, summary):
    print('[diag] serviceTp=%s http=%s root=%s tags=%s first_item_children=%s' % (
        tp, status, summary['root'], ','.join(summary['tags']) or '-', ','.join(summary['item_children']) or '-'))


def redact(msg, key):
    msg = str(msg)
    if key:
        for k in {key, urllib.parse.quote(key, safe=''), urllib.parse.quote_plus(key)}:
            msg = msg.replace(k, '***')
    return msg


# ---------- 가져오기 ----------
def http_get(url, timeout=TIMEOUT):
    """(status, body bytes)"""
    req = urllib.request.Request(url, headers={'User-Agent': 'cheolttara-culture-fetcher', 'Accept': 'application/xml, text/xml, */*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def build_url(key, tp, page, frm, to):
    q = urllib.parse.urlencode([
        ('serviceKey', key), (PAGE_PARAM, page), (ROWS_PARAM, ROWS),
        ('serviceTp', tp), ('from', frm), ('to', to),
    ], quote_via=urllib.parse.quote)   # Decoding 키를 한 번만 인코딩
    return ENDPOINT + '?' + q          # 키가 들어 있으므로 출력 금지


def fetch_live_page(key, tp, page, frm, to):
    err = None
    for attempt in range(RETRIES + 1):
        try:
            status, raw = http_get(build_url(key, tp, page, frm, to), TIMEOUT)
            return status, parse_page(raw)
        except FetchError as e:
            err = redact(e, key)
        except urllib.error.HTTPError as e:
            err = 'HTTP %s' % e.code
        except (urllib.error.URLError, OSError, ValueError) as e:
            err = '%s: request failed' % type(e).__name__
        if attempt < RETRIES:
            print('serviceTp=%s page %d failed (%s), retrying' % (tp, page, err), file=sys.stderr)
            time.sleep(RETRY_DELAY)
    raise FetchError('serviceTp=%s page %d failed: %s' % (tp, page, err))


def row_key(f):
    return pick(f, 'seq') or '%s|%s|%s' % (pick(f, 'title'), pick(f, 'start'), pick(f, 'place'))


def collect_tp(key, tp, frm, to, diagnose=False):
    """한 serviceTp 의 모든 쪽. -> [(tp, f)]"""
    rows, seen, total = [], set(), 0
    for page in range(1, MAX_PAGES + 1):
        status, (items, tot, summary) = fetch_live_page(key, tp, page, frm, to)
        if page == 1:
            print_diag(tp, status, summary)
            total = tot
            if diagnose:
                return [(tp, f) for f in items]
        if not items:
            break
        new = [f for f in items if row_key(f) not in seen]
        if not new:
            print('serviceTp=%s page %d repeated earlier rows -- stopping (check %s)' % (tp, page, PAGE_PARAM), file=sys.stderr)
            break
        seen.update(row_key(f) for f in new)
        rows.extend((tp, f) for f in new)
        if total and page * ROWS >= total:
            break
    return rows


def collect_live(key, today, diagnose=False):
    frm = today.strftime('%Y%m%d')
    to = (today + timedelta(days=KEEP_AHEAD_DAYS)).strftime('%Y%m%d')
    rows, errors = [], []
    for tp in SERVICE_TPS:
        try:
            rows.extend(collect_tp(key, tp, frm, to, diagnose))
        except FetchError as e:
            errors.append(str(e))
            print('error: %s' % e, file=sys.stderr)
    if errors:
        raise FetchError('%d of %d serviceTp loops failed: %s' % (len(errors), len(SERVICE_TPS), '; '.join(errors)))
    return rows


def collect_fixture(specs):
    rows, diag_done = [], set()
    for spec in specs:
        m = re.match(r'^([ABC])=(.+)$', spec)
        tp, path = (m.group(1), m.group(2)) if m else ('A', spec)
        try:
            with open(path, 'rb') as fh:
                raw = fh.read()
        except OSError as e:
            raise FetchError('cannot read fixture %s: %s' % (path, e.strerror or e))
        items, _, summary = parse_page(raw)
        if tp not in diag_done:
            diag_done.add(tp)
            print_diag(tp, 'fixture', summary)
        rows.extend((tp, f) for f in items)
    return rows


# ---------- 정리·저장 ----------
def build_items(rows, today):
    limit = today + timedelta(days=KEEP_AHEAD_DAYS)
    seen, out = set(), []
    for tp, f in rows:
        m = map_item(f, tp)
        if not m or m['id'] in seen:
            continue
        st, en = date.fromisoformat(m['start']), date.fromisoformat(m['end'])
        if en < today or st > limit or (en - st).days > MAX_SPAN_DAYS:
            continue
        seen.add(m['id'])
        out.append(m)
    out.sort(key=lambda x: (x['start'], x['end'], x['id']))
    return out


def write_atomic(path, obj):
    import json
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('{\n "updated": %s,\n "source": %s,\n "items": [\n' % (json.dumps(obj['updated']), json.dumps(obj['source'], ensure_ascii=False)))
        f.write(',\n'.join('  ' + json.dumps(i, ensure_ascii=False) for i in obj['items']))
        f.write('\n ]\n}\n')
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fixture', nargs='+', metavar='[TP=]FILE', help='네트워크 대신 저장된 XML 응답을 사용 (TP 는 A/B/C, 생략 시 A)')
    ap.add_argument('--out', default=DEFAULT_OUT, help='출력 파일 (기본: data/culture_kr.json)')
    ap.add_argument('--today', help='기준일 YYYY-MM-DD (테스트용, 기본: 오늘 KST)')
    ap.add_argument('--diagnose', action='store_true', help='serviceTp 마다 첫 쪽만 받아 응답 구조(태그 이름)만 출력하고 파일은 쓰지 않음')
    args = ap.parse_args(argv)

    now = datetime.now(KST)
    try:
        today = date.fromisoformat(args.today) if args.today else now.date()
    except ValueError:
        print('error: invalid --today', file=sys.stderr)
        return 1
    key = ''
    try:
        if args.fixture:
            rows = collect_fixture(args.fixture)
        else:
            key = os.environ.get('TOUR_API_KEY', '').strip()
            if not key:
                raise FetchError('TOUR_API_KEY is not set')
            rows = collect_live(key, today, args.diagnose)
        if args.diagnose:
            print('diagnose only: %d raw items on first pages, nothing written' % len(rows))
            return 0
        items = build_items(rows, today)
    except FetchError as e:
        print('error: %s -- keeping existing file' % redact(e, key), file=sys.stderr)
        return 1
    if not items:
        print('error: 0 culture events collected -- keeping existing file', file=sys.stderr)
        return 1
    write_atomic(args.out, {'updated': now.isoformat(timespec='seconds'), 'source': SOURCE, 'items': items})
    print('wrote %d culture events to %s' % (len(items), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())

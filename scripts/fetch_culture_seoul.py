#!/usr/bin/env python3
"""서울 열린데이터광장 '서울시 문화행사 정보'(culturalEventInfo)에서 공연·전시·체험 목록을 받아 data/culture_seoul.json 을 만든다.

표준 라이브러리만 사용한다.
  SEOUL_API_KEY=<인증키> python3 scripts/fetch_culture_seoul.py
  python3 scripts/fetch_culture_seoul.py --fixture tests/fixtures/seoul_culture_page1.json   (네트워크 없이 테스트)

수집 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1로 끝난다.
키는 URL 경로에 그대로 들어가므로 URL 은 어디에도 출력하지 않는다.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

ENDPOINT = 'http://openapi.seoul.go.kr:8088/%s/json/culturalEventInfo/%d/%d/'
SOURCE = '서울특별시 문화행사 정보 (공공누리 제1유형)'
KST = timezone(timedelta(hours=9))
ROWS = 1000
TIMEOUT = 30
RETRIES = 3          # 쪽마다 실패 시 재시도 횟수 (서울시 서버가 해외 접속 시 가끔 시간 초과)
RETRY_DELAY = 10     # 초 (재시도마다 RETRY_DELAY * 시도 횟수만큼 대기)
MAX_PAGES = 60
KEEP_AHEAD_DAYS = 120
MAX_SPAN_DAYS = 365
TEXT_MAX = 80
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'culture_seoul.json')

EXHIBIT = {'전시/미술'}
SHOW = {'연극', '뮤지컬/오페라', '무용', '국악', '클래식', '콘서트', '독주/독창회', '영화'}
EXPERIENCE = {'교육/체험'}


class FetchError(Exception):
    pass


# ---------- 변환 ----------
def s(v):
    return re.sub(r'\s+', ' ', str(v if v is not None else '')).strip()


def cut(v, n=TEXT_MAX):
    v = s(v)
    return v if len(v) <= n else v[:n].rstrip()


def group_of(codename):
    c = s(codename)
    if c.startswith('축제'):
        return 'festival'
    if c in EXHIBIT:
        return 'exhibit'
    if c in SHOW:
        return 'show'
    if c in EXPERIENCE:
        return 'experience'
    return 'etc'


def fmt_date(v):
    """'2026-11-24 00:00:00.0' 또는 '2026-11-24' -> '2026-11-24' (잘못된 값이면 None)."""
    m = re.match(r'^\s*(\d{4})-(\d{2})-(\d{2})', str(v or ''))
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
    """LAT/LOT 가 뒤바뀌어 오는 경우가 있어 범위(위도 33~39, 경도 124~132)로 판별. 판별 불가면 (None, None)."""
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


def web_link(*cands):
    for c in cands:
        c = s(c)
        if re.match(r'^https?://', c, re.I):
            return c
    return ''


def make_id(raw_title, raw_start, raw_place):
    key = '%s|%s|%s' % (s(raw_title), s(raw_start), s(raw_place))
    return 'seoul-' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]


def map_item(raw):
    """row -> 앱 형식. 필수값(제목/시작일)이 없으면 None."""
    title = s(raw.get('TITLE'))
    start = fmt_date(raw.get('STRTDATE')) or fmt_date(str(raw.get('DATE') or '').split('~')[0])
    if not title or not start:
        return None
    end = fmt_date(raw.get('END_DATE')) or fmt_date(str(raw.get('DATE') or '').split('~')[-1]) or start
    if end < start:
        end = start
    lat, lng = fix_coords(raw.get('LAT'), raw.get('LOT'))
    return {
        'id': make_id(title, raw.get('STRTDATE'), raw.get('PLACE')),
        'cat': s(raw.get('CODENAME')),
        'group': group_of(raw.get('CODENAME')),
        'title': title,
        'start': start,
        'end': end,
        'gu': s(raw.get('GUNAME')),
        'place': s(raw.get('PLACE')),
        'target': cut(raw.get('USE_TRGT')),
        'fee': cut(raw.get('USE_FEE')),
        'free': s(raw.get('IS_FREE')) == '무료',
        'time': cut(raw.get('PRO_TIME')),
        'image': https_image(raw.get('MAIN_IMG')),
        'link': web_link(raw.get('HMPG_ADDR'), raw.get('ORG_LINK')),
        'lat': lat,
        'lng': lng,
    }


# ---------- 응답 해석 ----------
def parse_response(data):
    """응답 JSON -> (rows 리스트, list_total_count). 오류 구조면 FetchError."""
    if not isinstance(data, dict):
        raise FetchError('unexpected response type')
    info = data.get('culturalEventInfo')
    if info is None:
        res = data.get('RESULT')  # 키 오류 등은 최상위에 RESULT 만 온다
        if isinstance(res, dict):
            raise FetchError('API error: %s %s' % (res.get('CODE'), res.get('MESSAGE')))
        raise FetchError('missing culturalEventInfo')
    if not isinstance(info, dict):
        raise FetchError('unexpected culturalEventInfo shape')
    res = info.get('RESULT') or {}
    code = str(res.get('CODE'))
    try:
        total = int(info.get('list_total_count') or 0)
    except (TypeError, ValueError):
        total = 0
    if code == 'INFO-200':
        return [], 0
    if code != 'INFO-000':
        raise FetchError('API error: %s %s' % (res.get('CODE'), res.get('MESSAGE')))
    rows = info.get('row')
    if rows is None:
        return [], total
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise FetchError('unexpected row shape')
    return [x for x in rows if isinstance(x, dict)], total


# ---------- 가져오기 ----------
def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={'User-Agent': 'cheolttara-culture-fetcher'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build_url(key, start, end):
    return ENDPOINT % (key, start, end)  # 키가 들어 있으므로 출력 금지


def fetch_live_page(key, page):
    first = (page - 1) * ROWS + 1
    last = page * ROWS
    err = None
    for attempt in range(RETRIES + 1):
        try:
            raw = http_get(build_url(key, first, last), TIMEOUT)
            return parse_response(json.loads(raw.decode('utf-8')))
        except FetchError as e:
            err = str(e)
        except urllib.error.HTTPError as e:
            err = 'HTTP %s' % e.code
        except (urllib.error.URLError, OSError, ValueError) as e:  # ValueError: JSON/디코딩 실패
            err = '%s: request failed' % type(e).__name__
        if attempt < RETRIES:
            print('page %d failed (%s), retrying' % (page, err), file=sys.stderr)
            time.sleep(RETRY_DELAY * (attempt + 1))
    raise FetchError('page %d failed: %s' % (page, err))


def collect_live(key):
    rows, total = fetch_live_page(key, 1)
    pages = min(MAX_PAGES, max(1, math.ceil(total / ROWS))) if total else 1
    for p in range(2, pages + 1):
        more, _ = fetch_live_page(key, p)
        rows.extend(more)
    return rows


def collect_fixture(paths):
    rows = []
    for p in paths:
        try:
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise FetchError('cannot read fixture %s: %s' % (p, e))
        more, _ = parse_response(data)
        rows.extend(more)
    return rows


# ---------- 정리·저장 ----------
def build_items(raw_rows, today):
    limit = today + timedelta(days=KEEP_AHEAD_DAYS)
    seen, out = set(), []
    for raw in raw_rows:
        m = map_item(raw)
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
    ap.add_argument('--fixture', nargs='+', metavar='FILE', help='네트워크 대신 저장된 응답 JSON(쪽 순서대로)을 사용')
    ap.add_argument('--out', default=DEFAULT_OUT, help='출력 파일 (기본: data/culture_seoul.json)')
    ap.add_argument('--today', help='기준일 YYYY-MM-DD (테스트용, 기본: 오늘 KST)')
    args = ap.parse_args(argv)

    now = datetime.now(KST)
    try:
        today = date.fromisoformat(args.today) if args.today else now.date()
    except ValueError:
        print('error: invalid --today', file=sys.stderr)
        return 1
    try:
        if args.fixture:
            raw = collect_fixture(args.fixture)
        else:
            key = os.environ.get('SEOUL_API_KEY', '').strip()
            if not key:
                raise FetchError('SEOUL_API_KEY is not set')
            raw = collect_live(key)
        items = build_items(raw, today)
    except FetchError as e:
        print('error: %s -- keeping existing file' % e, file=sys.stderr)
        return 1
    if not items:
        print('error: 0 culture events collected -- keeping existing file', file=sys.stderr)
        return 1
    write_atomic(args.out, {'updated': now.isoformat(timespec='seconds'), 'source': SOURCE, 'items': items})
    print('wrote %d culture events to %s' % (len(items), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())

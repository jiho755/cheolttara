#!/usr/bin/env python3
"""한국관광공사 TourAPI(KorService2 searchFestival2)에서 축제 목록을 받아 data/festivals.json 을 만든다.

표준 라이브러리만 사용한다.
  TOUR_API_KEY=<디코딩 키> python3 scripts/fetch_festivals.py
  python3 scripts/fetch_festivals.py --fixture tests/fixtures/searchFestival2_page1.json   (네트워크 없이 테스트)

수집 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1로 끝난다.
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

ENDPOINT = 'https://apis.data.go.kr/B551011/KorService2/searchFestival2'
SOURCE = '한국관광공사 TourAPI'
KST = timezone(timedelta(hours=9))
ROWS = 100
TIMEOUT = 20
RETRIES = 1          # 쪽마다 실패 시 재시도 횟수
RETRY_DELAY = 2      # 초
MAX_PAGES = 50
KEEP_DAYS = 180
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'festivals.json')

SIDO_NAMES = {
    '서울': '서울', '서울특별시': '서울',
    '부산': '부산', '부산광역시': '부산',
    '대구': '대구', '대구광역시': '대구',
    '인천': '인천', '인천광역시': '인천',
    '광주': '광주', '광주광역시': '광주',
    '대전': '대전', '대전광역시': '대전',
    '울산': '울산', '울산광역시': '울산',
    '세종': '세종', '세종특별자치시': '세종', '세종시': '세종',
    '경기': '경기', '경기도': '경기',
    '강원': '강원', '강원도': '강원', '강원특별자치도': '강원', '강원자치도': '강원',
    '충북': '충북', '충청북도': '충북',
    '충남': '충남', '충청남도': '충남',
    '전북': '전북', '전라북도': '전북', '전북특별자치도': '전북', '전북자치도': '전북',
    '전남': '전남', '전라남도': '전남',
    '경북': '경북', '경상북도': '경북',
    '경남': '경남', '경상남도': '경남',
    '제주': '제주', '제주도': '제주', '제주특별자치도': '제주',
}
# 법정동 시도 코드 (강원 42/51, 전북 45/52 는 구·신 코드 모두)
LDONG_SIDO = {
    '11': '서울', '26': '부산', '27': '대구', '28': '인천', '29': '광주', '30': '대전', '31': '울산', '36': '세종',
    '41': '경기', '42': '강원', '51': '강원', '43': '충북', '44': '충남', '45': '전북', '52': '전북',
    '46': '전남', '47': '경북', '48': '경남', '50': '제주',
}
# 관광공사 지역코드(areacode) — lDongRegnCd 도 없을 때의 마지막 보완
AREA_SIDO = {
    '1': '서울', '2': '인천', '3': '대전', '4': '대구', '5': '광주', '6': '부산', '7': '울산', '8': '세종',
    '31': '경기', '32': '강원', '33': '충북', '34': '충남', '35': '경북', '36': '경남', '37': '전북', '38': '전남', '39': '제주',
}


class FetchError(Exception):
    pass


# ---------- 변환 ----------
def normalize_sido(addr1, ldong='', area=''):
    words = (addr1 or '').split()
    if words and words[0] in SIDO_NAMES:
        return SIDO_NAMES[words[0]]
    if words and words[0].startswith('전남광주'):  # 전남광주통합특별시: 광주 자치구면 광주, 아니면 전남
        gu = words[1] if len(words) > 1 else ''
        return '광주' if gu in ('동구', '서구', '남구', '북구', '광산구') else '전남'
    code = str(ldong or '').strip()[:2]
    if code in LDONG_SIDO:
        return LDONG_SIDO[code]
    a = str(area or '').strip()
    if a in AREA_SIDO:
        return AREA_SIDO[a]
    return '기타'


def clean_title(t):
    t = re.sub(r'\s+', ' ', str(t or '')).strip()
    for pat in (r'^(\[[^\]]*\]\s*)+', r'(\s*\[[^\]]*\])+$'):
        stripped = re.sub(pat, '', t).strip()
        if stripped:
            t = stripped
    return t


def fmt_date(s):
    s = re.sub(r'\D', '', str(s or ''))
    if len(s) != 8:
        return None
    try:
        date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None
    return '%s-%s-%s' % (s[:4], s[4:6], s[6:])


def to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f == 0:
        return None
    return f


def map_item(raw):
    """TourAPI 항목 -> 앱 형식. 필수값(id/title/기간)이 없으면 None."""
    cid = str(raw.get('contentid') or '').strip()
    title = clean_title(raw.get('title'))
    start, end = fmt_date(raw.get('eventstartdate')), fmt_date(raw.get('eventenddate'))
    if not cid or not title or not start:
        return None
    if not end or end < start:
        end = start
    addr1 = str(raw.get('addr1') or '').strip()
    addr2 = str(raw.get('addr2') or '').strip()
    image = str(raw.get('firstimage') or '').strip()
    if image.startswith('http://'):
        image = 'https://' + image[len('http://'):]
    return {
        'id': cid,
        'title': title,
        'start': start,
        'end': end,
        'addr': (addr1 + ' ' + addr2).strip(),
        'sido': normalize_sido(addr1, raw.get('lDongRegnCd'), raw.get('areacode')),
        'image': image,
        'tel': str(raw.get('tel') or '').strip(),
        'mapx': to_float(raw.get('mapx')),
        'mapy': to_float(raw.get('mapy')),
    }


# ---------- 응답 해석 ----------
def parse_response(data):
    """응답 JSON -> (items 리스트, totalCount). 오류 구조면 FetchError."""
    if not isinstance(data, dict):
        raise FetchError('unexpected response type')
    if 'OpenAPI_ServiceResponse' in data:
        hdr = data['OpenAPI_ServiceResponse'].get('cmmMsgHeader', {}) if isinstance(data['OpenAPI_ServiceResponse'], dict) else {}
        raise FetchError('API error: %s' % (hdr.get('returnAuthMsg') or hdr.get('errMsg') or 'OpenAPI_ServiceResponse'))
    resp = data.get('response')
    if not isinstance(resp, dict):
        raise FetchError('missing response')
    header = resp.get('header') or {}
    if str(header.get('resultCode')) != '0000':
        raise FetchError('API error: %s %s' % (header.get('resultCode'), header.get('resultMsg')))
    body = resp.get('body')
    if not isinstance(body, dict):
        raise FetchError('missing body')
    try:
        total = int(body.get('totalCount') or 0)
    except (TypeError, ValueError):
        total = 0
    items = body.get('items')
    if not items:  # "" 또는 None
        return [], total
    if not isinstance(items, dict):
        raise FetchError('unexpected items shape')
    item = items.get('item')
    if item is None:
        return [], total
    if isinstance(item, dict):
        item = [item]
    if not isinstance(item, list):
        raise FetchError('unexpected item shape')
    return [x for x in item if isinstance(x, dict)], total


# ---------- 가져오기 ----------
def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={'User-Agent': 'cheolttara-festival-fetcher'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build_url(key, page, today):
    q = {
        'serviceKey': key, 'MobileOS': 'ETC', 'MobileApp': 'cheolttara', '_type': 'json',
        'arrange': 'A', 'numOfRows': ROWS, 'pageNo': page, 'eventStartDate': today.strftime('%Y%m%d'),
    }
    return ENDPOINT + '?' + urllib.parse.urlencode(q)  # 키는 여기서 한 번만 인코딩


def fetch_live_page(key, page, today):
    last = None
    for attempt in range(RETRIES + 1):
        try:
            raw = http_get(build_url(key, page, today), TIMEOUT)
            return parse_response(json.loads(raw.decode('utf-8')))
        except FetchError as e:
            last = str(e)
        except urllib.error.HTTPError as e:
            last = 'HTTP %s' % e.code
        except (urllib.error.URLError, OSError, ValueError) as e:  # ValueError: JSON/디코딩 실패
            last = '%s: %s' % (type(e).__name__, getattr(e, 'reason', e) if isinstance(e, urllib.error.URLError) else 'request failed')
        if attempt < RETRIES:
            print('page %d failed (%s), retrying' % (page, last), file=sys.stderr)
            time.sleep(RETRY_DELAY)
    raise FetchError('page %d failed: %s' % (page, last))


def collect_live(key, today):
    items, total = fetch_live_page(key, 1, today)
    pages = min(MAX_PAGES, max(1, math.ceil(total / ROWS))) if total else 1
    for p in range(2, pages + 1):
        more, _ = fetch_live_page(key, p, today)
        items.extend(more)
    return items


def collect_fixture(paths):
    items = []
    for p in paths:
        try:
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise FetchError('cannot read fixture %s: %s' % (p, e))
        more, _ = parse_response(data)
        items.extend(more)
    return items


# ---------- 정리·저장 ----------
def build_items(raw_items, today):
    limit = today + timedelta(days=KEEP_DAYS)
    seen, out = set(), []
    for raw in raw_items:
        m = map_item(raw)
        if not m or m['id'] in seen:
            continue
        s = date.fromisoformat(m['start'])
        e = date.fromisoformat(m['end'])
        if s > limit or e < today:
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
    ap.add_argument('--out', default=DEFAULT_OUT, help='출력 파일 (기본: data/festivals.json)')
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
            key = os.environ.get('TOUR_API_KEY', '').strip()
            if not key:
                raise FetchError('TOUR_API_KEY is not set')
            raw = collect_live(key, today)
        items = build_items(raw, today)
    except FetchError as e:
        print('error: %s -- keeping existing file' % e, file=sys.stderr)
        return 1
    if not items:
        print('error: 0 festivals collected -- keeping existing file', file=sys.stderr)
        return 1
    write_atomic(args.out, {'updated': now.isoformat(timespec='seconds'), 'source': SOURCE, 'items': items})
    print('wrote %d festivals to %s' % (len(items), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())

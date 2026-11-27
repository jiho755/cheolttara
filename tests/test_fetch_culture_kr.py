"""scripts/fetch_culture_kr.py 테스트 (네트워크 없음). 실행: python3 tests/test_fetch_culture_kr.py"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, 'tests', 'fixtures')
spec = importlib.util.spec_from_file_location('fetch_culture_kr', os.path.join(ROOT, 'scripts', 'fetch_culture_kr.py'))
kr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kr)
kr.RETRY_DELAY = 0
TODAY = '2026-11-24'
KEY = 'SECRET+KEY/123=abc'          # Decoding 키는 + / = 를 포함할 수 있다
A1, A2 = 'A=' + os.path.join(FIX, 'kr_culture_A_page1.xml'), 'A=' + os.path.join(FIX, 'kr_culture_A_page2.xml')
B1, C1 = 'B=' + os.path.join(FIX, 'kr_culture_B_page1.xml'), 'C=' + os.path.join(FIX, 'kr_culture_C_page1.xml')
CASING = os.path.join(FIX, 'kr_culture_casing.xml')
ERR, OAERR, EMPTY = (os.path.join(FIX, n) for n in ('kr_culture_error.xml', 'kr_culture_openapi_error.xml', 'kr_culture_empty.xml'))


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = kr.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def xml_page(rows, total, tag='item'):
    items = ''.join('<%s>%s</%s>' % (tag, ''.join('<%s>%s</%s>' % (k, v, k) for k, v in r.items()), tag) for r in rows)
    return ('<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>'
            '<body><items>%s</items><totalCount>%s</totalCount></body></response>' % (items, total)).encode()


def row(i, **kw):
    r = {'seq': str(i), 'title': 'T%s' % i, 'startDate': '20261201', 'endDate': '20261202', 'place': 'P', 'realmName': '전시',
         'area': '서울', 'sigungu': '종로구', 'gpsX': '126.9', 'gpsY': '37.5'}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, 'kr.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self):
        with open(self.out, encoding='utf-8') as f:
            return json.load(f)

    def by_title(self):
        return {i['title']: i for i in self.load()['items']}


class FixtureTests(Base):
    def gen(self, *extra):
        rc, out, err = run('--fixture', A1, A2, B1, C1, *extra, '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0, err)
        return out

    def test_mapping_and_filters(self):
        out = self.gen()
        d = self.load()
        self.assertEqual(d['source'], '한국문화정보원 한눈에보는문화정보')
        self.assertRegex(d['updated'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00$')
        items = d['items']
        self.assertEqual(len(items), 12)   # 17 rows - 중복 id - 제목/시작일 없음 - 종료 - 120일 밖 - 상설(2년)
        keys = {'id', 'cat', 'group', 'title', 'start', 'end', 'gu', 'sido', 'place', 'target', 'fee', 'free', 'time', 'image', 'link', 'lat', 'lng'}
        for i in items:
            self.assertEqual(set(i), keys)
            self.assertRegex(i['id'], r'^kc-[0-9A-Za-z]+$')
            self.assertRegex(i['start'], r'^\d{4}-\d\d-\d\d$')
            self.assertIsNone(i['free'])
            self.assertEqual((i['fee'], i['target'], i['time']), ('', '', ''))
        t = self.by_title()
        a = t['가을 사진전']
        self.assertEqual((a['id'], a['cat'], a['group'], a['sido'], a['gu'], a['start'], a['end'], a['place']),
                         ('kc-1001', '전시', 'exhibit', '강원', '춘천시', '2026-10-01', '2026-12-31', '춘천미술관'))
        self.assertEqual(a['link'], 'https://www.culture.go.kr/detail/1001')
        self.assertEqual(a['image'], 'https://cdn.example.kr/p/1001.jpg')   # http -> https
        self.assertEqual((a['lat'], a['lng']), (37.88, 127.73))
        for gone in ('지난 가을 조각전', '상설전시 한국의 역사', '먼 미래 연극', '시작일 없는 공연', '가을 사진전 (중복)'):
            self.assertNotIn(gone, t)
        self.assertIn('마지막 날 연극', t)                       # 종료일이 오늘이면 유지
        self.assertEqual(t['클래식 콘서트 & 토크']['start'], '2026-12-05')   # YYYY-MM-DD 입력도 받는다
        starts = [i['start'] for i in items]
        self.assertEqual(starts, sorted(starts))
        self.assertNotIn(KEY, out)

    def test_groups(self):
        self.gen()
        t = self.by_title()
        self.assertEqual(t['뮤지컬 <라이온>']['group'], 'show')
        self.assertEqual(t['국악 한마당']['group'], 'show')
        self.assertEqual(t['클래식 콘서트 & 토크']['group'], 'show')
        self.assertEqual(t['겨울 빛 축제']['group'], 'festival')
        self.assertEqual(t['청주 지역 행사']['group'], 'festival')   # serviceTp B
        self.assertEqual(t['도자기 만들기 체험']['group'], 'experience')
        self.assertEqual(t['주말 교실']['group'], 'experience')       # serviceTp C, realm 은 '기타'
        g = kr.group_of
        for realm, tp, want in (('전시', 'A', 'exhibit'), ('미술', 'A', 'exhibit'), ('연극', 'A', 'show'), ('뮤지컬', 'A', 'show'), ('음악', 'A', 'show'),
                                ('콘서트', 'A', 'show'), ('클래식', 'A', 'show'), ('국악', 'A', 'show'), ('무용', 'A', 'show'), ('공연', 'A', 'show'),
                                ('축제', 'A', 'festival'), ('지역행사', 'A', 'festival'), ('교육/체험', 'A', 'experience'), ('기타', 'A', 'etc'),
                                ('', 'A', 'etc'), (None, 'A', 'etc'), ('기타', 'B', 'festival'), ('기타', 'C', 'experience'), ('전시', 'B', 'festival'),
                                ('전시', 'C', 'experience')):
            self.assertEqual(g(realm, tp), want, (realm, tp))

    def test_sido(self):
        self.gen()
        t = self.by_title()
        want = {'가을 사진전': '강원', '뮤지컬 <라이온>': '부산', '국악 한마당': '광주', '마지막 날 연극': '경기', '일련번호 없는 무용': '제주',
                '청주 지역 행사': '충북', '주말 교실': '충남', '도자기 만들기 체험': '대전', '클래식 콘서트 & 토크': '서울'}
        for title, sido in want.items():
            self.assertEqual(t[title]['sido'], sido, title)
        self.assertEqual(kr.map_item({'title': 'x', 'startdate': '20261201', 'area': '어딘가'}, 'A')['sido'], '기타')

    def test_missing_seq_uses_sha1(self):
        self.gen()
        t = self.by_title()
        self.assertRegex(t['일련번호 없는 무용']['id'], r'^kc-[0-9a-f]{10}$')
        self.assertEqual(kr.make_id({}, 'A', '2026-12-10', 'P'), kr.make_id({}, 'A', '2026-12-10', 'P'))
        self.assertNotEqual(kr.make_id({}, 'A', '2026-12-10', 'P'), kr.make_id({}, 'A', '2026-12-11', 'P'))

    def test_coordinates(self):
        self.gen()
        t = self.by_title()
        sw = t['뮤지컬 <라이온>']        # 원본은 gpsX=35.16, gpsY=129.16 (뒤바뀜)
        self.assertEqual((sw['lat'], sw['lng']), (35.16, 129.16))
        self.assertEqual((t['주말 교실']['lat'], t['주말 교실']['lng']), (None, None))
        f = kr.fix_coords
        self.assertEqual(f('37.5', '127.0'), (37.5, 127.0))
        self.assertEqual(f('127.0', '37.5'), (37.5, 127.0))
        for bad in (('0', '0'), ('', ''), ('abc', '37'), ('50', '60'), ('nan', '127'), (None, None)):
            self.assertEqual(f(*bad), (None, None), bad)

    def test_link_only_if_http(self):
        m = kr.map_item
        base = {'title': 'x', 'startdate': '20261201'}
        self.assertEqual(m(dict(base), 'A')['link'], '')
        self.assertEqual(m(dict(base, url='javascript:alert(1)', homepage='ftp://x'), 'A')['link'], '')
        self.assertEqual(m(dict(base, url='www.example.kr'), 'A')['link'], '')
        self.assertEqual(m(dict(base, url='https://a.kr/x'), 'A')['link'], 'https://a.kr/x')
        self.assertEqual(m(dict(base, somefield='http://a.kr/y'), 'A')['link'], 'http://a.kr/y')   # 알려지지 않은 필드도 URL 이면
        self.assertEqual(m(dict(base, thumbnail='http://a.kr/t.jpg'), 'A')['link'], '')           # 이미지 URL 은 링크가 아니다

    def test_casing_and_aliases(self):
        rc, _, err = run('--fixture', CASING, '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0, err)
        t = self.by_title()
        a = t['대문자 태그 전시']
        self.assertEqual((a['id'], a['start'], a['place'], a['sido'], a['gu'], a['group']), ('kc-9001', '2026-11-25', '대구미술관', '대구', '수성구', 'exhibit'))
        self.assertEqual((a['image'], a['link']), ('https://cdn.example.kr/p/9001.jpg', 'http://www.example.kr/9001'))
        b = t['Mixed Case Concert']
        self.assertEqual((b['id'], b['place'], b['group'], b['sido'], b['lat'], b['lng']), ('kc-9002', '울산문예회관', 'show', '울산', 35.54, 129.33))

    def test_namespace_and_other_item_wrappers(self):
        raw = ('<ns:response xmlns:ns="urn:x"><ns:body><ns:items><ns:item><ns:seq>1</ns:seq><ns:title>NS 전시</ns:title>'
               '<ns:startDate>20261201</ns:startDate></ns:item></ns:items><ns:totalCount>1</ns:totalCount></ns:body></ns:response>').encode()
        items, total, summary = kr.parse_page(raw)
        self.assertEqual((len(items), total), (1, 1))
        self.assertEqual(items[0]['title'], 'NS 전시')
        self.assertIn('item', summary['tags'])
        items, _, _ = kr.parse_page(b'\xef\xbb\xbf' + xml_page([row(1)], 1))   # BOM
        self.assertEqual(len(items), 1)

    def test_diag_prints_structure_only(self):
        out = self.gen()
        self.assertIn('[diag] serviceTp=A http=fixture root=response', out)
        self.assertIn('first_item_children=seq,title,startDate', out)
        for tp in 'ABC':
            self.assertIn('serviceTp=%s' % tp, out)
        self.assertNotIn('가을 사진전', out)       # 값은 출력하지 않는다
        self.assertNotIn('1001', out)

    def test_failures_keep_existing_file(self):
        original = '{"updated": null, "source": "x", "items": []}\n'
        for name, path in (('error', ERR), ('openapi', OAERR), ('empty', EMPTY)):
            with open(self.out, 'w', encoding='utf-8') as f:
                f.write(original)
            rc, _, err = run('--fixture', path, '--today', TODAY, '--out', self.out)
            self.assertEqual(rc, 1, name)
            self.assertTrue(err.strip(), name)
            with open(self.out, encoding='utf-8') as f:
                self.assertEqual(f.read(), original, name)
        rc, _, err = run('--fixture', ERR, '--out', self.out)
        self.assertIn('SERVICE KEY IS NOT REGISTERED', err)
        rc, _, err = run('--fixture', OAERR, '--out', self.out)
        self.assertIn('API error', err)

    def test_failure_creates_no_file(self):
        for path in (ERR, OAERR, EMPTY):
            rc, _, _ = run('--fixture', path, '--out', self.out)
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(self.out))
            self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_all_filtered_missing_and_invalid(self):
        self.assertEqual(run('--fixture', A1, '--today', '2028-01-01', '--out', self.out)[0], 1)
        self.assertEqual(run('--fixture', os.path.join(self.tmp, 'nope.xml'), '--out', self.out)[0], 1)
        self.assertEqual(run('--fixture', A1, '--today', 'nope', '--out', self.out)[0], 1)
        bad = os.path.join(self.tmp, 'bad.xml')
        with open(bad, 'w') as f:
            f.write('<html>not xml')
        self.assertEqual(run('--fixture', bad, '--out', self.out)[0], 1)
        self.assertFalse(os.path.exists(self.out))

    def test_range_boundaries(self):
        def r(title, s, e):
            return {'title': title, 'startdate': s, 'enddate': e, 'place': 'x', 'realmname': '전시', 'seq': title}
        rows = [('A', r('정확히 120일 뒤 시작', '20270324', '20270330')), ('A', r('121일 뒤 시작', '20270325', '20270330')),
                ('A', r('365일 전시', '20261101', '20271101')), ('A', r('366일 전시', '20261101', '20271102')),
                ('A', r('종료일이 시작일보다 빠름', '20261201', '20261101')), ('A', {'title': '', 'startdate': '20261201'}), ('A', {'title': '날짜 없음'}),
                ('A', r('종료일 없음', '20261201', '')), ('A', r('잘못된 날짜', '20261301', '20261302'))]
        got = {i['title'] for i in kr.build_items(rows, kr.date(2026, 11, 24))}
        self.assertEqual(got, {'정확히 120일 뒤 시작', '365일 전시', '종료일이 시작일보다 빠름', '종료일 없음'})


class LiveLogicTests(Base):
    """http_get 을 바꿔치기해서 요청 파라미터·쪽 넘김·재시도·키 노출 여부를 확인한다 (실제 네트워크 없음)."""

    def setUp(self):
        super().setUp()
        self.orig = kr.http_get
        self.orig_key = os.environ.get('TOUR_API_KEY')
        os.environ['TOUR_API_KEY'] = KEY
        self.calls = []

    def tearDown(self):
        kr.http_get = self.orig
        if self.orig_key is None:
            os.environ.pop('TOUR_API_KEY', None)
        else:
            os.environ['TOUR_API_KEY'] = self.orig_key
        super().tearDown()

    @staticmethod
    def q(url):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)

    def serve(self, totals):
        """totals: serviceTp -> 전체 건수. 쪽 번호에 맞는 응답을 만든다."""
        def fake(url, timeout):
            self.assertEqual(timeout, 25)
            q = self.q(url)
            self.calls.append((q['serviceTp'][0], int(q['PageNo'][0])))
            tp, page, n = q['serviceTp'][0], int(q['PageNo'][0]), int(q['numOfrows'][0])
            total = totals[tp]
            lo, hi = (page - 1) * n, min(page * n, total)
            rows = [row('%s%d' % (tp, i), realmName='전시' if tp == 'A' else '축제' if tp == 'B' else '교육/체험') for i in range(lo, hi)]
            return 200, xml_page(rows, total)
        kr.http_get = fake

    def test_request_parameters(self):
        seen = []

        def fake(url, timeout):
            seen.append(url)
            return 200, xml_page([row(len(seen))], 1)
        kr.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(seen), 3)
        for tp, url in zip('ABC', seen):
            self.assertTrue(url.startswith('https://apis.data.go.kr/B553457/cultureinfo/period2?'))
            q = self.q(url)
            self.assertEqual(q['serviceKey'], [KEY])                  # 한 번만 인코딩 -> 디코드하면 원문
            self.assertIn(urllib.parse.quote(KEY, safe=''), url)
            self.assertNotIn(KEY, url)
            self.assertEqual((q['serviceTp'], q['PageNo'], q['numOfrows']), ([tp], ['1'], ['100']))
            self.assertEqual((q['from'], q['to']), (['20261124'], ['20270324']))
            self.assertEqual(set(q), {'serviceKey', 'serviceTp', 'PageNo', 'numOfrows', 'from', 'to'})
        self.assertNotIn(KEY, out + err)
        self.assertNotIn('apis.data.go.kr', out + err)
        self.assertIn('http=200', out)

    def test_pagination_by_total_count(self):
        self.serve({'A': 250, 'B': 100, 'C': 0 + 1})
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.calls, [('A', 1), ('A', 2), ('A', 3), ('B', 1), ('C', 1)])
        self.assertEqual(len(self.load()['items']), 351)
        self.assertNotIn(KEY, out + err)

    def test_stops_on_empty_page_when_total_unknown(self):
        def fake(url, timeout):
            q = self.q(url)
            page = int(q['PageNo'][0])
            self.calls.append((q['serviceTp'][0], page))
            rows = [row('%s-%d-%d' % (q['serviceTp'][0], page, i)) for i in range(3)] if page <= 2 else []
            return 200, xml_page(rows, 0)
        kr.http_get = fake
        rc, _, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual([c for c in self.calls if c[0] == 'A'], [('A', 1), ('A', 2), ('A', 3)])

    def test_page_cap(self):
        kr.MAX_PAGES = 4
        try:
            self.serve({'A': 99999, 'B': 1, 'C': 1})
            rc, _, _ = run('--today', TODAY, '--out', self.out)
        finally:
            kr.MAX_PAGES = 30
        self.assertEqual(rc, 0)
        self.assertEqual(len([c for c in self.calls if c[0] == 'A']), 4)

    def test_repeated_page_guard(self):
        def fake(url, timeout):                       # 서버가 PageNo 를 무시하고 같은 쪽을 계속 돌려줄 때
            self.calls.append(1)
            return 200, xml_page([row(i) for i in range(5)], 5000)
        kr.http_get = fake
        rc, _, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 6)          # 세 serviceTp 마다 2번 (두 번째에서 중복 감지)
        self.assertIn('repeated', err)
        self.assertEqual(len(self.load()['items']), 5)

    def test_call_budget(self):
        self.serve({'A': 3000, 'B': 3000, 'C': 3000})
        self.assertEqual(run('--today', TODAY, '--out', self.out)[0], 0)
        self.assertEqual(len(self.calls), 90)         # serviceTp 마다 최대 30쪽

    def test_retry_once_then_success(self):
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            if state['n'] == 1:
                raise urllib.error.URLError('boom ' + url)
            return 200, xml_page([row(state['n'])], 1)
        kr.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(state['n'], 4)               # A 는 2번(1회 재시도), B·C 는 1번씩
        self.assertNotIn(KEY, out + err)
        self.assertNotIn('boom', out + err)

    def test_retry_exhausted_keeps_file_and_hides_key(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            raise urllib.error.URLError('down ' + url)
        kr.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertEqual(state['n'], 6)               # serviceTp 3개 x (1 + 재시도 1)
        self.assertNotIn(KEY, out + err)
        self.assertNotIn(urllib.parse.quote(KEY, safe=''), out + err)
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_http_error_and_key_in_message_hidden(self):
        def fake(url, timeout):
            raise urllib.error.HTTPError(url, 500, 'err ' + url, {}, None)
        kr.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertIn('HTTP 500', err)
        self.assertNotIn(KEY, out + err)
        self.assertNotIn('serviceKey', out + err)
        # API 오류 문구에 키가 섞여 와도 가려진다
        leak = ('<response><header><resultCode>30</resultCode><resultMsg>bad %s</resultMsg></header></response>' % KEY).encode()
        kr.http_get = lambda url, timeout: (200, leak)
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertNotIn(KEY, out + err)

    def test_api_error_garbage_and_empty_keep_file(self):
        for payload in (read_bytes(ERR), read_bytes(OAERR), read_bytes(EMPTY), b'<html>not xml', b''):
            with open(self.out, 'w', encoding='utf-8') as f:
                f.write('KEEP')
            kr.http_get = lambda url, timeout, p=payload: (200, p)
            rc, out, err = run('--today', TODAY, '--out', self.out)
            self.assertEqual(rc, 1)
            self.assertNotIn(KEY, out + err)
            with open(self.out, encoding='utf-8') as f:
                self.assertEqual(f.read(), 'KEEP')

    def test_one_service_type_failing_aborts_without_writing(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')

        def fake(url, timeout):
            q = self.q(url)
            if q['serviceTp'][0] == 'B':
                return 200, b'garbage'
            return 200, xml_page([row(q['serviceTp'][0])], 1)
        kr.http_get = fake
        rc, _, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_diagnose_mode_writes_nothing(self):
        self.serve({'A': 500, 'B': 500, 'C': 500})
        rc, out, _ = run('--today', TODAY, '--out', self.out, '--diagnose')
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 3)
        self.assertFalse(os.path.exists(self.out))
        self.assertIn('nothing written', out)

    def test_missing_key(self):
        os.environ.pop('TOUR_API_KEY')
        kr.http_get = lambda *a, **k: self.fail('network must not be called')
        rc, _, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertIn('TOUR_API_KEY', err)
        self.assertFalse(os.path.exists(self.out))

    def test_cross_tp_duplicate_ids_collapse(self):
        kr.http_get = lambda url, timeout: (200, xml_page([row(7)], 1))   # 세 serviceTp 가 같은 seq
        rc, _, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.load()['items']), 1)


class CommittedFileTests(unittest.TestCase):
    def test_committed_data_file_shape(self):
        with open(os.path.join(ROOT, 'data', 'culture_kr.json'), encoding='utf-8') as f:
            d = json.load(f)
        self.assertEqual(set(d), {'updated', 'source', 'items'})
        self.assertEqual(d['source'], '한국문화정보원 한눈에보는문화정보')
        for i in d['items']:
            self.assertTrue(i['id'].startswith('kc-'))


if __name__ == '__main__':
    unittest.main(verbosity=1)

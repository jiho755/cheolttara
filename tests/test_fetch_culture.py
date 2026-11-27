"""scripts/fetch_culture_seoul.py 테스트 (네트워크 없음). 실행: python3 tests/test_fetch_culture.py"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, 'tests', 'fixtures')
spec = importlib.util.spec_from_file_location('fetch_culture_seoul', os.path.join(ROOT, 'scripts', 'fetch_culture_seoul.py'))
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
fc.RETRY_DELAY = 0
TODAY = '2026-11-24'
P1, P2 = os.path.join(FIX, 'seoul_culture_page1.json'), os.path.join(FIX, 'seoul_culture_page2.json')
ERR, EMPTY = os.path.join(FIX, 'seoul_culture_error.json'), os.path.join(FIX, 'seoul_culture_empty.json')
KEY = 'SECRETKEY123abc'


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fc.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, 'culture.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self):
        with open(self.out, encoding='utf-8') as f:
            return json.load(f)

    def by_title(self):
        return {i['title']: i for i in self.load()['items']}


class FixtureTests(Base):
    def test_mapping_and_filters(self):
        rc, _, _ = run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        d = self.load()
        self.assertEqual(d['source'], '서울특별시 문화행사 정보 (공공누리 제1유형)')
        self.assertRegex(d['updated'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00$')
        items = d['items']
        self.assertEqual(len(items), 21)   # 25 - 상설(2년) - 종료 - 120일 밖 - 중복 id
        keys = {'id', 'cat', 'group', 'title', 'start', 'end', 'gu', 'place', 'target', 'fee', 'free', 'time', 'image', 'link', 'lat', 'lng'}
        for i in items:
            self.assertEqual(set(i), keys)
            self.assertRegex(i['id'], r'^seoul-[0-9a-f]{10}$')
            self.assertRegex(i['start'], r'^\d{4}-\d\d-\d\d$')
        t = self.by_title()
        a = t['가을 서울 사진전']
        self.assertEqual((a['cat'], a['group'], a['gu'], a['start'], a['end'], a['free']), ('전시/미술', 'exhibit', '종로구', '2026-10-20', '2026-12-20', True))
        self.assertEqual(a['place'], '서울시립미술관 서소문본관')
        self.assertEqual(a['time'], '10:00~20:00')
        self.assertTrue(a['link'].startswith('https://culture.seoul.go.kr/'))
        self.assertFalse(t['빛의 정원 미디어아트전']['free'])
        # 걸러짐
        for gone in ('상설전시 서울의 역사', '지난 가을 조각전', '먼 미래 여름 콘서트'):
            self.assertNotIn(gone, t)
        self.assertEqual(sum(1 for i in items if i['title'] == '가을 서울 사진전'), 1)
        # 종료일이 오늘이면 유지
        self.assertIn('마지막 날 연극', t)
        # start 순 정렬
        starts = [i['start'] for i in items]
        self.assertEqual(starts, sorted(starts))

    def test_group_mapping(self):
        g = fc.group_of
        for c in ('전시/미술',):
            self.assertEqual(g(c), 'exhibit')
        for c in ('연극', '뮤지컬/오페라', '무용', '국악', '클래식', '콘서트', '독주/독창회', '영화'):
            self.assertEqual(g(c), 'show', c)
        self.assertEqual(g('교육/체험'), 'experience')
        self.assertEqual(g('축제-문화/예술'), 'festival')
        self.assertEqual(g('축제-시민화합'), 'festival')
        self.assertEqual(g('축제'), 'festival')
        self.assertEqual(g('기타'), 'etc')
        self.assertEqual(g(''), 'etc')
        self.assertEqual(g(None), 'etc')
        rc, _, _ = run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        t = self.by_title()
        self.assertEqual(t['서울 빛초롱축제']['group'], 'festival')
        self.assertEqual(t['신촌 겨울 거리 축제']['cat'], '축제-시민화합')
        self.assertEqual(t['골목 투어 걷기']['group'], 'etc')
        self.assertEqual(t['가족 도자기 만들기 체험']['group'], 'experience')
        self.assertEqual(t['바이올린 독주회']['group'], 'show')

    def test_cleaning(self):
        run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        t = self.by_title()
        self.assertIn('점심시간 클래식', t)             # 공백 정리
        self.assertEqual(t['점심시간 클래식']['place'], '양천문화회관')
        self.assertEqual(t['크리스마스 뮤지컬 콘서트']['image'], 'https://culture.seoul.go.kr/img/musical.jpg')   # http -> https
        self.assertEqual(t['빛의 정원 미디어아트전']['image'], '')   # 이미지 없음
        for i in t.values():
            self.assertFalse(i['image'].startswith('http://'))
            for k in ('target', 'fee', 'time'):
                self.assertLessEqual(len(i[k]), 80)
        self.assertGreater(len(t['신년 클래식 음악회']['fee']), 70)   # 긴 요금은 80자까지만
        self.assertTrue(t['신년 클래식 음악회']['fee'].startswith('R석 150,000원'))
        # 문화포털 링크가 없으면 기관 링크
        self.assertEqual(t['금천 거리 공연']['link'], 'https://www.geumcheon.go.kr/')

    def test_coordinate_fix(self):
        run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        t = self.by_title()
        sw = t['어린이 과학 체험 교실']      # 원본은 LAT=126.9066, LOT=37.5264
        self.assertEqual((sw['lat'], sw['lng']), (37.5264, 126.9066))
        ok = t['가을 서울 사진전']
        self.assertEqual((ok['lat'], ok['lng']), (37.5665, 126.978))
        none = t['금천 거리 공연']
        self.assertEqual((none['lat'], none['lng']), (None, None))
        f = fc.fix_coords
        self.assertEqual(f('37.5', '127.0'), (37.5, 127.0))
        self.assertEqual(f('127.0', '37.5'), (37.5, 127.0))
        self.assertEqual(f('0', '0'), (None, None))
        self.assertEqual(f('', ''), (None, None))
        self.assertEqual(f('abc', '37'), (None, None))
        self.assertEqual(f('50', '60'), (None, None))   # 범위 밖

    def test_id_stability(self):
        run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        a = {i['title']: i['id'] for i in self.load()['items']}
        out2 = os.path.join(self.tmp, 'again.json')
        run('--fixture', P1, P2, '--today', '2026-11-25', '--out', out2)   # 날짜가 달라도 같은 행사는 같은 id
        with open(out2, encoding='utf-8') as f:
            b = {i['title']: i['id'] for i in json.load(f)['items']}
        for title, i in b.items():
            self.assertEqual(a[title], i)
        self.assertEqual(len(set(a.values())), len(a))
        self.assertEqual(fc.make_id('A', '2026-01-01 00:00:00.0', 'P'), fc.make_id(' A ', '2026-01-01 00:00:00.0', ' P '))
        self.assertNotEqual(fc.make_id('A', '2026-01-01 00:00:00.0', 'P'), fc.make_id('A', '2026-01-02 00:00:00.0', 'P'))

    def test_range_boundaries(self):
        rows = []

        def row(title, s, e):
            return {'TITLE': title, 'STRTDATE': s + ' 00:00:00.0', 'END_DATE': e + ' 00:00:00.0', 'PLACE': 'x', 'CODENAME': '전시/미술'}
        rows.append(row('정확히 120일 뒤 시작', '2027-03-24', '2027-03-30'))
        rows.append(row('121일 뒤 시작', '2027-03-25', '2027-03-30'))
        rows.append(row('365일 전시', '2026-11-01', '2027-11-01'))
        rows.append(row('366일 전시', '2026-11-01', '2027-11-02'))
        rows.append(row('종료일이 시작일보다 빠름', '2026-12-01', '2026-11-01'))
        rows.append({'TITLE': '', 'STRTDATE': '2026-12-01 00:00:00.0'})
        rows.append({'TITLE': '날짜 없음'})
        got = {i['title'] for i in fc.build_items(rows, fc.date(2026, 11, 24))}
        self.assertEqual(got, {'정확히 120일 뒤 시작', '365일 전시', '종료일이 시작일보다 빠름'})

    def test_failures_keep_existing_file(self):
        original = '{"updated": null, "source": "x", "items": []}\n'
        for name, path in (('error', ERR), ('empty', EMPTY)):
            with open(self.out, 'w', encoding='utf-8') as f:
                f.write(original)
            rc, _, err = run('--fixture', path, '--today', TODAY, '--out', self.out)
            self.assertEqual(rc, 1, name)
            self.assertTrue(err.strip(), name)
            with open(self.out, encoding='utf-8') as f:
                self.assertEqual(f.read(), original, name)
        rc, _, err = run('--fixture', ERR, '--out', self.out)
        self.assertIn('INFO-100', err)

    def test_failure_creates_no_file(self):
        for path in (ERR, EMPTY):
            rc, _, _ = run('--fixture', path, '--out', self.out)
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(self.out))
            self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_all_filtered_is_failure(self):
        rc, _, _ = run('--fixture', P1, '--today', '2028-01-01', '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))

    def test_missing_fixture_file(self):
        rc, _, _ = run('--fixture', os.path.join(self.tmp, 'nope.json'), '--out', self.out)
        self.assertEqual(rc, 1)

    def test_invalid_today(self):
        rc, _, _ = run('--fixture', P1, '--today', 'nope', '--out', self.out)
        self.assertEqual(rc, 1)


class ParseTests(unittest.TestCase):
    def test_parse(self):
        ok = {'culturalEventInfo': {'list_total_count': 1, 'RESULT': {'CODE': 'INFO-000', 'MESSAGE': 'ok'}, 'row': [{'TITLE': 'a'}]}}
        rows, total = fc.parse_response(ok)
        self.assertEqual((len(rows), total), (1, 1))
        self.assertEqual(fc.parse_response({'culturalEventInfo': {'RESULT': {'CODE': 'INFO-200', 'MESSAGE': 'none'}}}), ([], 0))
        for bad in ({'RESULT': {'CODE': 'INFO-100', 'MESSAGE': 'bad key'}}, {'culturalEventInfo': {'RESULT': {'CODE': 'ERROR-500', 'MESSAGE': 'x'}}},
                    {}, [], 'x', {'culturalEventInfo': 5}):
            with self.assertRaises(fc.FetchError):
                fc.parse_response(bad)

    def test_url_shape(self):
        url = fc.build_url('KEY', 1001, 2000)
        self.assertEqual(url, 'http://openapi.seoul.go.kr:8088/KEY/json/culturalEventInfo/1001/2000/')


class LiveLogicTests(Base):
    """http_get 을 바꿔치기해서 쪽 넘김·재시도·키 노출 여부를 확인한다 (실제 네트워크 없음)."""

    def setUp(self):
        super().setUp()
        self.orig = fc.http_get
        self.orig_key = os.environ.get('SEOUL_API_KEY')
        os.environ['SEOUL_API_KEY'] = KEY
        self.urls = []

    def tearDown(self):
        fc.http_get = self.orig
        if self.orig_key is None:
            os.environ.pop('SEOUL_API_KEY', None)
        else:
            os.environ['SEOUL_API_KEY'] = self.orig_key
        super().tearDown()

    @staticmethod
    def body(start, end, total):
        n = max(0, min(end, total) - start + 1)
        rows = [{'CODENAME': '전시/미술', 'GUNAME': '종로구', 'TITLE': 'T%d' % (start + i), 'PLACE': 'P', 'STRTDATE': '2026-12-01 00:00:00.0',
                 'END_DATE': '2026-12-02 00:00:00.0', 'IS_FREE': '무료', 'LAT': '37.5', 'LOT': '126.9'} for i in range(n)]
        return json.dumps({'culturalEventInfo': {'list_total_count': total, 'RESULT': {'CODE': 'INFO-000', 'MESSAGE': 'ok'}, 'row': rows}}).encode()

    @staticmethod
    def range_of(url):
        parts = url.rstrip('/').split('/')
        return int(parts[-2]), int(parts[-1])

    def test_pagination(self):
        def fake(url, timeout):
            self.urls.append(url)
            self.assertEqual(timeout, 30)
            s, e = self.range_of(url)
            return self.body(s, e, 2500)
        fc.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual([self.range_of(u) for u in self.urls], [(1, 1000), (1001, 2000), (2001, 3000)])
        self.assertTrue(all(('/%s/json/culturalEventInfo/' % KEY) in u and u.startswith('http://openapi.seoul.go.kr:8088/') for u in self.urls))
        self.assertEqual(len(self.load()['items']), 2500)
        self.assertNotIn(KEY, out + err)

    def test_single_page_when_small(self):
        def fake(url, timeout):
            self.urls.append(url)
            s, e = self.range_of(url)
            return self.body(s, e, 7)
        fc.http_get = fake
        rc, _, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.urls), 1)

    def test_retry_once_then_success(self):
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            if state['n'] == 1:
                raise urllib.error.URLError('boom ' + url)
            s, e = self.range_of(url)
            return self.body(s, e, 5)
        fc.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(state['n'], 2)
        self.assertNotIn(KEY, out + err)

    def test_retry_exhausted_keeps_file_and_hides_key(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            raise urllib.error.URLError('down ' + url)       # 예외 문구에 URL(키)이 섞여 와도
        fc.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertEqual(state['n'], fc.RETRIES + 1)
        self.assertNotIn(KEY, out + err)                      # 출력에는 나오지 않아야 한다
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_http_error_hides_key(self):
        def fake(url, timeout):
            raise urllib.error.HTTPError(url, 500, 'err ' + url, {}, None)
        fc.http_get = fake
        rc, out, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertIn('HTTP 500', err)
        self.assertNotIn(KEY, out + err)

    def test_api_error_and_empty_keep_file(self):
        for payload in (read_bytes(ERR), read_bytes(EMPTY), b'<html>not json</html>'):
            with open(self.out, 'w', encoding='utf-8') as f:
                f.write('KEEP')
            fc.http_get = lambda url, timeout, p=payload: p
            rc, out, err = run('--today', TODAY, '--out', self.out)
            self.assertEqual(rc, 1)
            self.assertNotIn(KEY, out + err)
            with open(self.out, encoding='utf-8') as f:
                self.assertEqual(f.read(), 'KEEP')

    def test_second_page_failure_aborts_without_writing(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')

        def fake(url, timeout):
            s, e = self.range_of(url)
            if s == 1001:
                return b'garbage'
            return self.body(s, e, 1500)
        fc.http_get = fake
        rc, _, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_missing_key(self):
        os.environ.pop('SEOUL_API_KEY')
        fc.http_get = lambda *a, **k: self.fail('network must not be called')
        rc, _, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertIn('SEOUL_API_KEY', err)
        self.assertFalse(os.path.exists(self.out))


if __name__ == '__main__':
    unittest.main(verbosity=1)

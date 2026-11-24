"""scripts/fetch_festivals.py 테스트 (네트워크 없음). 실행: python3 tests/test_fetch.py"""
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
spec = importlib.util.spec_from_file_location('fetch_festivals', os.path.join(ROOT, 'scripts', 'fetch_festivals.py'))
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)
ff.RETRY_DELAY = 0
TODAY = '2026-11-24'
P1, P2 = os.path.join(FIX, 'searchFestival2_page1.json'), os.path.join(FIX, 'searchFestival2_page2.json')


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = ff.main(list(argv))
    return rc, err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, 'festivals.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self):
        with open(self.out, encoding='utf-8') as f:
            return json.load(f)

    def by_id(self):
        return {i['id']: i for i in self.load()['items']}


class FixtureTests(Base):
    def test_page1_mapping(self):
        rc, _ = run('--fixture', P1, '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        d = self.load()
        self.assertEqual(d['source'], '한국관광공사 TourAPI')
        self.assertRegex(d['updated'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00$')
        ids = self.by_id()
        self.assertEqual(len(ids), 15)
        for i in d['items']:
            self.assertEqual(set(i), {'id', 'title', 'start', 'end', 'addr', 'sido', 'image', 'tel', 'mapx', 'mapy'})
        # 제목 정리 / 날짜 / 주소 합치기
        self.assertEqual(ids['141001']['title'], '서울빛초롱축제')
        self.assertEqual(ids['141001']['start'], '2026-11-06')
        self.assertEqual(ids['141004']['addr'], '경기도 수원시 팔달구 정조로 825 (행궁동)')
        self.assertEqual(ids['141005']['title'], '강릉 겨울 바다 축제')
        # sido 정규화
        self.assertEqual(ids['141001']['sido'], '서울')
        self.assertEqual(ids['141002']['sido'], '강원')
        self.assertEqual(ids['141003']['sido'], '전북')
        self.assertEqual(ids['141011']['sido'], '세종')
        self.assertEqual(ids['141007']['sido'], '제주')
        self.assertEqual(ids['141006']['sido'], '부산')
        # addr 없음 -> lDongRegnCd 로 보완
        self.assertEqual(ids['141005']['addr'], '')
        self.assertEqual(ids['141005']['sido'], '강원')
        # 이미지: http -> https, 없으면 ""
        self.assertTrue(ids['141001']['image'].startswith('https://'))
        self.assertEqual(ids['141004']['image'], '')
        # 좌표: float, 없으면 null
        self.assertIsInstance(ids['141001']['mapx'], float)
        self.assertIsNone(ids['141013']['mapx'])
        self.assertIsNone(ids['141013']['mapy'])
        self.assertEqual(ids['141013']['tel'], '')
        # start 순 정렬
        starts = [i['start'] for i in d['items']]
        self.assertEqual(starts, sorted(starts))

    def test_two_pages_dedupe_and_range(self):
        rc, _ = run('--fixture', P1, P2, '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        ids = self.by_id()
        self.assertEqual(len(ids), 17)               # 15 + 울산 + 기타 (중복 1, 180일 밖 1 제외)
        self.assertEqual(len(self.load()['items']), 17)
        self.assertNotIn('141016', ids)               # 시작이 180일 넘게 뒤
        self.assertIn('141015', ids)                  # 약 128일 뒤
        self.assertIn('141012', ids)                  # 약 4개월 뒤
        self.assertEqual(ids['141017']['sido'], '기타')

    def test_boundary_180_days(self):
        # 141016 은 2027-06-30 시작 -> 기준일이 2026-12-31 이면 181일 이내가 아님, 2027-01-01 이면 180일 이내
        rc, _ = run('--fixture', P1, P2, '--today', '2027-01-01', '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertIn('141016', self.by_id())

    def test_single_object_item(self):
        rc, _ = run('--fixture', os.path.join(FIX, 'searchFestival2_single.json'), '--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.load()['items']), 1)

    def test_ended_festival_dropped(self):
        rc, _ = run('--fixture', P1, '--today', '2026-12-08', '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertNotIn('141001', self.by_id())      # 12/05 종료

    def test_failures_keep_existing_file(self):
        original = '{"updated": null, "source": "한국관광공사 TourAPI", "items": []}\n'
        for name in ('error', 'error_openapi', 'empty'):
            with open(self.out, 'w', encoding='utf-8') as f:
                f.write(original)
            rc, err = run('--fixture', os.path.join(FIX, 'searchFestival2_%s.json' % name), '--today', TODAY, '--out', self.out)
            self.assertEqual(rc, 1, name)
            self.assertTrue(err.strip(), name)
            with open(self.out, encoding='utf-8') as f:
                self.assertEqual(f.read(), original, name)

    def test_failure_creates_no_file(self):
        rc, _ = run('--fixture', os.path.join(FIX, 'searchFestival2_error.json'), '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_all_out_of_range_is_failure(self):
        rc, _ = run('--fixture', P1, '--today', '2026-04-05', '--out', self.out)   # 모두 180일 밖
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))

    def test_missing_fixture_file(self):
        rc, _ = run('--fixture', os.path.join(self.tmp, 'nope.json'), '--out', self.out)
        self.assertEqual(rc, 1)


class UnitTests(unittest.TestCase):
    def test_normalize_sido(self):
        n = ff.normalize_sido
        self.assertEqual(n('서울특별시 중구 세종대로'), '서울')
        self.assertEqual(n('강원특별자치도 강릉시'), '강원')
        self.assertEqual(n('강원도 강릉시'), '강원')
        self.assertEqual(n('전북특별자치도 전주시'), '전북')
        self.assertEqual(n('전라북도 전주시'), '전북')
        self.assertEqual(n('세종특별자치시 한누리대로'), '세종')
        self.assertEqual(n('충청북도 청주시'), '충북')
        self.assertEqual(n('경상남도 통영시'), '경남')
        self.assertEqual(n('제주특별자치도 제주시'), '제주')
        self.assertEqual(n('', '51'), '강원')
        self.assertEqual(n('', '42'), '강원')
        self.assertEqual(n('', '52'), '전북')
        self.assertEqual(n('', '45'), '전북')
        self.assertEqual(n('엉뚱한 주소', '11110'), '서울')
        self.assertEqual(n('엉뚱한 주소', ''), '기타')
        self.assertEqual(n('', None), '기타')

    def test_clean_title(self):
        self.assertEqual(ff.clean_title('  [서울]  빛 축제 '), '빛 축제')
        self.assertEqual(ff.clean_title('빛 축제 [2026]'), '빛 축제')
        self.assertEqual(ff.clean_title('[전부 대괄호]'), '[전부 대괄호]')

    def test_url_encodes_key_once(self):
        url = ff.build_url('a+b/c==', 2, ff.date(2026, 11, 24))
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(qs['serviceKey'], ['a+b/c=='])
        self.assertIn('serviceKey=a%2Bb%2Fc%3D%3D', url)
        self.assertEqual(qs['eventStartDate'], ['20261124'])
        self.assertEqual(qs['numOfRows'], ['100'])
        self.assertEqual(qs['pageNo'], ['2'])
        self.assertEqual(qs['_type'], ['json'])
        self.assertNotIn('areaCode', qs)
        self.assertNotIn('lDongRegnCd', qs)


class LiveLogicTests(Base):
    """http_get 을 바꿔치기해서 쪽 넘김·재시도를 확인한다 (실제 네트워크 없음)."""

    def setUp(self):
        super().setUp()
        self.orig = ff.http_get
        self.orig_key = os.environ.get('TOUR_API_KEY')
        os.environ['TOUR_API_KEY'] = 'test-key'
        self.calls = []

    def tearDown(self):
        ff.http_get = self.orig
        if self.orig_key is None:
            os.environ.pop('TOUR_API_KEY', None)
        else:
            os.environ['TOUR_API_KEY'] = self.orig_key
        super().tearDown()

    @staticmethod
    def page_body(page, total):
        n = max(0, min(100, total - (page - 1) * 100))
        items = [{'contentid': str((page - 1) * 100 + i), 'title': 'T%d' % ((page - 1) * 100 + i), 'eventstartdate': '20261201',
                  'eventenddate': '20261202', 'addr1': '서울특별시 중구 1', 'firstimage': '', 'tel': '', 'mapx': '126.9', 'mapy': '37.5'}
                 for i in range(1, n + 1)]
        body = {'response': {'header': {'resultCode': '0000', 'resultMsg': 'OK'},
                             'body': {'items': {'item': items} if items else '', 'numOfRows': 100, 'pageNo': page, 'totalCount': total}}}
        return json.dumps(body).encode()

    def test_pagination(self):
        def fake(url, timeout):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            self.calls.append(int(qs['pageNo'][0]))
            self.assertEqual(timeout, 20)
            return self.page_body(int(qs['pageNo'][0]), 250)
        ff.http_get = fake
        rc, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [1, 2, 3])
        self.assertEqual(len(self.load()['items']), 250)

    def test_retry_once_then_success(self):
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            if state['n'] == 1:
                raise urllib.error.URLError('boom')
            return self.page_body(1, 5)
        ff.http_get = fake
        rc, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 0)
        self.assertEqual(state['n'], 2)

    def test_retry_exhausted_keeps_file(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')
        state = {'n': 0}

        def fake(url, timeout):
            state['n'] += 1
            raise urllib.error.URLError('down')
        ff.http_get = fake
        rc, err = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertEqual(state['n'], 2)               # 1회 + 재시도 1회
        self.assertNotIn('test-key', err)
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_second_page_failure_aborts_without_writing(self):
        with open(self.out, 'w', encoding='utf-8') as f:
            f.write('KEEP')

        def fake(url, timeout):
            page = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['pageNo'][0])
            if page == 2:
                return b'<xml>not json</xml>'
            return self.page_body(page, 150)
        ff.http_get = fake
        rc, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        with open(self.out, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'KEEP')

    def test_missing_key(self):
        os.environ.pop('TOUR_API_KEY')
        ff.http_get = lambda *a, **k: self.fail('network must not be called')
        rc, _ = run('--today', TODAY, '--out', self.out)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))


if __name__ == '__main__':
    unittest.main(verbosity=1)

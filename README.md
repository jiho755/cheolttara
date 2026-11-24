# 철따라

이번 철에만 즐길 수 있는 제철 음식·자연·행사를 모아 보여주고, 해본 것은 도장으로 남기는 제철 버킷리스트 PWA입니다.

## 기능
- **이번 달**: 월 선택(이번 달부터 12개월) + 지역 칩. 축제·행사 / 가볼 만한 곳 / 제철 음식 / 자연을 한 화면에, 상세 시트에서 네이버 지도 링크
- **버킷리스트**: 담기, "해냈어요" 도장 + 사진 1장 + 한 줄 메모
- **도장판**: 계절별 도장판, 올해의 제철 카드 이미지 만들기
- **알림**: 담아둔 항목(축제는 시작·종료 3일 전)의 임박 알림 (앱을 열 때)

## 구조
- 프레임워크·빌드 없음 (HTML/CSS/JS), 오프라인 동작 (service worker)
- 데이터: `data/seasonal_items.json` (명세: `docs/DATA_SPEC.md`), `data/places.json` (큐레이션 명소), `data/festivals.json` (자동 생성, 손으로 수정 금지)
- v2 명세: `docs/SPEC_V2.md`
- 기록은 기기 안(IndexedDB)에만 저장
- 테스트 날짜 지정: `?date=2026-04-05`

## 축제 데이터 (한국관광공사)
축제·행사 정보는 한국관광공사 TourAPI(KorService2 `searchFestival2`)에서 가져옵니다. 자료: 한국관광공사.

- `scripts/fetch_festivals.py` (표준 라이브러리만)가 전국 축제를 받아 `data/festivals.json` 을 만듭니다. 수집 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1로 끝납니다.
- GitHub Actions(`.github/workflows/festivals.yml`)가 매일 03:00 KST(18:00 UTC)에 실행해 `data/festivals.json` 이 바뀌면 커밋·푸시합니다.
- 준비: 저장소 Settings > Secrets and variables > Actions 에 `TOUR_API_KEY`(공공데이터포털 **Decoding** 키)를 등록하세요.
- 수동 실행: GitHub 저장소의 **Actions** 탭 > "Update festivals" > **Run workflow**.
- 로컬 실행: `TOUR_API_KEY=... python3 scripts/fetch_festivals.py` / 네트워크 없이: `python3 scripts/fetch_festivals.py --fixture tests/fixtures/searchFestival2_page1.json --out /tmp/f.json`

## 테스트
```
cd /tmp && python3 -I /path/to/tests/test.py        # UI (Playwright, 390x844)
python3 -I /path/to/tests/test_fetch.py             # 수집 스크립트 (네트워크 없음)
```

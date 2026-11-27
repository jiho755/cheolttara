# 철따라

이번 철에만 즐길 수 있는 제철 음식·자연·행사를 모아 보여주고, 해본 것은 도장으로 남기는 제철 버킷리스트 PWA입니다.

## 기능
- **이번 달**: 월 선택(이번 달부터 12개월) + 지역 칩. 축제·행사 / 가볼 만한 곳 / 제철 음식 / 자연을 한 화면에, 상세 시트에서 네이버 지도 링크
- **버킷리스트**: 담기, "해냈어요" 도장 + 사진 1장 + 한 줄 메모
- **도장판**: 계절별 도장판, 올해의 제철 카드 이미지 만들기
- **알림**: 담아둔 항목(축제는 시작·종료 3일 전)의 임박 알림 (앱을 열 때)

## 구조
- 프레임워크·빌드 없음 (HTML/CSS/JS), 오프라인 동작 (service worker)
- 데이터: `data/seasonal_items.json` (명세: `docs/DATA_SPEC.md`), `data/places.json` (큐레이션 명소), `data/festivals.json`·`data/culture_seoul.json` (자동 생성, 손으로 수정 금지)
- v3 명세: `docs/SPEC_V3_CULTURE.md`
- v2 명세: `docs/SPEC_V2.md`
- 기록은 기기 안(IndexedDB)에만 저장
- 테스트 날짜 지정: `?date=2026-04-05`

## 축제 데이터 (한국관광공사)
축제·행사 정보는 한국관광공사 TourAPI(KorService2 `searchFestival2`)에서 가져옵니다. 자료: 한국관광공사.

- `scripts/fetch_festivals.py` (표준 라이브러리만)가 전국 축제를 받아 `data/festivals.json` 을 만듭니다. 수집 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1로 끝납니다.
- GitHub Actions(`.github/workflows/festivals.yml`, "Update events")가 매일 03:00 KST(18:00 UTC)에 축제·서울 문화행사를 각각 수집하고, 바뀐 데이터 파일을 커밋·푸시합니다. 한쪽이 실패해도 다른 쪽은 커밋되며, 실패한 step 이 있으면 마지막에 job 을 실패로 표시합니다.
- 준비: 저장소 Settings > Secrets and variables > Actions 에 `TOUR_API_KEY`(공공데이터포털 **Decoding** 키)를 등록하세요.
- 수동 실행: GitHub 저장소의 **Actions** 탭 > "Update events" > **Run workflow**.
- 로컬 실행: `TOUR_API_KEY=... python3 scripts/fetch_festivals.py` / 네트워크 없이: `python3 scripts/fetch_festivals.py --fixture tests/fixtures/searchFestival2_page1.json --out /tmp/f.json`

## 공연·전시 데이터 (서울특별시)
서울 열린데이터광장 '서울시 문화행사 정보'(`culturalEventInfo`)로 공연·전시·체험(민간 포함)을 보강합니다. 자료: 서울특별시 (공공누리 제1유형). 화면의 🎭 공연·전시 섹션은 지역 칩이 전체·수도권일 때만 보이고, 서울 축제는 🎉 축제·행사에 합쳐집니다. 명세: `docs/SPEC_V3_CULTURE.md`

- `scripts/fetch_culture_seoul.py` (표준 라이브러리만)가 `data/culture_seoul.json` 을 만듭니다. 실패·0건이면 기존 파일을 유지하고 종료코드 1. 키가 URL 에 들어가므로 URL 은 로그에 출력하지 않습니다.
- 준비: 저장소 Settings > Secrets and variables > Actions 에 `SEOUL_API_KEY`(서울 열린데이터광장 인증키)를 등록하세요.
- 로컬 실행: `SEOUL_API_KEY=... python3 scripts/fetch_culture_seoul.py` / 네트워크 없이: `python3 scripts/fetch_culture_seoul.py --fixture tests/fixtures/seoul_culture_page1.json --out /tmp/c.json`

## 앱(APK)
사이트(https://jiho755.github.io/cheolttara/)를 WebView 로 감싼 최소 Android 앱이 `android/` 에 있습니다. (AndroidX·Kotlin 없음, 순수 프레임워크 API)

- `.github/workflows/android.yml` 이 `android/**`, `app.js` 변경 시(또는 수동 실행) 서명된 APK 를 빌드해 Releases 의 **apk-latest** 에 `cheolttara.apk` 로 올립니다. 버전은 `2.0.<빌드 번호>`.
- 설치: Releases > apk-latest 에서 `cheolttara.apk` 다운로드 → 출처를 알 수 없는 앱 설치 허용 → 설치. 업데이트는 같은 방법으로 덮어쓰기.
- 서명 키(`android/keystore/cheolttara-sideload.jks`)는 사이드로드용으로 저장소에 포함돼 있습니다. 스토어 배포용 키가 아닙니다.
- 앱에서는 `window.CheolttaraAndroid.saveImage(base64, 파일명)` 브리지로 제철 카드를 갤러리(Pictures/철따라)에 저장하고, Notification API 가 없어 알림 토글은 비활성화됩니다.
- 로컬 빌드(Android SDK + Gradle 8.7+): `VERSION_CODE=1 gradle -p android assembleRelease`

## 테스트
```
cd /tmp && python3 -I /path/to/tests/test.py        # UI (Playwright, 390x844)
python3 -I /path/to/tests/test_fetch.py             # 축제 수집 스크립트 (네트워크 없음)
python3 -I /path/to/tests/test_fetch_culture.py     # 서울 문화행사 수집 스크립트 (네트워크 없음)
```

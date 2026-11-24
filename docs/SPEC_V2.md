# 철따라 v2 명세 — 월별로 "지금 할 수 있는 것" 알려주기

v1의 문제: 무엇이 제철인지만 알려줘서 "어디서, 언제"는 사용자가 따로 검색해야 함.
v2 목표: 달을 고르면 그 달의 **축제·행사 / 가볼 만한 곳 / 제철 음식 / 자연**을 장소·기간·지도 링크까지 한 화면에서 보여준다.

---

## 1. 데이터 파일

### 1-1. `data/seasonal_items.json` (기존 파일 확장)
기존 필드는 그대로 두고 아래만 추가한다.
- food 항목: `origin` (string, 30자 이내, 유명 산지. 예: "포항 구룡포", "전국" 금지), `dishes` (string 배열 2~3개, 각 15자 이내. 예: ["과메기 쌈", "과메기 무침"])
- nature 항목: `spots` (string 배열, `places.json`의 id 0~3개)

### 1-2. `data/places.json` (신규, 큐레이션)
JSON 배열. 항목:
| 필드 | 타입 | 규칙 |
|---|---|---|
| id | string | `place-{영문슬러그}`, 중복 금지 |
| name | string | 명소 이름. 예: "내장산 국립공원" |
| sido | string | 시도 표준명 17개 중 하나: 서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주 |
| sigungu | string | 시군구. 예: "정읍시" |
| months | number[] | 가기 가장 좋은 달 (1~3개) |
| when | string | 사람이 읽는 시기. 예: "10월 말~11월 초" (20자 이내) |
| summary | string | 40자 이내 |
| tip | string | 60자 이내. 실용 팁 (주차, 시간대, 혼잡 등) |
| related | string[] | 관련 seasonal item id 0~3개 (예: `nature-maple-hike`) |

구성: 총 84곳, 매달 정확히 7곳(months 첫 값 기준). 매달 수도권(서울·경기·인천) 최소 2곳, 나머지는 지역 고르게. 계절 명소(꽃·단풍·설경·해돋이·바다 등) 중심, 매년 같은 시기에 가볼 이유가 있는 곳만.

### 1-3. `data/festivals.json` (신규, 자동 생성 — 손으로 수정 금지)
```json
{ "updated": "2026-11-24T03:00:00+09:00", "source": "한국관광공사 TourAPI",
  "items": [ { "id": "141105", "title": "...", "start": "2026-12-01", "end": "2026-12-31",
               "addr": "서울특별시 중구 ...", "sido": "서울", "image": "https://...", "tel": "02-...",
               "mapx": 126.97, "mapy": 37.56 } ] }
```
초기 커밋은 `{"updated": null, "source": "한국관광공사 TourAPI", "items": []}`.

---

## 2. 축제 자동 수집

### 2-1. `scripts/fetch_festivals.py` (표준 라이브러리만)
- 엔드포인트: `https://apis.data.go.kr/B551011/KorService2/searchFestival2`
- 파라미터: `serviceKey`(환경변수 `TOUR_API_KEY`, Decoding 키 — urlencode로 한 번만 인코딩), `MobileOS=ETC`, `MobileApp=cheolttara`, `_type=json`, `arrange=A`, `numOfRows=100`, `pageNo`, `eventStartDate=오늘(KST, YYYYMMDD)`.
  - eventStartDate=오늘이면 오늘 이후에도 열려 있는 행사만 온다.
  - **areaCode·lDongRegnCd로 서버 필터를 걸지 않는다** (KorService2에서 areaCode 필터는 0건을 반환하는 알려진 문제). 전국을 받아서 클라이언트에서 지역을 판별한다.
- 응답: `response.body.items.item` (리스트 또는 단일 객체). 결과 0건이면 `items`가 빈 문자열 `""`로 올 수 있다. 오류 시 최상위 구조가 다르다(`OpenAPI_ServiceResponse` 또는 `response.header.resultCode != "0000"`) → 오류로 처리.
- `totalCount`로 쪽수 계산, 모든 쪽 수집. 쪽마다 실패 시 1회 재시도(timeout 20초).
- 필드 매핑: contentid→id, title(앞뒤 공백·대괄호 정리), eventstartdate/eventenddate(YYYYMMDD→YYYY-MM-DD), addr1(+addr2)→addr, firstimage→image(`http://`는 `https://`로 바꿈, 없으면 ""), tel, mapx/mapy(float, 없으면 null).
- sido 판별: addr1 첫 단어를 표준명으로 정규화(예: "서울특별시"→서울, "강원특별자치도"→강원, "전북특별자치도"→전북, "세종특별자치시"→세종). 실패 시 lDongRegnCd 앞 두 자리로 보완(강원 42/51, 전북 45/52 둘 다). 그래도 모르면 "기타".
- 보관 범위: start가 오늘로부터 180일 이내인 것만. 중복 id 제거. start 순 정렬.
- **안전장치**: 수집 실패·0건이면 기존 `data/festivals.json`을 덮어쓰지 않고 종료코드 1.
- `--fixture 파일경로` 옵션: 네트워크 대신 저장된 응답 JSON으로 실행(테스트용).

### 2-2. `.github/workflows/festivals.yml`
- 트리거: 매일 18:00 UTC(= 03:00 KST) + `workflow_dispatch`(수동 실행)
- `permissions: contents: write`
- 단계: checkout → `python3 scripts/fetch_festivals.py` (env `TOUR_API_KEY: ${{ secrets.TOUR_API_KEY }}`) → 변경 있으면 `data/festivals.json`만 커밋·푸시 (커밋 작성자 github-actions[bot])

---

## 3. 화면

하단 탭 4개 유지: **이번 달**(기존 "이번 철" 대체) / 버킷리스트 / 도장판 / 알림.

### 3-1. 이번 달 (홈)
- 상단: 월 선택 띠(가로 스크롤). 이번 달부터 12개월(예: 11월…10월), 해가 바뀌면 "1월 ’27"처럼 연도 표시. 기본 선택 = 이번 달.
- 지역 칩: 전체 / 수도권(서울·경기·인천) / 강원 / 충청(대전·세종·충북·충남) / 전라(광주·전북·전남) / 경상(부산·대구·울산·경북·경남) / 제주. 선택값은 localStorage에 기억. 축제와 명소에만 적용(음식·자연은 전국).
- 섹션 순서 (비어 있으면 섹션 숨김, 단 축제는 안내 문구 표시):
  1. **🎉 축제·행사**: 선택한 달과 기간이 겹치는 festivals. 정렬: 진행 중 → 시작일 순. 카드: 썸네일(이미지 없거나 로딩 실패 시 🎉 자리표시), 제목, 기간, "시군 · 진행 중" 또는 "D-12", 종료 7일 이내면 "곧 끝나요". 처음 10개 + "더 보기". 그 아래 소제목 "절기·세시풍속"으로 기존 event 항목(seasonal_items) 표시.
     - festivals가 비었거나 선택한 달이 수집 범위(180일) 밖이면: "축제 일정은 보통 1~2달 전에 확정돼요. 가까워지면 자동으로 채워져요."
  2. **📍 가볼 만한 곳**: months에 선택한 달이 있는 places. 카드: 이름, "시도 시군 · when", summary.
  3. **🍓 제철 음식**: 선택한 달과 겹치는 food. 카드에 origin 표시("📍 포항 구룡포").
  4. **🌸 자연**: 선택한 달과 겹치는 nature. spots가 있으면 "명소 2곳" 표시.
- "곧 끝나요/곧 시작해요" 배지는 선택한 달이 이번 달일 때만.
- 하단 작은 글씨: "축제 정보 업데이트: 11/24 · 자료: 한국관광공사"

### 3-2. 상세 시트 (탭하면 열림)
- 공통: ♡ 버킷 담기, "해냈어요"(기존 도장 흐름) 
- 축제: 이미지(있으면), 기간, 주소, 전화(텍스트로 표시 + tel: 링크), **지도 보기** 버튼 → `https://map.naver.com/p/search/{encodeURIComponent(title)}` (새 탭, 일반 a href), "자료: 한국관광공사"
- 명소: when, summary, tip, 관련 제철 항목 칩(탭하면 그 항목 시트), **지도 보기** → 네이버 지도 검색(`name + ' ' + sigungu`)
- 음식: summary, tip, 산지, 추천 요리 칩
- 자연: summary, tip, 연결된 명소 카드(탭하면 명소 시트)

### 3-3. 버킷리스트·도장판·알림
- 버킷에 담는 키에 종류 접두어: seasonal item은 기존 id 그대로(`food-…` 등, 기존 데이터 호환), 명소는 `place-…`, 축제는 `fest-{contentid}`. 축제는 담을 때 title/start/end/addr를 함께 저장(나중에 festivals.json에서 빠져도 표시 가능).
- 버킷 그룹: 기존과 같되 축제는 실제 날짜, 명소는 months 기준으로 판단.
- 도장판: 계절 보드 4개(기존 seasonal item)는 유지, 아래에 "다녀온 곳" 보드 추가(도장 찍힌 명소·축제).
- 알림: 담아둔 축제의 시작 3일 전·종료 3일 전 알림 추가.

## 4. 호환·제약
- 기존 저장 데이터(IndexedDB `cheolttara`, 버킷 id)가 깨지지 않을 것.
- 프레임워크·빌드·외부 요청 없음(이미지 제외). 축제 이미지는 외부 URL이므로 service worker 캐시 대상에서 제외하고 `loading="lazy"`, onerror 시 자리표시.
- 테스트 날짜 지정 `?date=YYYY-MM-DD` 유지.

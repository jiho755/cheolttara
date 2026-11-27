# 철따라 v3 — 서울 문화행사(공연·전시) 추가

목표: 관광공사 축제에 없는 공연·전시·체험(민간 포함)을 서울시 문화행사 API로 보강한다. 양이 많으므로 화면에서는 걸러서 조금만 보여준다.

## 1. 데이터 수집 — `scripts/fetch_culture_seoul.py` (표준 라이브러리만)
- 엔드포인트: `http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/culturalEventInfo/{start}/{end}/` (HTTP, 포트 8088. 한 번에 최대 1000건)
- 키: 환경변수 `SEOUL_API_KEY` (URL 경로에 그대로 들어감 — 로그에 URL을 출력하지 말 것)
- 응답: `culturalEventInfo.list_total_count`, `culturalEventInfo.RESULT.CODE`("INFO-000" 정상, "INFO-200" 데이터 없음, 그 외 오류), `culturalEventInfo.row[]`. 키 오류 등은 최상위에 `RESULT`만 오는 경우도 있음 → 오류 처리.
- 전체 건수(약 2만)를 1000건씩 모두 받아 클라이언트에서 거른다. 쪽마다 1회 재시도, timeout 30초.
- row 주요 필드: CODENAME(분류), GUNAME(자치구), TITLE, DATE("YYYY-MM-DD~YYYY-MM-DD"), PLACE, ORG_NAME, USE_TRGT(대상), USE_FEE(요금), MAIN_IMG, STRTDATE/END_DATE("YYYY-MM-DD HH:MM:SS.0"), IS_FREE("무료"/"유료"), ORG_LINK(기관 홈페이지), HMPG_ADDR(문화포털 상세 URL), PRO_TIME(행사시간), LAT/LOT(좌표 — 두 값이 뒤바뀌어 오는 경우가 있으니 범위로 판별: 위도 33~39, 경도 124~132).
- 보관 조건: 종료일 ≥ 오늘(KST) 그리고 시작일 ≤ 오늘+120일. 기간이 365일을 넘는 상설 전시는 제외.
- 출력 `data/culture_seoul.json`:
```json
{ "updated": "...", "source": "서울특별시 문화행사 정보 (공공누리 제1유형)",
  "items": [ { "id": "seoul-<sha1(TITLE|STRTDATE|PLACE) 앞 10자>", "cat": "전시/미술", "group": "exhibit",
               "title": "...", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "gu": "종로구", "place": "...",
               "target": "...", "fee": "...", "free": true, "time": "...", "image": "https://...",
               "link": "문화포털 상세 URL 또는 기관 링크", "lat": 37.5, "lng": 126.9 } ] }
```
  - group 매핑: 전시/미술→exhibit; 연극·뮤지컬/오페라·무용·국악·클래식·콘서트·독주/독창회·영화→show; 교육/체험→experience; CODENAME이 "축제"로 시작→festival; 그 외→etc.
  - 문자열 앞뒤 공백 정리, 이미지 http→https, 중복 id 제거, 시작일 순 정렬. target/fee/time은 각 80자에서 자르기.
- 안전장치: 실패·0건이면 기존 파일을 덮어쓰지 않고 종료코드 1. `--fixture`, `--out`, `--today` 옵션(기존 fetch_festivals.py와 같은 방식).
- 초기 커밋 파일: `{"updated": null, "source": "서울특별시 문화행사 정보 (공공누리 제1유형)", "items": []}`

## 2. 워크플로
`.github/workflows/festivals.yml`을 확장 (이름은 "Update events"로 변경, 파일명 유지):
- 축제 수집과 서울 수집을 각각 별도 step으로, `continue-on-error: true` — 하나가 실패해도 다른 하나는 커밋된다.
- 마지막 step에서 두 파일 중 바뀐 것만 커밋(메시지 "chore: update events data").
- 서울 step env: `SEOUL_API_KEY: ${{ secrets.SEOUL_API_KEY }}`.
- 마지막에 두 수집 step 중 하나라도 실패했으면 job을 실패로 표시(커밋은 이미 끝난 뒤) — 사용자가 Actions 탭에서 알아챌 수 있게.

## 3. 화면 (이번 달 탭)
- 새 섹션 **🎭 공연·전시** — 축제·행사 섹션 바로 아래. 지역 칩이 "전체" 또는 "수도권"일 때만 표시(서울 데이터뿐이므로). 섹션 제목 옆 작은 글씨 "서울".
- 섹션 안 필터 칩: 추천(기본) / 무료 / 전시 / 공연 / 체험 / 아이와 함께.
  - 추천: 무료 우선 → 선택한 달에 시작하거나 그 달 안에 끝나는 것 우선 → 기간이 짧은 것 우선. 처음 8개 + "더 보기"(8개씩).
  - 아이와 함께: target에 "어린이|아동|가족|유아|초등|누구나|전체" 포함.
- 대상: 선택한 달과 기간이 겹치는 항목 중 group이 festival이 아닌 것.
- group=festival인 항목은 **🎉 축제·행사 섹션에 합친다** (sido 서울). 관광공사 축제와 제목이 같으면(공백·괄호·특수문자 제거 후 비교) 서울 항목은 버린다.
- 카드: 썸네일(없으면 🎭), 제목, "구 · 장소", 기간, 배지(무료 / 진행 중 / D-n / 곧 끝나요).
- 상세 시트: 이미지, 분류, 기간, 시간, 장소(구), 대상, 요금, **자세히 보기**(link, 새 탭) 버튼, **지도 보기**(좌표 있으면 `https://map.naver.com/p/search/` + encodeURIComponent(place), 없어도 place로 검색), ♡ 담기·해냈어요, "자료: 서울특별시(공공누리 제1유형)".
- 버킷: id `seoul-…`, 담을 때 title/start/end/place/gu 저장(축제와 같은 방식). 도장판 "다녀온 곳"에 포함. 알림: 축제와 같은 규칙.
- 하단 업데이트 표시: "축제 11/27 · 공연·전시 11/27 · 자료: 한국관광공사, 서울특별시"
- `sw.js` 캐시 버전 올리고 `data/culture_seoul.json`을 festivals.json과 같이 network-first.
- 성능: culture_seoul.json이 1MB 안팎일 수 있음. 홈 첫 렌더를 막지 않도록 축제·명소를 먼저 그리고 공연·전시는 로드 후 채운다.

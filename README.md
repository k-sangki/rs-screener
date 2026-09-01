# RS Screener

한국 주식의 상대강도(RS)를 검색·정렬·필터링하는 정적 웹 스크리너입니다. 프론트엔드는 별도 빌드 없이 GitHub Pages에서 실행되고, GitHub Actions가 평일 장 마감 후 KRX 데이터를 갱신합니다.

## 현재 기능

- 종목명·종목코드·시장·테마 검색
- RS 70/80/90 필터와 전체 열 정렬
- Minervini Trend Template, VCP, 포켓 피봇, 이동평균 정배열 필터
- 52주 고가, RS Line 신고가 근접, RS 70 신규 진입 판정
- 시가총액 구간, 관심종목, 최대 4개 종목 비교 선택
- 다크 모드와 반응형 표
- KR/US 분리 구조(US 데이터는 다음 단계에서 추가)

## RS 계산

63거래일 수익률 40%, 126·189·252거래일 수익률을 각각 20%로 가중한 뒤 유효 종목 집합에서 0~99 백분위로 변환합니다. 252거래일 이력이 없거나 최근 종가가 5,000원 미만인 종목은 공개 목록에서 제외합니다.

## 로컬 실행

```bash
python -m http.server 8000
```

브라우저에서 `http://localhost:8000`을 엽니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 데이터 갱신

```bash
pip install -r requirements.txt
python scripts/collect_kr.py
```

평일 18:45 KST에 `.github/workflows/update-kr-data.yml`이 자동 실행됩니다. 첫 실행은 전체 가격 이력을 수집하므로 시간이 오래 걸릴 수 있고, 이후 실행은 Actions 캐시를 이용해 누락 구간만 추가합니다.

## 주의

RS와 파생 신호는 과거 가격 기반의 탐색 도구이며 매수·매도 신호가 아닙니다. KRX 또는 데이터 제공처의 응답 변경, 기업행동, 거래정지 등에 따라 값이 달라질 수 있습니다.

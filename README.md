# 공공 AX 사례 찾기

공공기관의 AI 도입 담당자가 문장으로 물으면, 다른 기관이 실제로 발주한 AI 관련 용역 사업 중 의미가 가까운 것을 찾아 주는 웹앱이다. KAIST ITM.690 실습 2-(ii) 과제.

- 데이터: 조달청 나라장터 발주계획현황서비스(공공데이터포털 15129462) 용역 중 AI 관련 사업 5,593건, 2024-01 ~ 2026-09 발주 예정분
- 방식: 사업명을 임베딩(qwen/qwen3-embedding-8b, 앞 1,024차원)해 두고, 질의 문장도 같은 방식으로 임베딩해 코사인 유사도 순으로 보여 준다
- 브라우저에는 키가 없다. 질의 문장만 서버로 가고, 서버가 OpenRouter 임베딩 API를 부른다

## 로컬에서 실행

필요한 것: Python 3 (3.14에서 확인), OpenRouter API 키

```bash
python -m venv .venv
.venv/Scripts/activate        # macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
```

키를 환경변수로 넣는다 (PowerShell 예: `$env:OPENROUTER_API_KEY = "sk-or-..."`). 키를 코드나 파일에 적지 않는다.

```bash
python app.py                 # http://127.0.0.1:8000
python search_core.py "민원 상담 챗봇을 도입한 기관"   # 화면 없이 검색만 확인
```

## Vercel 배포

1. GitHub 계정으로 Vercel에 가입한다
2. 이 폴더를 GitHub 저장소로 올린다 (`data/` 색인 파일 포함, 키 파일 제외)
3. Vercel → Add New → Project → 저장소 Import. Application Preset은 Flask
4. Environment Variables에 `OPENROUTER_API_KEY` 입력 → Deploy
5. 받은 주소를 휴대폰 등 다른 기기에서 열어 검색이 되는지 확인한다

Vercel은 `app.py`의 Flask 인스턴스 `app`을 찾아 함수 하나로 실행하고, `public/` 파일은 CDN에서 직접 내보낸다.

## 환경변수

| 이름 | 용도 |
| --- | --- |
| `OPENROUTER_API_KEY` | 질의 문장 임베딩. OpenRouter에서 키 사용 한도를 걸어 둔다 |

## 파일

| 파일 | 내용 |
| --- | --- |
| `app.py` | Flask 서버. `/`(화면), `/api/search?q=`(검색) |
| `search_core.py` | 질의 임베딩과 유사도 검색 |
| `public/index.html` | 검색 화면 |
| `data/vectors.f16`, `data/docs.json`, `data/index.meta.json` | 색인 (공개 정보만, 담당자 이름·연락처 없음) |
| `build_index.py` | 과제 1 임베딩에서 색인을 다시 만든다. 상위 폴더 `../data`가 있어야 한다 |

색인 다시 만들기: `python build_index.py --source all --dim 1024`

## 자주 나는 문제

- "OPENROUTER_API_KEY 환경변수가 없습니다": 환경변수를 넣지 않았다. Vercel에서는 넣은 뒤 다시 배포해야 반영된다
- 검색이 15초 넘게 걸리다 실패: 임베딩 API가 가끔 응답하지 않는다. 서버가 한 번 다시 묻고, 그래도 안 되면 "잠시 뒤 다시 시도" 메시지를 낸다
- 결과가 이상하다: 사업명만으로 찾기 때문에 이름이 짧거나 일반적인 사업은 잘 걸리지 않는다. 같은 사업이 두 번 나오기도 한다 (정정 공고 등)

## 한계

- 발주계획은 사전 계획이라 실제 입찰공고·계약과 1:1이 아니다
- 사업 개요 필드가 비어 있어 사업명만 임베딩했다
- 결과는 정보 제공용이다. 조달·기술 자문이 아니다

결정과 이유는 DECISIONS.md, 계획은 PLAN.md에 있다.

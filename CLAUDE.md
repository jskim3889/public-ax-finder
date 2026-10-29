# 작업 규칙 (공공 AX 사례 찾기 웹앱)

## 구조

- `app.py`: Flask 서버. Vercel이 이 파일의 `app`을 함수로 실행한다
- `search_core.py`: 질의 임베딩 + 코사인 유사도. 로컬 서버와 Vercel이 함께 쓴다
- `public/index.html`: 검색 화면. Vercel은 `public/`을 CDN에서 직접 내보낸다
- `data/`: 색인. `build_index.py`가 상위 폴더 `../data`(과제 1 산출물)에서 만든다
- 문서: PLAN.md(계획), DECISIONS.md(결정 기록, 아래로만 추가), README.md(실행·배포)

## 규칙

- 키는 환경변수 `OPENROUTER_API_KEY`로만 읽는다. 코드, 저장소, 브라우저 JS에 넣지 않는다
- 질의 임베딩은 색인과 같은 모델(qwen/qwen3-embedding-8b), 같은 차원 자르기(앞 1,024차원 후 정규화)를 쓴다. 모델이나 차원을 바꾸면 색인을 다시 만든다
- 상위 폴더 `../data`, `../scripts`는 과제 1 작업 영역이다. 이 폴더에서 고치지 않고 읽기만 한다
- 색인과 화면에 담당자 이름·연락처를 넣지 않는다
- Flask `static_folder`를 쓰지 않는다 (Vercel 문서 권고). 정적 파일은 `public/`에 둔다
- 결정을 바꾸면 DECISIONS.md에 날짜·결정·이유·버린 대안을 덧붙인다

## 자주 쓰는 명령

```bash
.venv/Scripts/python app.py                                  # 로컬 서버 :8000
.venv/Scripts/python search_core.py "질의 문장"               # 검색만 확인
.venv/Scripts/python build_index.py --source all --dim 1024   # 색인 다시 만들기
```

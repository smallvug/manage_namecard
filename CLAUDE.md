# 명함 정리 (manage_namecard)

## 프로젝트 개요

명함 사진을 사람별 폴더로 자동 분류·저장하는 GUI 프로그램.
Claude Vision API로 명함 이미지를 분석해 폴더명을 생성하고, 앞면/뒷면을 자동 감지한다.

> **CLAUDE.md 업데이트 규칙**: 이 파일은 사용자가 명시적으로 요청할 때만 업데이트한다. 작업 완료 후 자동으로 업데이트하지 않는다. 단, git 푸시 전에는 반드시 CLAUDE.md를 최신 상태로 업데이트한다.

- **환경**: Python 3.14, Windows 10
- **주요 라이브러리**: anthropic, Pillow, python-dotenv
- **실행**: `명함정리.vbs` 더블클릭 (콘솔 창 없음, `.venv` 자동 사용)
- **API 키**: `.env` 파일에 `ANTHROPIC_API_KEY=` 형식으로 저장 (git 제외)

## 폴더 구조

```
manage_namecard/
├── _data/          # 처리할 명함 사진 (git 제외)
├── _processed/     # 분류 결과 (git 제외)
├── .env            # API 키 (git 제외)
├── .venv/          # 가상환경 (git 제외)
├── manage_gui.py   # GUI 메인 프로그램
├── manage.py       # CLI 버전
├── requirements.txt
└── 명함정리.vbs    # 더블클릭 실행기
```

## 폴더명 규칙

- **한국인**: `성 이름, 기관, 직책`  예) `강 남규, 연세대학교, 교수`
- **외국인**: `성(대문자) 이름, 기관, 직책`  예) `GLASS John, MIT, Professor`
- 부서가 있으면 콤마로 추가

## 파일명 규칙

```
[YYYY.MM.DD] 명함 1.JPG   ← 앞면
[YYYY.MM.DD] 명함 2.JPG   ← 뒷면
```

## 핵심 구조

### GUI (manage_gui.py)

- `PanedWindow` 레이아웃: 왼쪽(목록·입력·버튼·로그) / 오른쪽(이미지 캔버스)
- **앞면 분석**: `analyze_namecard()` → Claude Vision으로 폴더명 생성
- **뒷면 자동 감지**: `check_is_back()` → 다음 이미지가 같은 명함인지 확인, 감지 시 위아래 분할 표시
- **스레딩**: API 호출은 daemon 스레드로 처리, `root.after(0, ...)` 로 UI 업데이트
- **창 위치**: 닫을 때 `.window_pos.json` 저장, 재시작 시 복원

### VBScript 런처 (명함정리.vbs)

- `WScript.ScriptFullName` 으로 스크립트 경로 취득
- `pythonw.exe` + `Run ... 0, False` 로 콘솔 창 완전 숨김

## 진행 상황

### 1. 초기 구현 (v0.1.0)

- Claude Vision API (`claude-opus-4-6`) 로 명함 분석 및 폴더명 생성
- VBScript 더블클릭 런처 (콘솔 없음)
- GUI: 이미지 목록, 폴더명 입력, 뒷면 번호 입력, 저장/뒷면추가/건너뜀 버튼
- 뒷면 자동 감지: 다음 이미지를 미리 분석해 앞/뒷면 여부 판별, 위아래 분할 표시
- 기존 폴더에 추가 (뒷면 추가) 팝업: 최근 폴더 볼드·선택, 메인 창 가운데 배치
- 창 위치/크기 자동 저장·복원

## 다음 단계

1. **드래그 앤 드롭**: 이미지 직접 끌어다 놓기
2. **일괄 처리**: 여러 장 선택 후 한 번에 처리
3. **검색**: 기존 폴더 검색 필터

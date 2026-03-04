# 명함 정리 (manage_namecard)

명함 사진을 사람별 폴더로 자동 분류·저장하는 Windows GUI 프로그램.
Claude Vision API가 명함 이미지를 인식해 폴더명을 자동 생성하고, 앞면/뒷면을 자동으로 감지한다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **AI 명함 인식** | Claude Vision(`claude-opus-4-6`)이 이름·기관·직책을 읽어 폴더명 자동 생성 |
| **앞뒷면 자동 감지** | 다음 사진이 같은 명함의 뒷면인지 자동 판별, 위아래로 나란히 표시 |
| **폴더명 자동 제안** | 분석 결과를 입력창에 채워 넣어 바로 저장 또는 수정 가능 |
| **기존 폴더에 추가** | 이미 저장된 폴더에 뒷면/추가 사진을 붙일 수 있는 선택 팝업 |
| **파일명 자동 결정** | EXIF 촬영일 기준 `[YYYY.MM.DD] 명함 N.JPG` 형식으로 저장 |
| **썸네일 목록** | 이미지 목록에 미리보기 썸네일 표시, 클릭 시 자동 분석 시작 |
| **키보드 단축키** | `Enter` 저장 / `Space` 건너뜀 / `B` 뒷면추가 |
| **창 위치 저장** | 프로그램 종료 시 위치·크기를 저장, 재시작 시 그대로 복원 |

---

## 사전 준비

### 1. Python 3.x 설치

Python 3.9 이상 권장. [python.org](https://www.python.org/downloads/) 에서 설치.

### 2. 가상환경 생성 및 패키지 설치

```bat
cd manage_namecard
python -m venv .venv
.venv\Scripts\activate
pip install anthropic Pillow python-dotenv
```

### 3. Anthropic API 키 설정

프로젝트 루트에 `.env` 파일을 만들고 아래 내용을 입력한다.

```env
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxx
```

API 키는 [Anthropic Console](https://console.anthropic.com/) 에서 발급받는다.

---

## 실행 방법

### 방법 1: VBScript 더블클릭 (권장)

`명함정리.vbs` 를 더블클릭.
콘솔 창 없이 GUI만 바로 실행된다. 별도의 가상환경 활성화 불필요.

### 방법 2: 터미널

```bat
.venv\Scripts\activate
python manage_gui.py
```

---

## 사용 흐름

```
_data/ 에 명함 사진 넣기
          ↓
프로그램 실행 → 썸네일 목록에서 사진 클릭
          ↓
AI가 자동으로 명함 분석 → 폴더명 자동 입력
          ↓
필요하면 폴더명 수정 → [저장] 또는 Enter
          ↓
_processed/폴더명/[날짜] 명함 1.JPG 저장
```

### 버튼 및 단축키

| 버튼 | 단축키 | 동작 |
|------|--------|------|
| **저장** | `Enter` | 입력된 폴더명으로 `_processed/` 에 저장 |
| **뒷면 추가** | `B` | 기존 폴더를 선택해 현재 사진을 뒷면으로 추가 |
| **건너뜀** | `Space` | 현재 사진을 분류하지 않고 다음으로 넘김 |

> **참고**: `Space` / `B` 단축키는 폴더명 입력창에 포커스가 있을 때는 일반 타이핑으로 동작합니다.

---

## 폴더/파일 명명 규칙

### 폴더명

- **한국인**: `성 이름, 기관, 직책`
  - 예) `강 남규, 연세대학교, 교수`
  - 예) `김 민수, 삼성전자 반도체사업부, 수석연구원`
- **외국인**: `성(대문자) 이름, 기관, 직책`
  - 예) `GLASS John, MIT, Professor`

### 파일명

```
[2024.03.15] 명함 1.JPG   ← 앞면 (또는 단면)
[2024.03.15] 명함 2.JPG   ← 뒷면
```

같은 폴더에 추가 저장 시 번호가 자동으로 이어진다 (`명함 3.JPG`, `명함 4.JPG` …).

---

## 폴더 구조

```
manage_namecard/
├── _data/              # ★ 처리할 명함 사진을 여기에 넣는다 (git 제외)
├── _processed/         # ★ 분류 결과가 저장된다 (git 제외)
│   ├── 강 남규, 연세대학교, 교수/
│   │   ├── [2024.03.15] 명함 1.JPG
│   │   └── [2024.03.15] 명함 2.JPG
│   └── GLASS John, MIT, Professor/
│       └── [2024.01.20] 명함 1.JPG
├── .env                # API 키 (git 제외)
├── .venv/              # 가상환경 (git 제외)
├── manage_gui.py       # GUI 메인 프로그램
├── manage.py           # CLI 버전 (일괄 처리)
├── requirements.txt    # 패키지 목록
└── 명함정리.vbs        # 더블클릭 실행기
```

---

## 동작 원리

### 명함 분석 (`analyze_namecard`)

1. 사진을 Base64로 인코딩
2. Claude Vision API(`claude-opus-4-6`)에 이미지와 프롬프트 전송
3. AI가 이름·기관·직책을 추출해 `성 이름, 기관, 직책` 형식으로 반환
4. 반환 문자열을 폴더명으로 사용

### 앞뒷면 자동 감지 (`check_is_back`)

1. 현재 사진(앞면)과 다음 사진 두 장을 함께 API에 전송
2. "같은 명함의 앞면과 뒷면입니까?" 질의
3. "예"이면 두 사진을 위아래로 나란히 표시하고 함께 저장

### 스레딩

API 호출은 별도 daemon 스레드에서 실행되어 UI가 멈추지 않는다.
결과는 `root.after(0, ...)` 를 통해 메인 스레드에서 안전하게 UI에 반영한다.

---

## 환경

- **OS**: Windows 10 이상
- **Python**: 3.9+
- **주요 라이브러리**: `anthropic`, `Pillow`, `python-dotenv`
- **API**: Anthropic Claude Vision (`claude-opus-4-6`)

---

## 라이선스

MIT

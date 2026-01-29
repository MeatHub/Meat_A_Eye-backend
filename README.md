# Meat-A-Eye Backend

Meat-A-Eye 프로젝트의 백엔드 서버입니다. FastAPI 기반으로 구축되었으며, Next.js 프론트엔드와 연동됩니다.

## 기술 스택

- **Framework**: FastAPI
- **Database**: MySQL (SQLAlchemy 2.0 + aiomysql)
- **Authentication**: JWT (python-jose)
- **AI Server**: FastAPI (포트 8001)
- **External APIs**: 축산물 이력제 API, KAMIS API

## 프로젝트 구조

```
Meat_A_Eye-backend/
├── meat_backend/
│   ├── config/          # 설정 (CORS, DB, 환경 변수)
│   ├── models/          # SQLAlchemy 모델
│   ├── routes/          # API 라우터
│   │   ├── api.py       # /api 엔드포인트 (프론트엔드 호환)
│   │   └── v1/          # /api/v1 엔드포인트
│   ├── schemas/         # Pydantic 스키마
│   ├── services/        # 비즈니스 로직 (AI 프록시, 이력제 API 등)
│   └── middleware/     # 미들웨어 (JWT, 에러 핸들러)
├── sql/                 # 데이터베이스 마이그레이션
├── run.py              # 서버 실행 스크립트
└── requirements.txt    # Python 의존성

```

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 환경 변수를 설정하세요. 자세한 내용은 [ENV_SETUP.md](./ENV_SETUP.md)를 참조하세요.

필수 환경 변수:
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- `JWT_SECRET`
- `CORS_ORIGINS` (프론트엔드 도메인)
- `AI_SERVER_URL` (AI 서버 주소, 기본값: http://localhost:8001)

### 3. 데이터베이스 설정

MySQL 데이터베이스를 생성하고 마이그레이션을 실행하세요:

```bash
mysql -u root -p < sql/001_schema.sql
mysql -u root -p < sql/002_add_missing_columns.sql
mysql -u root -p < sql/003_add_notification_tables.sql
mysql -u root -p < sql/004_add_traceability_columns.sql
```

### 4. 서버 실행

#### 개발 모드 (자동 리로드)
```bash
python run.py
```

#### 프로덕션 모드
```bash
uvicorn meat_backend.main:app --host 0.0.0.0 --port 8000
```

서버는 기본적으로 `http://localhost:8000`에서 실행됩니다.

## 주요 API 엔드포인트

### 프론트엔드 호환 엔드포인트

- `POST /api/analyze` - AI 이미지 분석 (인증 선택적)
  - 이미지 파일 업로드
  - AI 서버로 전달하여 부위 인식 또는 이력번호 추출
  - 축산물 이력제 API 호출 (이력번호가 있는 경우)
  - 냉장고에 자동 추가 (로그인 사용자, 선택적)

### 버전 관리 엔드포인트 (`/api/v1`)

- `POST /api/v1/ai/analyze` - AI 분석 (인증 필수)
- `GET /api/v1/fridge/list` - 냉장고 목록
- `POST /api/v1/fridge/item` - 냉장고 아이템 추가
- `GET /api/v1/auth/me` - 현재 사용자 정보

자세한 API 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인할 수 있습니다.

## 기능

### 1. AI 이미지 분석
- 이미지 업로드 후 AI 서버로 전달
- 부위 인식 (vision 모드) 또는 이력번호 추출 (OCR 모드)
- Mock 응답 모드 지원 (개발 환경)

### 2. 축산물 이력제 연동
- 이력번호를 이용한 이력제 API 호출
- 도축일자, 등급, 원산지, 업체명 정보 조회
- 냉장고 아이템에 자동 저장

### 3. 냉장고 관리
- 냉장고 아이템 추가/조회
- 유통기한 임박 알림
- 이력제 정보 포함 저장

### 4. 인증 및 권한
- JWT 기반 인증
- 게스트 모드 지원
- 선택적 인증 (일부 엔드포인트)

## 개발 가이드

### Mock API 응답

개발 환경에서 AI 서버가 없을 때 Mock 응답을 사용할 수 있습니다:

1. `.env` 파일에서 `DEBUG=true` 설정
2. `AI_SERVER_URL`을 비워두거나 잘못된 URL 설정
3. `/api/analyze` 엔드포인트 호출 시 Mock 응답 반환

### CORS 설정

프론트엔드 도메인을 `.env` 파일의 `CORS_ORIGINS`에 추가하세요:

```env
CORS_ORIGINS=http://localhost:3000,https://your-domain.com
```

## 문제 해결

### 데이터베이스 연결 오류
- MySQL 서버가 실행 중인지 확인
- `.env` 파일의 데이터베이스 설정 확인
- 데이터베이스가 생성되었는지 확인

### AI 서버 연결 오류
- AI 서버가 실행 중인지 확인 (기본 포트: 8001)
- `AI_SERVER_URL` 환경 변수 확인
- 개발 환경에서는 Mock 응답 모드 사용 가능

### CORS 오류
- 프론트엔드 도메인이 `CORS_ORIGINS`에 포함되어 있는지 확인
- 브라우저 콘솔에서 정확한 오류 메시지 확인

## 라이선스

이 프로젝트는 Meat-A-Eye 프로젝트의 일부입니다.

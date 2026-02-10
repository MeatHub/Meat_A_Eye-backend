# AI 서버 연동 안내

## 개요

- **Vision(부위 인식)** 요청 시 백엔드는 **AI 서버**의 `POST /predict`를 호출합니다.
- AI 서버가 꺼져 있거나 URL이 잘못되면 분석 API가 **503**을 반환합니다.

## 설정

- **환경변수**: `AI_SERVER_URL` (기본값: `http://localhost:8001`)
- **.env 예시**: `AI_SERVER_URL=http://localhost:8001`

## AI 서버 실행 (Meat_A_Eye-aimodels)

1. `Meat_A_Eye-aimodels/ai-server` 폴더로 이동
2. 가상환경 활성화 후 `python main.py` 또는 `uvicorn main:app --host 0.0.0.0 --port 8001`
3. 포트 8001에서 `/predict` 엔드포인트가 응답하는지 확인

## 17개 부위 (AI·DB·백엔드 동일)

- **소 10**: Beef_Tenderloin, Beef_Ribeye, Beef_Sirloin, Beef_Chuck, Beef_Round, Beef_BottomRound, Beef_Brisket, Beef_Shank, Beef_Rib, Beef_Shoulder
- **돼지 7**: Pork_Tenderloin, Pork_Loin, Pork_Neck, Pork_PicnicShoulder, Pork_Ham, Pork_Belly, Pork_Ribs
- `PART_TO_CODES`와 `meat_info` 테이블은 위 17개 영문 `part_name`으로 통일되어 있습니다.
- 레거시 이름(예: FrontLeg, Pork_Rib)만 `AI_PART_TO_BACKEND`에서 위 17개로 매핑됩니다.

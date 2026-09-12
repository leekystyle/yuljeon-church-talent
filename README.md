# 율전중앙교회 교회학교 달란트 잔치 시스템 (v2.0.0)

율전중앙교회 교회학교(아동부 ~ 청소년부) 학생들의 모범 신앙 활동(예배 출석, 성경 암송, 전도, 봉사)을 독려하고, 달란트 획득 실적 및 매점 키오스크 결제를 투명하게 관리하는 통합 웹 애플리케이션입니다.

---

## 🌟 주요 기능

1. **학생 관리 & 가입 승인 (관리자)**:
   - 신규 학생 등록 (고유 ID 자동 채번, 초기 비밀번호 `0000`)
   - 온라인 가입 학생 승인 활성화 및 비밀번호 분실 시 `0000` 즉시 초기화
   - 필수 정보(이름, 고유 ID, 비밀번호) 및 선택 정보(소속, 나이, 성별, 연락처, 이메일), **프로필 사진** 등록
2. **달란트 실적 지급 (관리자)**:
   - 출석, 전도, 암송 등 기준에 따라 개별/선택 학생에게 달란트 지급
3. **달란트 지급 기준 CRUD (관리자/학생 공개)**:
   - 지급 기준 동적 등록 및 수정, 학생 포털에 실시간 공개
4. **매점 물품 및 재고 관리 CRUD (관리자/학생 공개)**:
   - 매점 판매 품목, 필요 달란트(가격), 재고 수량 및 이미지 관리
5. **학생 전용 포털 (My Talent)**:
   - 본인 프로필 사진, 누적 획득 달란트, 누적 사용 달란트, 현재 잔여 달란트 실시간 조회
   - 일자별 적립 상세 내역 및 매점 결제 세부 내역 열람
6. **매점 키오스크 쇼핑몰 (태블릿/PC 최적화)**:
   - 학생 로그인 시 **본인 사진과 이름, 잔여 달란트 크게 표출** (도용 방지)
   - 장바구니 담기 ➔ 잔액 부족 시 결제 차단 ➔ 2차 비밀번호 확인 모달 ➔ 즉시 차감 및 영수증 안내 후 5초 자동 로그아웃
7. **구매 내역 수정 및 반품 (관리자)**:
   - 잘못 구매하거나 반품 시 기존 거래 롤백(달란트 환불 및 재고 복원) 후 신규 주문으로 안전하게 교체
8. **연 1회 달란트 총괄 초기화 (관리자)**:
   - 학년도 말 전체 학생 잔여 달란트 일괄 0 리셋 및 직전 잔액 영구 아카이빙(스냅샷)
9. **보안 게이트웨이**:
   - 시스템 최초 진입 시 마스터 패스워드(`ADMIN_PW`) 인증 필요

---

## 🏗️ 시스템 환경 및 기술 스택

* **호스팅**: Cloudtype (Build type: dockerfile)
* **프레임워크**: FastAPI (Python 3.11+)
* **데이터베이스**: MariaDB (Service: `mariadb`, DB: `mpoq4l0a34cd6b3f`)
* **테이블 접두어**: 모든 테이블명에 **`yuljeon-`** 접두어 적용
  - `yuljeon-students`
  - `yuljeon-talent_rules`
  - `yuljeon-talent_earnings`
  - `yuljeon-items`
  - `yuljeon-orders`
  - `yuljeon-order_items`
  - `yuljeon-annual_resets`
  - `yuljeon-annual_snapshots`
* **서버 시간대**: `Asia/Seoul` (KST, UTC+9) 표준 라이브러리 `zoneinfo` 사용, `DateTime(timezone=True)`
* **정적 디렉터리**: `static/` 및 `static/uploads/profiles/` (`.gitkeep` 형상 추적)

---

## ⚙️ 환경변수 설정 (Cloudtype)

| 환경변수명 | 필수 여부 | 기본값 / 예시 | 설명 |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | 필수 | `mysql+pymysql://root:[암호]@mariadb:3306/mpoq4l0a34cd6b3f?charset=utf8mb4` | MariaDB 연결 URL |
| `ADMIN_PW` | 필수 | `1234` | 시스템 보안 게이트 및 관리자 비밀번호 |
| `SECRET_KEY` | 선택 | 임의 난수 문자열 | 세션 및 쿠키 암호화 키 |

---

## 🚀 배포 및 로컬 실행 방법

### 로컬 실행 (테스트)
```bash
cd yuljeon-church-talent

# 패키지 설치
pip install -r requirements.txt

# DB 테이블 생성 및 더미 데이터 (각 테이블별 3건) 시딩
python seed_data.py

# 서버 기동
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Cloudtype 배포
1. 본 레포지토리(`https://github.com/leekystyle/yuljeon-church-talent`)를 Cloudtype과 연동합니다.
2. 배포 유형을 **Dockerfile**로 지정합니다.
3. 환경변수 `DATABASE_URL`, `ADMIN_PW`를 입력합니다.
4. **"배포하기"** 버튼을 클릭하여 수동 배포를 진행합니다.

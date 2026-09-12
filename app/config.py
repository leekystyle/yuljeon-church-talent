import os
from dotenv import load_dotenv

load_dotenv()

# 데이터베이스 연결 URL (MariaDB 권장, 환경변수 미설정 시 로컬 테스트용 SQLite 자동 폴백)
raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./yuljeon_talent.db")

# mysql:// 프로토콜을 SQLAlchemy 표준 mysql+pymysql:// 로 자동 보정
if raw_db_url.startswith("mysql://"):
    DATABASE_URL = raw_db_url.replace("mysql://", "mysql+pymysql://", 1)
elif raw_db_url.startswith("mariadb://"):
    DATABASE_URL = raw_db_url.replace("mariadb://", "mysql+pymysql://", 1)
else:
    DATABASE_URL = raw_db_url

# 관리자 마스터 비밀번호 (보안 게이트웨이 및 관리자 로그인)
ADMIN_PW = os.getenv("ADMIN_PW", "1234")

# 최고 관리자 전용 마스터 비밀번호 (Master_PW: 테스트 데이터 초기화 및 치명적 작업용)
MASTER_PW = os.getenv("Master_PW", os.getenv("MASTER_PW", "master1234"))

# 세션 암호화 시크릿 키
SECRET_KEY = os.getenv("SECRET_KEY", "yuljeon-church-talent-2026-secret-key")

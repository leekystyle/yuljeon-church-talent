"""
율전중앙교회 달란트 시스템 KST (Asia/Seoul) 표준 시간대 유틸리티 모듈
- Python 3.9+ 표준 라이브러리 zoneinfo 사용
- 모든 날짜·시간 데이터는 Asia/Seoul(UTC+9) 기준으로 저장 및 표출
- datetime.utcnow() 및 타임존 미지정 datetime.now() 사용을 엄격히 배제함
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# 한국 표준시(KST) 타임존 객체
KST = ZoneInfo("Asia/Seoul")


def get_kst_now() -> datetime:
    """현재 한국 표준시(Asia/Seoul, UTC+9)를 타임존 인식 datetime 객체로 반환"""
    return datetime.now(KST)


def format_kst(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """datetime 객체를 KST 기준 포맷 문자열로 변환"""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # naive 객체인 경우 KST로 localize
        dt = dt.replace(tzinfo=KST)
    else:
        dt = dt.astimezone(KST)
    return dt.strftime(fmt)

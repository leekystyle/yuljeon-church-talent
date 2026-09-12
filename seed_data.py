"""
율전중앙교회 달란트 시스템 테이블 생성 및 필수 마스터 데이터 시딩 스크립트
(실운영 환경 대비: 학생, 거래/주문, 적립실적, 달란트 톡톡 등의 테스트 더미 데이터 자동 주입은 제외)
테이블 접두어 'yuljeon-' 적용 확인
"""

import sys
import os

# 현재 디렉터리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base, SessionLocal
from app.models import (
    Student, TalentRule, TalentEarning, Item, Order, OrderItem, AnnualReset, AnnualSnapshot,
    Department, RuleCategory, ItemCategory, OrderAdjustmentLog, SystemConfig, set_system_config,
    TalentTalk
)
from sqlalchemy import text
from app.timezone import get_kst_now


def init_db_and_seed():
    print("=== [1/2] 데이터베이스 테이블 생성 시작 ('yuljeon-' 접두어) ===")
    Base.metadata.create_all(bind=engine)
    print("테이블 목록:", [t for t in Base.metadata.tables.keys()])

    # MariaDB 컬럼 자동 마이그레이션 (photo_url, image_url을 MEDIUMTEXT로 확장)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE `yuljeon-students` MODIFY COLUMN photo_url MEDIUMTEXT;"))
            conn.execute(text("ALTER TABLE `yuljeon-items` MODIFY COLUMN image_url MEDIUMTEXT;"))
            conn.commit()
            print("✓ [DB 마이그레이션] photo_url 및 image_url 컬럼 MEDIUMTEXT 승격 완료")
    except Exception as e:
        print(f"ℹ️ [DB 마이그레이션 정보] {e}")

    db = SessionLocal()
    try:
        print("=== [2/2] 필수 마스터 데이터 초기화 ===")

        # 1. yuljeon-departments 초기 소속부서
        if db.query(Department).count() == 0:
            default_depts = [
                Department(name="유치부", display_order=1, is_active=True, created_at=get_kst_now()),
                Department(name="아동부", display_order=2, is_active=True, created_at=get_kst_now()),
                Department(name="청소년부", display_order=3, is_active=True, created_at=get_kst_now()),
            ]
            db.add_all(default_depts)
            db.commit()
            print("✓ [yuljeon-departments] 기본 소속부서 3건 등록 완료")

        # 2. yuljeon-rule_categories 초기 기준 분류
        if db.query(RuleCategory).count() == 0:
            default_cats = [
                RuleCategory(name="예배", display_order=1, is_active=True, created_at=get_kst_now()),
                RuleCategory(name="전도", display_order=2, is_active=True, created_at=get_kst_now()),
                RuleCategory(name="봉사", display_order=3, is_active=True, created_at=get_kst_now()),
                RuleCategory(name="암송", display_order=4, is_active=True, created_at=get_kst_now()),
                RuleCategory(name="특별", display_order=5, is_active=True, created_at=get_kst_now()),
            ]
            db.add_all(default_cats)
            db.commit()
            print("✓ [yuljeon-rule_categories] 기본 기준 분류 5건 등록 완료")

        # 3. yuljeon-item_categories 매점 상품 초기 분류
        if db.query(ItemCategory).count() == 0:
            default_item_cats = [
                ItemCategory(name="먹거리", display_order=1, is_active=True, created_at=get_kst_now()),
                ItemCategory(name="문화생활", display_order=2, is_active=True, created_at=get_kst_now()),
                ItemCategory(name="문구/완구", display_order=3, is_active=True, created_at=get_kst_now()),
                ItemCategory(name="도서/학용품", display_order=4, is_active=True, created_at=get_kst_now()),
                ItemCategory(name="기타", display_order=5, is_active=True, created_at=get_kst_now()),
            ]
            db.add_all(default_item_cats)
            db.commit()
            print("✓ [yuljeon-item_categories] 기본 상품 분류 5건 등록 완료")

        # 4. yuljeon-system_configs 시스템 환경설정 기본값
        kiosk_timeout_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == "kiosk_auto_logout_seconds").first()
        if not kiosk_timeout_cfg:
            set_system_config(
                db,
                key="kiosk_auto_logout_seconds",
                value="10",
                description="매점 키오스크 로그인 세션 자동 로그아웃 대기 시간 (초)"
            )
            print("✓ [yuljeon-system_configs] 매점 키오스크 자동 로그아웃 기본 시간(10초) 등록 완료")

        # 5. yuljeon-talent_rules 초기 기본 지급 기준 마스터 (기준이 비어있을 때만)
        if db.query(TalentRule).count() == 0:
            rules = [
                TalentRule(
                    rule_code="R001",
                    title="주일예배 출석",
                    category="예배",
                    points=2,
                    description="주일 예배 출석 시 2달란트 지급 (예배 시작 10분 전 도착 시 3달란트)",
                    is_public=True,
                    is_active=True,
                    created_at=get_kst_now(),
                ),
                TalentRule(
                    rule_code="R002",
                    title="새친구 전도",
                    category="전도",
                    points=5,
                    description="새친구 전도 시 5달란트 지급 (전도된 친구 4주 등반 시 5달란트 추가 지급)",
                    is_public=True,
                    is_active=True,
                    created_at=get_kst_now(),
                ),
                TalentRule(
                    rule_code="R003",
                    title="주일 성경 암송 및 봉사 모범",
                    category="봉사",
                    points=2,
                    description="지정된 주일 성경 구절 완벽 암송 및 예배당 정리정돈 모범 봉사자 지급",
                    is_public=True,
                    is_active=True,
                    created_at=get_kst_now(),
                ),
            ]
            db.add_all(rules)
            db.commit()
            print("✓ [yuljeon-talent_rules] 기본 지급 기준 마스터 3건 등록 완료")

        # 6. yuljeon-items 초기 기본 매점 물품 마스터 (물품이 비어있을 때만)
        if db.query(Item).count() == 0:
            items = [
                Item(
                    item_code="P001",
                    name="한강라면",
                    category="먹거리",
                    price=4,
                    stock=50,
                    image_url="/static/images/ramen.svg",
                    is_active=True,
                    created_at=get_kst_now(),
                ),
                Item(
                    item_code="P002",
                    name="초코과자",
                    category="먹거리",
                    price=5,
                    stock=30,
                    image_url="/static/images/snack.svg",
                    is_active=True,
                    created_at=get_kst_now(),
                ),
                Item(
                    item_code="P003",
                    name="메가커피 기프티콘",
                    category="문화생활",
                    price=10,
                    stock=20,
                    image_url="/static/images/coffee.svg",
                    is_active=True,
                    created_at=get_kst_now(),
                ),
            ]
            db.add_all(items)
            db.commit()
            print("✓ [yuljeon-items] 기본 매점 물품 마스터 3건 등록 완료")

        # ※ 참고: 달란트 톡톡(TalentTalk), 매점 주문(Order, OrderItem), 적립 실적(TalentEarning),
        #    연간 초기화 이력(AnnualReset, AnnualSnapshot), 학생(Student) 등의 활동/거래 데이터는
        #    실운영 환경의 무결성을 위해 배포 시 자동 주입하지 않고 관리자가 실제 운영 및 업로드하도록 비워둡니다.

        print("=== [완료] 필수 마스터 설정 확인 완료! ===")
    finally:
        db.close()


if __name__ == "__main__":
    init_db_and_seed()

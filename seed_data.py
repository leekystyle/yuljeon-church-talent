"""
율전중앙교회 달란트 시스템 테이블 생성 및 8개 테이블 더미 데이터 각각 3건씩 시딩 스크립트
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
    print("=== [1/3] 데이터베이스 테이블 생성 시작 ('yuljeon-' 접두어) ===")
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
        # 1. yuljeon-students 더미 데이터 (3건)
        if db.query(Student).count() == 0:
            print("=== [2/3] 더미 데이터 주입 시작 ===")
            students = [
                Student(
                    student_code="S001",
                    name="김도현",
                    password_hash="0000",
                    photo_url="/static/uploads/profiles/student_s001.svg",
                    department="아동부",
                    age=12,
                    gender="M",
                    phone="010-1234-5671",
                    email="dohyun@example.com",
                    current_talent=10,
                    total_earned=14,
                    total_spent=4,
                    is_active=True,
                    created_at=get_kst_now(),
                    updated_at=get_kst_now(),
                ),
                Student(
                    student_code="S002",
                    name="김종우",
                    password_hash="0000",
                    photo_url="/static/uploads/profiles/student_s002.svg",
                    department="아동부",
                    age=11,
                    gender="M",
                    phone="010-1234-5672",
                    email="jongwoo@example.com",
                    current_talent=10,
                    total_earned=15,
                    total_spent=5,
                    is_active=True,
                    created_at=get_kst_now(),
                    updated_at=get_kst_now(),
                ),
                Student(
                    student_code="S003",
                    name="김주아",
                    password_hash="0000",
                    photo_url="/static/uploads/profiles/student_s003.svg",
                    department="청소년부",
                    age=15,
                    gender="F",
                    phone="010-1234-5673",
                    email="jooa@example.com",
                    current_talent=10,
                    total_earned=20,
                    total_spent=10,
                    is_active=True,
                    created_at=get_kst_now(),
                    updated_at=get_kst_now(),
                ),
            ]
            db.add_all(students)
            db.commit()
            print("✓ [yuljeon-students] 3건 등록 완료")

        # 2. yuljeon-talent_rules 더미 데이터 (3건)
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
            print("✓ [yuljeon-talent_rules] 3건 등록 완료")

        # 3. yuljeon-talent_earnings 더미 데이터 (3건)
        if db.query(TalentEarning).count() == 0:
            s1 = db.query(Student).filter_by(student_code="S001").first()
            s2 = db.query(Student).filter_by(student_code="S002").first()
            s3 = db.query(Student).filter_by(student_code="S003").first()
            r1 = db.query(TalentRule).filter_by(rule_code="R001").first()
            r2 = db.query(TalentRule).filter_by(rule_code="R002").first()
            r3 = db.query(TalentRule).filter_by(rule_code="R003").first()

            earnings = [
                TalentEarning(
                    student_id=s1.id,
                    rule_id=r1.id,
                    points=3,
                    reason="주일예배 10분 전 출석 모범",
                    granted_by="김은혜 교사",
                    created_at=get_kst_now(),
                ),
                TalentEarning(
                    student_id=s2.id,
                    rule_id=r2.id,
                    points=5,
                    reason="새친구 전도 (학교 짝꿍 전도)",
                    granted_by="박선민 교사",
                    created_at=get_kst_now(),
                ),
                TalentEarning(
                    student_id=s3.id,
                    rule_id=r3.id,
                    points=2,
                    reason="요한복음 3장 16절 성경 암송 완료",
                    granted_by="이바울 교역자",
                    created_at=get_kst_now(),
                ),
            ]
            db.add_all(earnings)
            db.commit()
            print("✓ [yuljeon-talent_earnings] 3건 등록 완료")

        # 4. yuljeon-items 더미 데이터 (3건)
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
            print("✓ [yuljeon-items] 3건 등록 완료")

        # 5. yuljeon-orders 및 yuljeon-order_items 더미 데이터 (각각 3건)
        if db.query(Order).count() == 0:
            s1 = db.query(Student).filter_by(student_code="S001").first()
            s2 = db.query(Student).filter_by(student_code="S002").first()
            s3 = db.query(Student).filter_by(student_code="S003").first()
            p1 = db.query(Item).filter_by(item_code="P001").first()
            p2 = db.query(Item).filter_by(item_code="P002").first()
            p3 = db.query(Item).filter_by(item_code="P003").first()

            o1 = Order(
                order_number="ORD-20260910-0001",
                student_id=s1.id,
                total_points=4,
                status="COMPLETED",
                created_at=get_kst_now(),
                updated_at=get_kst_now(),
            )
            o2 = Order(
                order_number="ORD-20260910-0002",
                student_id=s2.id,
                total_points=5,
                status="COMPLETED",
                created_at=get_kst_now(),
                updated_at=get_kst_now(),
            )
            o3 = Order(
                order_number="ORD-20260911-0003",
                student_id=s3.id,
                total_points=10,
                status="COMPLETED",
                created_at=get_kst_now(),
                updated_at=get_kst_now(),
            )
            db.add_all([o1, o2, o3])
            db.flush()

            order_items = [
                OrderItem(
                    order_id=o1.id,
                    item_id=p1.id,
                    item_name="한강라면",
                    unit_price=4,
                    quantity=1,
                    subtotal_points=4,
                ),
                OrderItem(
                    order_id=o2.id,
                    item_id=p2.id,
                    item_name="초코과자",
                    unit_price=5,
                    quantity=1,
                    subtotal_points=5,
                ),
                OrderItem(
                    order_id=o3.id,
                    item_id=p3.id,
                    item_name="메가커피 기프티콘",
                    unit_price=10,
                    quantity=1,
                    subtotal_points=10,
                ),
            ]
            db.add_all(order_items)
            db.commit()
            print("✓ [yuljeon-orders] 3건 등록 완료")
            print("✓ [yuljeon-order_items] 3건 등록 완료")

        # 7. yuljeon-annual_resets 및 yuljeon-annual_snapshots 더미 데이터 (각각 3건)
        if db.query(AnnualReset).count() == 0:
            s1 = db.query(Student).filter_by(student_code="S001").first()
            s2 = db.query(Student).filter_by(student_code="S002").first()
            s3 = db.query(Student).filter_by(student_code="S003").first()

            r1 = AnnualReset(
                reset_year=2024,
                student_count=75,
                total_reset_points=1250,
                admin_memo="2024학년도 학기말 달란트 정기 총괄 초기화",
                reset_at=get_kst_now(),
            )
            r2 = AnnualReset(
                reset_year=2025,
                student_count=80,
                total_reset_points=890,
                admin_memo="2025년 여름성경학교 결산 달란트 중간 초기화",
                reset_at=get_kst_now(),
            )
            r3 = AnnualReset(
                reset_year=2025,
                student_count=84,
                total_reset_points=1420,
                admin_memo="2025학년도 학기말 달란트 정기 총괄 초기화",
                reset_at=get_kst_now(),
            )
            db.add_all([r1, r2, r3])
            db.flush()

            snapshots = [
                AnnualSnapshot(
                    reset_id=r3.id,
                    student_id=s1.id,
                    snapshot_talent=15,
                    created_at=get_kst_now(),
                ),
                AnnualSnapshot(
                    reset_id=r3.id,
                    student_id=s2.id,
                    snapshot_talent=8,
                    created_at=get_kst_now(),
                ),
                AnnualSnapshot(
                    reset_id=r3.id,
                    student_id=s3.id,
                    snapshot_talent=22,
                    created_at=get_kst_now(),
                ),
            ]
            db.add_all(snapshots)
            db.commit()
            print("✓ [yuljeon-annual_resets] 3건 등록 완료")
            print("✓ [yuljeon-annual_snapshots] 3건 등록 완료")

        # 9. yuljeon-departments 초기 소속부서
        if db.query(Department).count() == 0:
            default_depts = [
                Department(name="유치부", display_order=1, is_active=True, created_at=get_kst_now()),
                Department(name="아동부", display_order=2, is_active=True, created_at=get_kst_now()),
                Department(name="청소년부", display_order=3, is_active=True, created_at=get_kst_now()),
            ]
            db.add_all(default_depts)
            db.commit()
            print("✓ [yuljeon-departments] 기본 소속부서 3건 등록 완료")

        # 10. yuljeon-rule_categories 초기 기준 분류
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

        # 11. yuljeon-item_categories 매점 상품 초기 분류
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

        # 12. yuljeon-system_configs 시스템 환경설정 기본값

        kiosk_timeout_cfg = db.query(SystemConfig).filter(SystemConfig.config_key == "kiosk_auto_logout_seconds").first()
        if not kiosk_timeout_cfg:
            set_system_config(
                db,
                key="kiosk_auto_logout_seconds",
                value="10",
                description="매점 키오스크 로그인 세션 자동 로그아웃 대기 시간 (초)"
            )
            print("✓ [yuljeon-system_configs] 매점 키오스크 자동 로그아웃 기본 시간(10초) 등록 완료")

        # 13. yuljeon-talent_talks 초기 한줄글 더미 데이터 (3건)
        if db.query(TalentTalk).count() == 0:
            first_student = db.query(Student).first()
            if first_student:
                sample_talks = [
                    TalentTalk(
                        student_id=first_student.id,
                        content="오늘 말씀 암송 칭찬받아서 달란트 받았어요! 매점 간식 사러 가야지~ 😋",
                        created_at=get_kst_now(),
                        updated_at=get_kst_now()
                    ),
                    TalentTalk(
                        student_id=first_student.id,
                        content="새로 온 친구 전도해서 기뻐요! 달란트 세상 너무 신나요! 🎉",
                        created_at=get_kst_now(),
                        updated_at=get_kst_now()
                    ),
                    TalentTalk(
                        student_id=first_student.id,
                        content="선생님 항상 사랑으로 가르쳐 주셔서 감사해요! 모두 축복해요 ❤️",
                        created_at=get_kst_now(),
                        updated_at=get_kst_now()
                    ),
                ]
                db.add_all(sample_talks)
                db.commit()
                print("✓ [yuljeon-talent_talks] 초기 달란트 톡톡 더미 데이터 3건 주입 완료")

        print("=== [3/3] 전체 테이블 초기화 및 시딩 완료! ===")
    finally:
        db.close()


if __name__ == "__main__":
    init_db_and_seed()

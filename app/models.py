from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.database import Base
from app.timezone import get_kst_now


class Student(Base):
    """학생 마스터 테이블 ('yuljeon-students')"""
    __tablename__ = "yuljeon-students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_code = Column(String(20), unique=True, index=True, nullable=False)  # 고유 ID (S001~, 필수)
    name = Column(String(50), nullable=False, index=True)                       # 이름 (필수)
    password_hash = Column(String(255), nullable=False)                         # 비밀번호 (필수)
    photo_url = Column(String(255), nullable=True)                              # 프로필 사진 경로 (선택/추가)
    department = Column(String(50), nullable=True)                              # 소속(아동부/청소년부 등, 선택)
    age = Column(Integer, nullable=True)                                        # 나이 (선택)
    gender = Column(String(10), nullable=True)                                  # 성별 (선택)
    phone = Column(String(20), nullable=True)                                   # 연락처 (선택)
    email = Column(String(100), nullable=True)                                  # 이메일 (선택)

    current_talent = Column(Integer, default=0, nullable=False)                 # 현재 보유 잔여 달란트
    total_earned = Column(Integer, default=0, nullable=False)                   # 누적 획득 달란트
    total_spent = Column(Integer, default=0, nullable=False)                    # 누적 사용 달란트
    is_active = Column(Boolean, default=False, nullable=False)                  # 계정 승인 활성화 여부

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now, nullable=False)

    # 관계 정의
    earnings = relationship("TalentEarning", back_populates="student", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="student", cascade="all, delete-orphan")
    snapshots = relationship("AnnualSnapshot", back_populates="student", cascade="all, delete-orphan")


class TalentRule(Base):
    """달란트 지급 기준 테이블 ('yuljeon-talent_rules')"""
    __tablename__ = "yuljeon-talent_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rule_code = Column(String(20), unique=True, index=True, nullable=False)     # 기준 코드 (R001~)
    title = Column(String(100), nullable=False)                                 # 항목명 (주일예배 출석 등)
    category = Column(String(50), nullable=False)                               # 분류 (예배/전도/봉사/암송 등)
    points = Column(Integer, nullable=False)                                    # 지급 달란트
    description = Column(Text, nullable=True)                                   # 상세 규칙 설명
    is_public = Column(Boolean, default=True, nullable=False)                   # 학생 공개 여부
    is_active = Column(Boolean, default=True, nullable=False)                   # 활성화 여부

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

    # 관계 정의
    earnings = relationship("TalentEarning", back_populates="rule")


class TalentEarning(Base):
    """달란트 실적 적립 내역 테이블 ('yuljeon-talent_earnings')"""
    __tablename__ = "yuljeon-talent_earnings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("yuljeon-students.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("yuljeon-talent_rules.id"), nullable=True)
    points = Column(Integer, nullable=False)                                    # 지급 달란트
    reason = Column(String(255), nullable=False)                                # 지급 사유
    granted_by = Column(String(50), nullable=False)                             # 지급 교사명

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

    # 관계 정의
    student = relationship("Student", back_populates="earnings")
    rule = relationship("TalentRule", back_populates="earnings")


class Item(Base):
    """매점 판매 물품 테이블 ('yuljeon-items')"""
    __tablename__ = "yuljeon-items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_code = Column(String(20), unique=True, index=True, nullable=False)     # 상품 코드 (P001~)
    name = Column(String(100), nullable=False)                                  # 상품명
    category = Column(String(50), nullable=False)                               # 분류 (먹거리/문화/문구)
    price = Column(Integer, nullable=False)                                     # 필요 달란트 가격
    stock = Column(Integer, default=0, nullable=False)                          # 재고 수량
    image_url = Column(String(255), nullable=True)                              # 상품 이미지 경로
    is_active = Column(Boolean, default=True, nullable=False)                   # 판매 활성 여부

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

    # 관계 정의
    order_items = relationship("OrderItem", back_populates="item")


class Order(Base):
    """매점 구매 거래 마스터 테이블 ('yuljeon-orders')"""
    __tablename__ = "yuljeon-orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)  # 주문번호 (ORD-YYYYMMDD-XXXX)
    student_id = Column(Integer, ForeignKey("yuljeon-students.id"), nullable=False, index=True)
    total_points = Column(Integer, nullable=False)                              # 총 결제 달란트
    status = Column(String(20), default="COMPLETED", nullable=False)            # COMPLETED / REFUNDED / MODIFIED

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now, nullable=False)

    # 관계 정의
    student = relationship("Student", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """주문 세부 품목 테이블 ('yuljeon-order_items')"""
    __tablename__ = "yuljeon-order_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("yuljeon-orders.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("yuljeon-items.id"), nullable=True)
    item_name = Column(String(100), nullable=False)                             # 주문 당시 상품명 스냅샷
    unit_price = Column(Integer, nullable=False)                                # 개당 달란트
    quantity = Column(Integer, nullable=False)                                  # 구매 수량
    subtotal_points = Column(Integer, nullable=False)                           # 소계 달란트

    # 관계 정의
    order = relationship("Order", back_populates="items")
    item = relationship("Item", back_populates="order_items")


class AnnualReset(Base):
    """연간 달란트 총괄 초기화 마스터 테이블 ('yuljeon-annual_resets')"""
    __tablename__ = "yuljeon-annual_resets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    reset_year = Column(Integer, nullable=False, index=True)                    # 대상 연도
    student_count = Column(Integer, nullable=False)                             # 대상 학생 수
    total_reset_points = Column(Integer, nullable=False)                        # 초기화(소멸) 총 달란트
    admin_memo = Column(String(255), nullable=True)                             # 관리자 메모
    reset_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

    # 관계 정의
    snapshots = relationship("AnnualSnapshot", back_populates="reset_master", cascade="all, delete-orphan")


class AnnualSnapshot(Base):
    """연간 초기화 직전 학생별 잔여 달란트 영구 보존 테이블 ('yuljeon-annual_snapshots')"""
    __tablename__ = "yuljeon-annual_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    reset_id = Column(Integer, ForeignKey("yuljeon-annual_resets.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("yuljeon-students.id"), nullable=False, index=True)
    snapshot_talent = Column(Integer, nullable=False)                           # 초기화 직전 잔여 달란트

    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

    # 관계 정의
    reset_master = relationship("AnnualReset", back_populates="snapshots")
    student = relationship("Student", back_populates="snapshots")


class Department(Base):
    """학생 소속부서 설정 테이블 ('yuljeon-departments')"""
    __tablename__ = "yuljeon-departments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)                      # 소속부서명 (유치부, 아동부, 청소년부 등)
    display_order = Column(Integer, default=0, nullable=False)                  # 표시 순서
    is_active = Column(Boolean, default=True, nullable=False)                   # 활성화 여부
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)


class RuleCategory(Base):
    """달란트 지급 기준 분류 설정 테이블 ('yuljeon-rule_categories')"""
    __tablename__ = "yuljeon-rule_categories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)                      # 기준 분류명 (예배, 전도, 봉사, 암송 등)
    display_order = Column(Integer, default=0, nullable=False)                  # 표시 순서
    is_active = Column(Boolean, default=True, nullable=False)                   # 활성화 여부
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)

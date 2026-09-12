import os
import shutil
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import (
    Student, TalentRule, TalentEarning, Item, Order, OrderItem, AnnualReset, AnnualSnapshot
)
from app.config import ADMIN_PW
from app.timezone import get_kst_now

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


def check_admin(request: Request):
    """관리자 인증 쿠키 확인"""
    auth = request.cookies.get("yuljeon_admin_auth")
    if auth != "authenticated":
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/admin/login"})


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": error})


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    total_students = db.query(Student).count()
    active_students = db.query(Student).filter(Student.is_active == True).count()
    pending_students = db.query(Student).filter(Student.is_active == False).count()
    
    total_earned = db.query(func.sum(Student.total_earned)).scalar() or 0
    total_spent = db.query(func.sum(Student.total_spent)).scalar() or 0
    total_circulating = db.query(func.sum(Student.current_talent)).scalar() or 0

    recent_earnings = db.query(TalentEarning).order_by(TalentEarning.created_at.desc()).limit(10).all()
    recent_orders = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "total_students": total_students,
        "active_students": active_students,
        "pending_students": pending_students,
        "total_earned": total_earned,
        "total_spent": total_spent,
        "total_circulating": total_circulating,
        "recent_earnings": recent_earnings,
        "recent_orders": recent_orders
    })


# -------------------------------------------------------------
# 1 & 6. 학생 관리 기능
# -------------------------------------------------------------
@router.get("/students", response_class=HTMLResponse)
async def list_students(request: Request, search: Optional[str] = None, dept: Optional[str] = None, db: Session = Depends(get_db)):
    check_admin(request)
    query = db.query(Student)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((Student.name.ilike(s)) | (Student.student_code.ilike(s)))
    if dept:
        query = query.filter(Student.department == dept.strip())

    students = query.order_by(Student.student_code.asc()).all()
    return templates.TemplateResponse("admin/students.html", {
        "request": request,
        "students": students,
        "search": search or "",
        "dept": dept or ""
    })


@router.post("/students/create")
async def create_student(
    name: str = Form(...),
    student_code: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """관리자 화면에서 신규 학생 직접 등록 (고유 ID 자동 채번 및 초기 비밀번호 0000)"""
    if not student_code or not student_code.strip():
        count = db.query(Student).count()
        student_code = f"S{count + 1:03d}"
        while db.query(Student).filter(Student.student_code == student_code).first():
            count += 1
            student_code = f"S{count + 1:03d}"
    else:
        student_code = student_code.strip()

    photo_url = "/static/uploads/profiles/default_avatar.svg"
    if photo and photo.filename:
        filename = f"{student_code}_{photo.filename.replace(' ', '_')}"
        upload_dir = "static/uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_url = f"/static/uploads/profiles/{filename}"

    student = Student(
        student_code=student_code,
        name=name.strip(),
        password_hash="0000",  # 초기 비밀번호 0000
        photo_url=photo_url,
        department=department.strip() if department else None,
        age=age,
        gender=gender,
        phone=phone.strip() if phone else None,
        email=email.strip() if email else None,
        current_talent=0,
        total_earned=0,
        total_spent=0,
        is_active=True,  # 관리자 등록 학생은 즉시 활성화
        created_at=get_kst_now(),
        updated_at=get_kst_now()
    )
    db.add(student)
    db.commit()
    return RedirectResponse(url="/admin/students?msg=created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/activate")
async def activate_student(student_id: int, db: Session = Depends(get_db)):
    """가입 신청한 학생의 계정 활성화 승인"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if student:
        student.is_active = True
        db.commit()
    return RedirectResponse(url="/admin/students?msg=activated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/reset_pw")
async def reset_student_password(student_id: int, db: Session = Depends(get_db)):
    """비밀번호를 분실한 학생의 비밀번호를 '0000'으로 초기화"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if student:
        student.password_hash = "0000"
        db.commit()
    return RedirectResponse(url="/admin/students?msg=pw_reset", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 2. 학생의 달란트 실적 등록
# -------------------------------------------------------------
@router.get("/talent/grant", response_class=HTMLResponse)
async def grant_talent_page(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    students = db.query(Student).filter(Student.is_active == True).order_by(Student.name.asc()).all()
    rules = db.query(TalentRule).filter(TalentRule.is_active == True).all()
    return templates.TemplateResponse("admin/talent_grant.html", {
        "request": request,
        "students": students,
        "rules": rules
    })


@router.post("/talent/grant")
async def grant_talent(
    student_id: int = Form(...),
    rule_id: Optional[int] = Form(None),
    points: int = Form(...),
    reason: str = Form(...),
    granted_by: str = Form(...),
    db: Session = Depends(get_db)
):
    """달란트 실적 등록 및 잔여/누적 달란트 가산"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return RedirectResponse(url="/admin/talent/grant?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    earning = TalentEarning(
        student_id=student.id,
        rule_id=rule_id if rule_id and rule_id > 0 else None,
        points=points,
        reason=reason.strip(),
        granted_by=granted_by.strip(),
        created_at=get_kst_now()
    )
    student.current_talent += points
    student.total_earned += points

    db.add(earning)
    db.commit()
    return RedirectResponse(url="/admin/talent/grant?msg=granted", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 3. 달란트 지급 기준 관리
# -------------------------------------------------------------
@router.get("/talent/rules", response_class=HTMLResponse)
async def manage_rules(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    rules = db.query(TalentRule).order_by(TalentRule.id.asc()).all()
    return templates.TemplateResponse("admin/talent_rules.html", {"request": request, "rules": rules})


@router.post("/talent/rules/create")
async def create_rule(
    title: str = Form(...),
    category: str = Form(...),
    points: int = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(True),
    db: Session = Depends(get_db)
):
    count = db.query(TalentRule).count()
    rule_code = f"R{count + 1:03d}"
    rule = TalentRule(
        rule_code=rule_code,
        title=title.strip(),
        category=category.strip(),
        points=points,
        description=description.strip() if description else None,
        is_public=is_public,
        is_active=True,
        created_at=get_kst_now()
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(url="/admin/talent/rules?msg=created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/talent/rules/{rule_id}/delete")
async def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(TalentRule).filter(TalentRule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
    return RedirectResponse(url="/admin/talent/rules?msg=deleted", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 4. 달란트로 구매할 수 있는 품목 관리
# -------------------------------------------------------------
@router.get("/items", response_class=HTMLResponse)
async def manage_items(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    items = db.query(Item).order_by(Item.id.asc()).all()
    return templates.TemplateResponse("admin/items.html", {"request": request, "items": items})


@router.post("/items/create")
async def create_item(
    name: str = Form(...),
    category: str = Form(...),
    price: int = Form(...),
    stock: int = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    count = db.query(Item).count()
    item_code = f"P{count + 1:03d}"
    image_url = "/static/images/ramen.svg"
    if image and image.filename:
        filename = f"{item_code}_{image.filename.replace(' ', '_')}"
        upload_dir = "static/images"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/images/{filename}"

    item = Item(
        item_code=item_code,
        name=name.strip(),
        category=category.strip(),
        price=price,
        stock=stock,
        image_url=image_url,
        is_active=True,
        created_at=get_kst_now()
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url="/admin/items?msg=created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/{item_id}/update_stock")
async def update_item_stock(item_id: int, stock: int = Form(...), price: int = Form(...), db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if item:
        item.stock = stock
        item.price = price
        db.commit()
    return RedirectResponse(url="/admin/items?msg=updated", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 9. 달란트 사용 내역 수정 기능 (기존 구매 취소 및 롤백 후 변경)
# -------------------------------------------------------------
@router.get("/orders", response_class=HTMLResponse)
async def list_orders(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    items = db.query(Item).filter(Item.is_active == True).all()
    return templates.TemplateResponse("admin/orders.html", {
        "request": request,
        "orders": orders,
        "items": items
    })


@router.post("/orders/{order_id}/modify")
async def modify_order(
    order_id: int,
    action: str = Form(...),  # 'refund' 또는 'update'
    new_item_id: Optional[int] = Form(None),
    new_quantity: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """구매 내역 수정/반품 로직: 기존 구매 취소(원상복구) 후 신규 구매 내역 갱신"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != "COMPLETED":
        return RedirectResponse(url="/admin/orders?error=invalid_order", status_code=status.HTTP_303_SEE_OTHER)

    student = order.student

    # 1. 기존 사용 달란트 및 재고 전액 원상복구 (Rollback)
    student.current_talent += order.total_points
    student.total_spent -= order.total_points
    for o_item in order.items:
        if o_item.item:
            o_item.item.stock += o_item.quantity

    if action == "refund":
        # 단순 반품/환불 처리
        order.status = "REFUNDED"
        order.updated_at = get_kst_now()
        db.commit()
        return RedirectResponse(url="/admin/orders?msg=refunded", status_code=status.HTTP_303_SEE_OTHER)

    elif action == "update" and new_item_id and new_quantity and new_quantity > 0:
        # 수정한 품목 및 수량으로 재결제 처리
        new_item = db.query(Item).filter(Item.id == new_item_id).first()
        if not new_item or new_item.stock < new_quantity:
            db.rollback()
            return RedirectResponse(url="/admin/orders?error=stock_shortage", status_code=status.HTTP_303_SEE_OTHER)

        new_total = new_item.price * new_quantity
        if student.current_talent < new_total:
            db.rollback()
            return RedirectResponse(url="/admin/orders?error=insufficient_talent", status_code=status.HTTP_303_SEE_OTHER)

        # 새 차감 적용
        student.current_talent -= new_total
        student.total_spent += new_total
        new_item.stock -= new_quantity

        # 기존 주문 건 내용 교체
        order.total_points = new_total
        order.status = "COMPLETED"
        order.updated_at = get_kst_now()

        # 세부 품목 교체
        for o_item in list(order.items):
            db.delete(o_item)
        
        new_order_item = OrderItem(
            order_id=order.id,
            item_id=new_item.id,
            item_name=new_item.name,
            unit_price=new_item.price,
            quantity=new_quantity,
            subtotal_points=new_total
        )
        db.add(new_order_item)
        db.commit()
        return RedirectResponse(url="/admin/orders?msg=modified", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(url="/admin/orders", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 10. 학생들의 달란트 총괄 관리 (연 1회 일괄 0 리셋 및 영구 아카이빙)
# -------------------------------------------------------------
@router.get("/annual_reset", response_class=HTMLResponse)
async def annual_reset_page(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    resets = db.query(AnnualReset).order_by(AnnualReset.reset_at.desc()).all()
    current_year = get_kst_now().year
    active_count = db.query(Student).filter(Student.current_talent > 0).count()
    total_talent = db.query(func.sum(Student.current_talent)).scalar() or 0

    return templates.TemplateResponse("admin/annual_reset.html", {
        "request": request,
        "resets": resets,
        "current_year": current_year,
        "active_count": active_count,
        "total_talent": total_talent
    })


@router.post("/annual_reset")
async def execute_annual_reset(
    admin_pw: str = Form(...),
    admin_memo: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """연 1회 달란트 총괄 초기화 실행"""
    if admin_pw != ADMIN_PW:
        return RedirectResponse(url="/admin/annual_reset?error=invalid_password", status_code=status.HTTP_303_SEE_OTHER)

    now = get_kst_now()
    students = db.query(Student).all()
    total_reset_points = 0
    student_count = len(students)

    reset_master = AnnualReset(
        reset_year=now.year,
        student_count=student_count,
        total_reset_points=0,
        admin_memo=admin_memo.strip() if admin_memo else f"{now.year}학년도 정기 달란트 초기화",
        reset_at=now
    )
    db.add(reset_master)
    db.flush()

    for s in students:
        if s.current_talent > 0:
            total_reset_points += s.current_talent
            snapshot = AnnualSnapshot(
                reset_id=reset_master.id,
                student_id=s.id,
                snapshot_talent=s.current_talent,
                created_at=now
            )
            db.add(snapshot)
            s.current_talent = 0  # 0으로 초기화

    reset_master.total_reset_points = total_reset_points
    db.commit()

    return RedirectResponse(url="/admin/annual_reset?msg=reset_completed", status_code=status.HTTP_303_SEE_OTHER)

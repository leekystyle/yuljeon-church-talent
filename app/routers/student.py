import os
import shutil
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Student, TalentRule, TalentEarning, Order, Item
from app.timezone import get_kst_now

router = APIRouter(prefix="/student", tags=["student"])
templates = Jinja2Templates(directory="templates")


def get_current_student(request: Request, db: Session) -> Optional[Student]:
    student_id = request.cookies.get("yuljeon_student_id")
    if not student_id:
        return None
    try:
        return db.query(Student).filter(Student.id == int(student_id)).first()
    except (ValueError, TypeError):
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse("student/login.html", {"request": request, "error": error})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("student/register.html", {"request": request})


@router.post("/register")
async def register_student(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    department: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """학생 자율 회원가입 처리"""
    # 다음 자동 고유 ID 채번
    count = db.query(Student).count()
    student_code = f"S{count + 1:03d}"
    
    # 중복 방지 루프
    while db.query(Student).filter(Student.student_code == student_code).first():
        count += 1
        student_code = f"S{count + 1:03d}"

    photo_url = "/static/uploads/profiles/default_avatar.svg"
    if photo and photo.filename:
        filename = f"{student_code}_{photo.filename.replace(' ', '_')}"
        upload_dir = "static/uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_url = f"/static/uploads/profiles/{filename}"

    new_student = Student(
        student_code=student_code,
        name=name.strip(),
        password_hash=password.strip(),
        photo_url=photo_url,
        department=department.strip() if department else None,
        age=age,
        gender=gender,
        phone=phone.strip() if phone else None,
        email=email.strip() if email else None,
        current_talent=0,
        total_earned=0,
        total_spent=0,
        is_active=False,  # 관리자 승인 대기
        created_at=get_kst_now(),
        updated_at=get_kst_now()
    )
    db.add(new_student)
    db.commit()

    return templates.TemplateResponse("student/registered.html", {
        "request": request,
        "student": new_student
    })


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    student = get_current_student(request, db)
    if not student:
        return RedirectResponse(url="/student/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # 최근 적립 5건, 최근 사용 5건
    recent_earnings = db.query(TalentEarning).filter(TalentEarning.student_id == student.id)\
        .order_by(TalentEarning.created_at.desc()).limit(5).all()
    recent_orders = db.query(Order).filter(Order.student_id == student.id)\
        .order_by(Order.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("student/dashboard.html", {
        "request": request,
        "student": student,
        "recent_earnings": recent_earnings,
        "recent_orders": recent_orders
    })


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request, db: Session = Depends(get_db)):
    student = get_current_student(request, db)
    if not student:
        return RedirectResponse(url="/student/login", status_code=status.HTTP_303_SEE_OTHER)

    earnings = db.query(TalentEarning).filter(TalentEarning.student_id == student.id)\
        .order_by(TalentEarning.created_at.desc()).all()
    orders = db.query(Order).filter(Order.student_id == student.id)\
        .order_by(Order.created_at.desc()).all()

    return templates.TemplateResponse("student/history.html", {
        "request": request,
        "student": student,
        "earnings": earnings,
        "orders": orders
    })


@router.get("/rules", response_class=HTMLResponse)
async def public_rules(request: Request, db: Session = Depends(get_db)):
    student = get_current_student(request, db)
    rules = db.query(TalentRule).filter(TalentRule.is_public == True, TalentRule.is_active == True).all()
    items = db.query(Item).filter(Item.is_active == True).all()

    return templates.TemplateResponse("student/rules.html", {
        "request": request,
        "student": student,
        "rules": rules,
        "items": items
    })

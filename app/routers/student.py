import os
import shutil
import re
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


from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

@router.get("/api/lookup")
async def student_lookup(query: str = "", db: Session = Depends(get_db)):
    """이름 또는 학생코드로 학생 검색 (동명이인 및 자동완성 지원)"""
    q = query.strip()
    if not q:
        return JSONResponse([])
    
    # 1. 완전 일치 이름/코드
    exact_matches = db.query(Student).filter(
        (Student.name == q) | (Student.student_code == q.upper())
    ).all()
    
    # 2. 부분 일치 (만약 완전 일치 없거나 적은 경우)
    if len(exact_matches) < 5:
        partial_matches = db.query(Student).filter(
            (Student.name.ilike(f"%{q}%")) | (Student.student_code.ilike(f"%{q}%"))
        ).limit(10).all()
        # 합치기 및 중복 제거
        combined = {s.id: s for s in exact_matches + partial_matches}.values()
    else:
        combined = exact_matches

    results = [
        {
            "id": s.id,
            "student_code": s.student_code,
            "name": s.name,
            "department": s.department or "미지정",
            "age": s.age,
            "photo_url": s.photo_url or "/static/uploads/profiles/default_avatar.svg",
            "is_active": s.is_active
        }
        for s in combined
    ]
    return JSONResponse(results)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, name: Optional[str] = None, db: Session = Depends(get_db)):
    error = request.query_params.get("error")
    candidates = []
    if name:
        candidates = db.query(Student).filter(Student.name == name.strip()).all()
    return templates.TemplateResponse("student/login.html", {
        "request": request,
        "error": error,
        "searched_name": name or "",
        "candidates": candidates
    })


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
        # 파일 크기 500KB 검사 (500 * 1024 bytes)
        photo_bytes = await photo.read()
        if len(photo_bytes) > 500 * 1024:
            return templates.TemplateResponse("student/register.html", {
                "request": request,
                "error": "이미지 파일 크기는 500KB 이하만 업로드 가능합니다."
            })
        
        filename = f"{student_code}_{photo.filename.replace(' ', '_')}"
        upload_dir = "static/uploads/profiles"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, "wb") as buffer:
            buffer.write(photo_bytes)
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

    # 최초 로그인 시 초기 비밀번호(0000) 변경 강제
    if student.password_hash == "0000":
        return RedirectResponse(url="/student/change_password?first_login=true", status_code=status.HTTP_303_SEE_OTHER)
    
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

    if student.password_hash == "0000":
        return RedirectResponse(url="/student/change_password?first_login=true", status_code=status.HTTP_303_SEE_OTHER)

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
    if student and student.password_hash == "0000":
        return RedirectResponse(url="/student/change_password?first_login=true", status_code=status.HTTP_303_SEE_OTHER)

    rules = db.query(TalentRule).filter(TalentRule.is_public == True, TalentRule.is_active == True).all()
    items = db.query(Item).filter(Item.is_active == True).all()

    return templates.TemplateResponse("student/rules.html", {
        "request": request,
        "student": student,
        "rules": rules,
        "items": items
    })


@router.get("/change_password", response_class=HTMLResponse)
async def change_password_page(request: Request, db: Session = Depends(get_db)):
    """학생 비밀번호 변경 화면 (최초 로그인 강제 변경 및 일반 변경 겸용)"""
    student = get_current_student(request, db)
    if not student:
        return RedirectResponse(url="/student/login", status_code=status.HTTP_303_SEE_OTHER)

    first_login = request.query_params.get("first_login") == "true" or student.password_hash == "0000"
    error = request.query_params.get("error")
    return templates.TemplateResponse("student/change_password.html", {
        "request": request,
        "student": student,
        "first_login": first_login,
        "error": error
    })


@router.post("/change_password")
async def change_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """학생 비밀번호 숫자 4자리 변경 처리"""
    student = get_current_student(request, db)
    if not student:
        return RedirectResponse(url="/student/login", status_code=status.HTTP_303_SEE_OTHER)

    new_pw = new_password.strip()
    conf_pw = confirm_password.strip()

    # 숫자 4자리 정규식 검증
    if not re.match(r"^\d{4}$", new_pw):
        return RedirectResponse(url="/student/change_password?error=format_error", status_code=status.HTTP_303_SEE_OTHER)

    # 초기 비밀번호 0000 사용 금지
    if new_pw == "0000":
        return RedirectResponse(url="/student/change_password?error=default_forbidden", status_code=status.HTTP_303_SEE_OTHER)

    # 비밀번호 확인 일치 여부
    if new_pw != conf_pw:
        return RedirectResponse(url="/student/change_password?error=mismatch", status_code=status.HTTP_303_SEE_OTHER)

    student.password_hash = new_pw
    student.updated_at = get_kst_now()
    db.commit()

    return RedirectResponse(url="/student/dashboard?msg=password_changed", status_code=status.HTTP_303_SEE_OTHER)


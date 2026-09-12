import os
import shutil
import csv
import io
import urllib.parse
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import (
    Student, TalentRule, TalentEarning, Item, Order, OrderItem, AnnualReset, AnnualSnapshot,
    Department, RuleCategory, ItemCategory, OrderAdjustmentLog, SystemConfig, get_system_config, set_system_config,
    TalentTalk
)
from app.config import ADMIN_PW
from app.timezone import get_kst_now
from app.image_utils import bytes_to_data_url

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


def decode_csv_content(content_bytes: bytes) -> str:
    """한국어 엑셀 CSV 인코딩(UTF-8 BOM, CP949, EUC-KR, UTF-8) 자동 감지 디코딩"""
    for encoding in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content_bytes.decode("utf-8", errors="replace")


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
    departments = [d.name for d in db.query(Department).filter(Department.is_active == True).order_by(Department.display_order.asc(), Department.id.asc()).all()]
    return templates.TemplateResponse("admin/students.html", {
        "request": request,
        "students": students,
        "departments": departments,
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
        photo_bytes = await photo.read()
        if len(photo_bytes) > 500 * 1024:
            return RedirectResponse(url="/admin/students?error=image_too_large", status_code=status.HTTP_303_SEE_OTHER)
        # Base64 Data URL로 인코딩하여 DB 영구 저장
        photo_url = bytes_to_data_url(photo_bytes, photo.filename)
        try:
            filename = f"{student_code}_{photo.filename.replace(' ', '_')}"
            upload_dir = "static/uploads/profiles"
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), "wb") as buffer:
                buffer.write(photo_bytes)
        except Exception:
            pass

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
        student.updated_at = get_kst_now()
        db.commit()
    return RedirectResponse(url="/admin/students?msg=activated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/deactivate")
async def deactivate_student(student_id: int, db: Session = Depends(get_db)):
    """학생 계정 비활성화 (로그인 및 키오스크 이용 제한)"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if student:
        student.is_active = False
        student.updated_at = get_kst_now()
        db.commit()
    return RedirectResponse(url="/admin/students?msg=deactivated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/reset_pw")
async def reset_student_password(student_id: int, db: Session = Depends(get_db)):
    """비밀번호를 분실한 학생의 비밀번호를 '0000'으로 초기화"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if student:
        student.password_hash = "0000"
        student.updated_at = get_kst_now()
        db.commit()
    return RedirectResponse(url="/admin/students?msg=pw_reset", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/students/{student_id}/edit")
async def edit_student(
    student_id: int,
    name: str = Form(...),
    department: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    is_active: str = Form("true"),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """기존 등록된 학생 정보(성명, 소속부서, 나이, 성별, 연락처, 이메일, 사진, 계정상태) 수정"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="해당 학생을 찾을 수 없습니다.")

    student.name = name.strip()
    student.department = department.strip() if department else None
    student.age = age
    student.gender = gender if gender in ["M", "F"] else None
    student.phone = phone.strip() if phone else None
    student.email = email.strip() if email else None
    student.is_active = (is_active in ["true", "True", "1", True])
    student.updated_at = get_kst_now()


    if photo and photo.filename:
        photo_bytes = await photo.read()
        if len(photo_bytes) > 500 * 1024:
            return RedirectResponse(url="/admin/students?error=image_too_large", status_code=status.HTTP_303_SEE_OTHER)
        # Base64 Data URL로 인코딩하여 DB 영구 저장
        student.photo_url = bytes_to_data_url(photo_bytes, photo.filename)
        try:
            filename = f"{student.student_code}_{photo.filename.replace(' ', '_')}"
            upload_dir = "static/uploads/profiles"
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), "wb") as buffer:
                buffer.write(photo_bytes)
        except Exception:
            pass

    db.commit()
    return RedirectResponse(url="/admin/students?msg=updated", status_code=status.HTTP_303_SEE_OTHER)



@router.get("/students/{student_id}/preview", response_class=HTMLResponse)
async def preview_student_screen(
    student_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """관리자 콘솔에서 특정 학생의 포털 화면 새 창 미리보기"""
    check_admin(request)
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="학생을 찾을 수 없습니다.")

    recent_earnings = db.query(TalentEarning).filter(TalentEarning.student_id == student.id)\
        .order_by(TalentEarning.created_at.desc()).limit(5).all()
    recent_orders = db.query(Order).filter(Order.student_id == student.id)\
        .order_by(Order.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("student/dashboard.html", {
        "request": request,
        "student": student,
        "recent_earnings": recent_earnings,
        "recent_orders": recent_orders,
        "is_admin_preview": True
    })


@router.get("/students/csv/template")
async def download_students_csv_template(request: Request):
    """학생 등록 CSV 양식 다운로드"""
    check_admin(request)
    headers = ["고유ID", "이름", "소속", "나이", "성별", "전화번호", "이메일"]
    sample_rows = [
        ["S004", "홍길동", "아동부", "11", "남", "010-1234-5678", "hong@church.org"],
        ["S005", "이영희", "유치부", "6", "여", "010-9876-5432", ""],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in sample_rows:
        writer.writerow(r)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=students_template.csv"}
    )


@router.post("/students/csv/upload")
async def upload_students_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """학생 일괄 등록 CSV 파일 업로드 및 형식 검증 (단일 트랜잭션 롤백 보장)"""
    check_admin(request)
    content_bytes = await file.read()
    if not content_bytes:
        msg = urllib.parse.quote("업로드된 CSV 파일이 비어 있습니다.")
        return RedirectResponse(url=f"/admin/students?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    content = decode_csv_content(content_bytes)
    reader = csv.reader(io.StringIO(content))
    rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        msg = urllib.parse.quote("유효한 데이터 행이 존재하지 않습니다.")
        return RedirectResponse(url=f"/admin/students?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    data_rows = rows[1:]
    if not data_rows:
        msg = urllib.parse.quote("헤더 아래에 등록할 학생 데이터 행이 없습니다.")
        return RedirectResponse(url=f"/admin/students?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    errors = []
    new_students = []
    seen_codes = set()

    for idx, row in enumerate(data_rows, start=2):
        if len(row) < 2:
            errors.append(f"{idx}행: 최소 [고유ID, 이름] 컬럼이 필요합니다.")
            continue

        code_raw = row[0].strip() if len(row) > 0 else ""
        name_raw = row[1].strip() if len(row) > 1 else ""
        dept_raw = row[2].strip() if len(row) > 2 else None
        age_raw = row[3].strip() if len(row) > 3 else None
        gender_raw = row[4].strip() if len(row) > 4 else None
        phone_raw = row[5].strip() if len(row) > 5 else None
        email_raw = row[6].strip() if len(row) > 6 else None

        if not name_raw:
            errors.append(f"{idx}행: 이름은 필수 입력값입니다.")
            continue

        # 나이 형식 검증
        age = None
        if age_raw:
            try:
                age = int(age_raw)
                if age < 0 or age > 100:
                    errors.append(f"{idx}행: 나이는 0~100 사이여야 합니다.")
                    continue
            except ValueError:
                errors.append(f"{idx}행: 나이 '{age_raw}'는 올바른 숫자가 아닙니다.")
                continue

        # 고유 ID 처리 및 중복 검증
        if code_raw:
            if code_raw in seen_codes:
                errors.append(f"{idx}행: CSV 내 중복된 고유ID '{code_raw}'가 존재합니다.")
                continue
            if db.query(Student).filter(Student.student_code == code_raw).first():
                errors.append(f"{idx}행: DB에 이미 등록된 고유ID '{code_raw}'입니다.")
                continue
            student_code = code_raw
        else:
            count = db.query(Student).count() + len(new_students)
            student_code = f"S{count + 1:03d}"
            while db.query(Student).filter(Student.student_code == student_code).first() or student_code in seen_codes:
                count += 1
                student_code = f"S{count + 1:03d}"

        seen_codes.add(student_code)

        if gender_raw in ["남", "남자", "M", "m"]:
            gender = "M"
        elif gender_raw in ["여", "여자", "F", "f"]:
            gender = "F"
        else:
            gender = gender_raw if gender_raw else None

        student = Student(
            student_code=student_code,
            name=name_raw,
            password_hash="0000",
            photo_url="/static/uploads/profiles/default_avatar.svg",
            department=dept_raw if dept_raw else None,
            age=age,
            gender=gender,
            phone=phone_raw if phone_raw else None,
            email=email_raw if email_raw else None,
            current_talent=0,
            total_earned=0,
            total_spent=0,
            is_active=True,
            created_at=get_kst_now(),
            updated_at=get_kst_now()
        )
        new_students.append(student)

    if errors:
        db.rollback()
        error_msg = "; ".join(errors[:5])
        if len(errors) > 5:
            error_msg += f" 외 {len(errors)-5}건 오류"
        msg = urllib.parse.quote(f"CSV 형식 검증 실패 ({len(errors)}건): {error_msg}")
        return RedirectResponse(url=f"/admin/students?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    db.add_all(new_students)
    db.commit()
    return RedirectResponse(url=f"/admin/students?msg=csv_success&count={len(new_students)}", status_code=status.HTTP_303_SEE_OTHER)



# -------------------------------------------------------------
# 2. 학생의 달란트 실적 등록
# -------------------------------------------------------------
@router.get("/talent/grant", response_class=HTMLResponse)
async def grant_talent_page(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    students = db.query(Student).filter(Student.is_active == True).order_by(Student.department.asc(), Student.name.asc()).all()
    rules = db.query(TalentRule).filter(TalentRule.is_active == True).all()
    departments = [d.name for d in db.query(Department).filter(Department.is_active == True).order_by(Department.display_order.asc(), Department.id.asc()).all()]
    return templates.TemplateResponse("admin/talent_grant.html", {
        "request": request,
        "students": students,
        "rules": rules,
        "departments": departments
    })


@router.post("/talent/grant")
async def grant_talent(
    student_ids: List[int] = Form(...),
    rule_id: Optional[int] = Form(None),
    points: int = Form(...),
    reason: str = Form(...),
    granted_by: str = Form(...),
    db: Session = Depends(get_db)
):
    """달란트 실적 등록 및 잔여/누적 달란트 가산 (단일 또는 복수 학생 일괄 동시 지급)"""
    if not student_ids:
        return RedirectResponse(url="/admin/talent/grant?error=no_students", status_code=status.HTTP_303_SEE_OTHER)

    now = get_kst_now()
    count = 0
    for sid in student_ids:
        student = db.query(Student).filter(Student.id == sid).first()
        if student:
            earning = TalentEarning(
                student_id=student.id,
                rule_id=rule_id if rule_id and rule_id > 0 else None,
                points=points,
                reason=reason.strip(),
                granted_by=granted_by.strip(),
                created_at=now
            )
            student.current_talent += points
            student.total_earned += points
            db.add(earning)
            count += 1

    db.commit()
    return RedirectResponse(url=f"/admin/talent/grant?msg=granted_multi&count={count}&points={points}", status_code=status.HTTP_303_SEE_OTHER)



@router.get("/talent/csv/template")
async def download_talent_csv_template(request: Request):
    """달란트 일괄 지급 CSV 양식 다운로드"""
    check_admin(request)
    headers = ["학생고유ID", "달란트점수", "지급사유", "지급자"]
    sample_rows = [
        ["S001", "2", "주일예배 출석 모범", "김철수"],
        ["S002", "5", "성경 암송 10절 완송", "교육부"],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in sample_rows:
        writer.writerow(r)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=talent_grant_template.csv"}
    )


@router.post("/talent/csv/upload")
async def upload_talent_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """달란트 일괄 지급 CSV 파일 업로드 및 형식 검증 (단일 트랜잭션 롤백 보장)"""
    check_admin(request)
    content_bytes = await file.read()
    if not content_bytes:
        msg = urllib.parse.quote("업로드된 CSV 파일이 비어 있습니다.")
        return RedirectResponse(url=f"/admin/talent/grant?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    content = decode_csv_content(content_bytes)
    reader = csv.reader(io.StringIO(content))
    rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        msg = urllib.parse.quote("유효한 데이터 행이 존재하지 않습니다.")
        return RedirectResponse(url=f"/admin/talent/grant?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    data_rows = rows[1:]
    if not data_rows:
        msg = urllib.parse.quote("지급할 실적 데이터 행이 없습니다.")
        return RedirectResponse(url=f"/admin/talent/grant?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    errors = []
    grant_tasks = []

    for idx, row in enumerate(data_rows, start=2):
        if len(row) < 4:
            errors.append(f"{idx}행: [학생고유ID, 달란트점수, 지급사유, 지급자] 4개 항목이 모두 필요합니다.")
            continue

        student_code = row[0].strip()
        points_raw = row[1].strip()
        reason = row[2].strip()
        granted_by = row[3].strip()

        if not student_code:
            errors.append(f"{idx}행: 학생고유ID는 필수입니다.")
            continue

        student = db.query(Student).filter(Student.student_code == student_code).first()
        if not student:
            errors.append(f"{idx}행: 학생고유ID '{student_code}'을(를) 시스템에서 찾을 수 없습니다.")
            continue

        try:
            points = int(points_raw)
            if points <= 0:
                errors.append(f"{idx}행: 달란트 점수는 1 이상의 양수여야 합니다. (입력값: {points_raw})")
                continue
        except ValueError:
            errors.append(f"{idx}행: 달란트 점수 '{points_raw}'는 올바른 정수가 아닙니다.")
            continue

        if not reason:
            errors.append(f"{idx}행: 지급사유는 필수입니다.")
            continue

        if not granted_by:
            errors.append(f"{idx}행: 지급자(교사/부서)는 필수입니다.")
            continue

        grant_tasks.append((student, points, reason, granted_by))

    if errors:
        db.rollback()
        error_msg = "; ".join(errors[:5])
        if len(errors) > 5:
            error_msg += f" 외 {len(errors)-5}건 오류"
        msg = urllib.parse.quote(f"CSV 형식 검증 실패 ({len(errors)}건): {error_msg}")
        return RedirectResponse(url=f"/admin/talent/grant?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    now = get_kst_now()
    for student, points, reason, granted_by in grant_tasks:
        earning = TalentEarning(
            student_id=student.id,
            rule_id=None,
            points=points,
            reason=reason,
            granted_by=granted_by,
            created_at=now
        )
        student.current_talent += points
        student.total_earned += points
        db.add(earning)

    db.commit()
    return RedirectResponse(url=f"/admin/talent/grant?msg=csv_success&count={len(grant_tasks)}", status_code=status.HTTP_303_SEE_OTHER)



# -------------------------------------------------------------
# 3. 달란트 지급 기준 관리
# -------------------------------------------------------------
@router.get("/talent/rules", response_class=HTMLResponse)
async def manage_rules(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    rules = db.query(TalentRule).order_by(TalentRule.id.asc()).all()
    categories = db.query(RuleCategory).filter(RuleCategory.is_active == True).order_by(RuleCategory.display_order.asc(), RuleCategory.id.asc()).all()
    return templates.TemplateResponse("admin/talent_rules.html", {
        "request": request,
        "rules": rules,
        "categories": categories
    })


@router.post("/talent/rules/create")
async def create_rule(
    title: str = Form(...),
    category: str = Form(...),
    points: int = Form(...),
    description: Optional[str] = Form(None),
    is_public: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    count = db.query(TalentRule).count()
    rule_code = f"R{count + 1:03d}"
    is_pub = (is_public == "true" or is_public == "on" or is_public is True)
    rule = TalentRule(
        rule_code=rule_code,
        title=title.strip(),
        category=category.strip(),
        points=points,
        description=description.strip() if description else None,
        is_public=is_pub,
        is_active=True,
        created_at=get_kst_now()
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(url="/admin/talent/rules?msg=created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/talent/rules/{rule_id}/edit")
async def edit_rule(
    rule_id: int,
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    points: int = Form(...),
    description: Optional[str] = Form(None),
    is_public: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """지급 기준 수정 및 공개여부 변경"""
    check_admin(request)
    rule = db.query(TalentRule).filter(TalentRule.id == rule_id).first()
    if rule:
        rule.title = title.strip()
        rule.category = category.strip()
        rule.points = points
        rule.description = description.strip() if description else None
        rule.is_public = (is_public == "true" or is_public == "on" or is_public is True)
        db.commit()
    return RedirectResponse(url="/admin/talent/rules?msg=updated", status_code=status.HTTP_303_SEE_OTHER)


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
    categories = db.query(ItemCategory).filter(ItemCategory.is_active == True).order_by(ItemCategory.display_order.asc(), ItemCategory.id.asc()).all()
    
    # 카테고리가 비어있는 경우 기본 카테고리 자동 주입 보장
    if not categories:
        default_names = ["먹거리", "문화생활", "문구/완구", "도서/학용품", "기타"]
        for idx, cname in enumerate(default_names, 1):
            db.add(ItemCategory(name=cname, display_order=idx, is_active=True, created_at=get_kst_now()))
        db.commit()
        categories = db.query(ItemCategory).filter(ItemCategory.is_active == True).order_by(ItemCategory.display_order.asc(), ItemCategory.id.asc()).all()

    return templates.TemplateResponse("admin/items.html", {
        "request": request,
        "items": items,
        "categories": categories
    })



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
        image_bytes = await image.read()
        if len(image_bytes) > 500 * 1024:
            return RedirectResponse(url="/admin/items?error=image_too_large", status_code=status.HTTP_303_SEE_OTHER)
        # Base64 Data URL로 인코딩하여 DB 영구 저장
        image_url = bytes_to_data_url(image_bytes, image.filename)
        try:
            filename = f"{item_code}_{image.filename.replace(' ', '_')}"
            upload_dir = "static/images"
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), "wb") as buffer:
                buffer.write(image_bytes)
        except Exception:
            pass

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


@router.post("/items/{item_id}/edit")
async def edit_item(
    item_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    price: int = Form(...),
    stock: int = Form(...),
    is_active: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """매점 물품 상세 정보 (상품명, 카테고리/분류, 가격, 재고, 판매상태, 사진) 종합 수정"""
    check_admin(request)
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return RedirectResponse(url="/admin/items?error=item_not_found", status_code=status.HTTP_303_SEE_OTHER)

    item.name = name.strip()
    item.category = category.strip()
    item.price = max(1, price)
    item.stock = max(0, stock)
    item.is_active = (is_active in ["true", "on", "1", True])

    # 선택 사항: 이미지 파일 업로드 시 갱신
    if image and image.filename:
        image_bytes = await image.read()
        if len(image_bytes) > 500 * 1024:
            return RedirectResponse(url=f"/admin/items?error=image_too_large&item_id={item_id}", status_code=status.HTTP_303_SEE_OTHER)
        image_url = bytes_to_data_url(image_bytes, image.filename)
        item.image_url = image_url
        try:
            filename = f"{item.item_code}_{image.filename.replace(' ', '_')}"
            upload_dir = "static/images"
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), "wb") as buffer:
                buffer.write(image_bytes)
        except Exception:
            pass

    db.commit()
    return RedirectResponse(url="/admin/items?msg=edited", status_code=status.HTTP_303_SEE_OTHER)



@router.get("/items/csv/template")
async def download_items_csv_template(request: Request):
    """물품 등록 CSV 양식 다운로드"""
    check_admin(request)
    headers = ["상품코드", "상품명", "카테고리", "가격", "재고"]
    sample_rows = [
        ["P004", "미니초코파이", "먹거리", "1", "100"],
        ["P005", "달란트지우개세트", "문구/완구", "2", "30"],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for r in sample_rows:
        writer.writerow(r)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=items_template.csv"}
    )


@router.post("/items/csv/upload")
async def upload_items_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """물품 일괄 등록 CSV 파일 업로드 및 형식 검증 (단일 트랜잭션 롤백 보장)"""
    check_admin(request)
    content_bytes = await file.read()
    if not content_bytes:
        msg = urllib.parse.quote("업로드된 CSV 파일이 비어 있습니다.")
        return RedirectResponse(url=f"/admin/items?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    content = decode_csv_content(content_bytes)
    reader = csv.reader(io.StringIO(content))
    rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        msg = urllib.parse.quote("유효한 데이터 행이 존재하지 않습니다.")
        return RedirectResponse(url=f"/admin/items?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    data_rows = rows[1:]
    if not data_rows:
        msg = urllib.parse.quote("등록할 물품 데이터 행이 없습니다.")
        return RedirectResponse(url=f"/admin/items?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    errors = []
    new_items = []
    seen_codes = set()

    for idx, row in enumerate(data_rows, start=2):
        if len(row) < 5:
            errors.append(f"{idx}행: [상품코드, 상품명, 카테고리, 가격, 재고] 5개 항목이 모두 필요합니다.")
            continue

        code_raw = row[0].strip()
        name_raw = row[1].strip()
        cat_raw = row[2].strip()
        price_raw = row[3].strip()
        stock_raw = row[4].strip()

        if not name_raw:
            errors.append(f"{idx}행: 상품명은 필수입니다.")
            continue

        if not cat_raw:
            errors.append(f"{idx}행: 카테고리는 필수입니다.")
            continue

        try:
            price = int(price_raw)
            if price <= 0:
                errors.append(f"{idx}행: 가격은 1 이상의 양수여야 합니다. (입력값: {price_raw})")
                continue
        except ValueError:
            errors.append(f"{idx}행: 가격 '{price_raw}'는 올바른 정수가 아닙니다.")
            continue

        try:
            stock = int(stock_raw)
            if stock < 0:
                errors.append(f"{idx}행: 재고는 0 이상이어야 합니다. (입력값: {stock_raw})")
                continue
        except ValueError:
            errors.append(f"{idx}행: 재고 '{stock_raw}'는 올바른 정수가 아닙니다.")
            continue

        if code_raw:
            if code_raw in seen_codes:
                errors.append(f"{idx}행: CSV 내 중복된 상품코드 '{code_raw}'가 있습니다.")
                continue
            existing = db.query(Item).filter(Item.item_code == code_raw).first()
            if existing:
                errors.append(f"{idx}행: 이미 등록된 상품코드 '{code_raw}'입니다.")
                continue
            item_code = code_raw
        else:
            count = db.query(Item).count() + len(new_items)
            item_code = f"P{count + 1:03d}"
            while db.query(Item).filter(Item.item_code == item_code).first() or item_code in seen_codes:
                count += 1
                item_code = f"P{count + 1:03d}"

        seen_codes.add(item_code)

        item = Item(
            item_code=item_code,
            name=name_raw,
            category=cat_raw,
            price=price,
            stock=stock,
            image_url="/static/images/ramen.svg",
            is_active=True,
            created_at=get_kst_now()
        )
        new_items.append(item)

    if errors:
        db.rollback()
        error_msg = "; ".join(errors[:5])
        if len(errors) > 5:
            error_msg += f" 외 {len(errors)-5}건 오류"
        msg = urllib.parse.quote(f"CSV 형식 검증 실패 ({len(errors)}건): {error_msg}")
        return RedirectResponse(url=f"/admin/items?csv_error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    db.add_all(new_items)
    db.commit()
    return RedirectResponse(url=f"/admin/items?msg=csv_success&count={len(new_items)}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/{item_id}/update_image")
async def update_item_image(
    item_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """판매 상품 이미지 신규 등록 및 교체"""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="물품을 찾을 수 없습니다.")

    if image and image.filename:
        image_bytes = await image.read()
        if len(image_bytes) > 500 * 1024:
            return RedirectResponse(url="/admin/items?error=image_too_large", status_code=status.HTTP_303_SEE_OTHER)
        # Base64 Data URL로 인코딩하여 DB 영구 저장
        item.image_url = bytes_to_data_url(image_bytes, image.filename)
        try:
            filename = f"item_{item.item_code}_{image.filename.replace(' ', '_')}"
            upload_dir = "static/uploads/items"
            os.makedirs(upload_dir, exist_ok=True)
            with open(os.path.join(upload_dir, filename), "wb") as buffer:
                buffer.write(image_bytes)
        except Exception:
            pass
        db.commit()

    return RedirectResponse(url="/admin/items?msg=image_updated", status_code=status.HTTP_303_SEE_OTHER)



# -------------------------------------------------------------
# 9. 달란트 사용 내역 수정 기능 (기존 구매 취소 및 롤백 후 변경)
# -------------------------------------------------------------
@router.get("/orders", response_class=HTMLResponse)
async def list_orders(
    request: Request,
    student_id: Optional[int] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    check_admin(request)

    # 전체 학생 목록 (학생별 조회 드롭다운용)
    students = db.query(Student).order_by(Student.department.asc(), Student.name.asc()).all()

    # 주문 기본 쿼리
    query = db.query(Order).join(Order.student)

    selected_student = None
    if student_id:
        query = query.filter(Order.student_id == student_id)
        selected_student = db.query(Student).filter(Student.id == student_id).first()

    if q and q.strip():
        search_str = f"%{q.strip()}%"
        query = query.filter(
            (Student.name.ilike(search_str)) |
            (Student.student_code.ilike(search_str)) |
            (Order.order_number.ilike(search_str))
        )

    orders = query.order_by(Order.created_at.desc()).all()
    items = db.query(Item).filter(Item.is_active == True).all()

    # 최근 구매내역 수정/반품/환불 조정 이력 로그 (최근 50건)
    adj_query = db.query(OrderAdjustmentLog).join(OrderAdjustmentLog.student)
    if student_id:
        adj_query = adj_query.filter(OrderAdjustmentLog.student_id == student_id)
    if q and q.strip():
        search_str = f"%{q.strip()}%"
        adj_query = adj_query.filter(
            (Student.name.ilike(search_str)) |
            (Student.student_code.ilike(search_str)) |
            (OrderAdjustmentLog.order_number.ilike(search_str))
        )
    adjustments = adj_query.order_by(OrderAdjustmentLog.adjusted_at.desc()).limit(50).all()

    return templates.TemplateResponse("admin/orders.html", {
        "request": request,
        "orders": orders,
        "items": items,
        "students": students,
        "selected_student_id": student_id,
        "selected_student": selected_student,
        "q": q or "",
        "adjustments": adjustments
    })


@router.post("/orders/{order_id}/modify")
async def modify_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """구매 내역 수정/반품 로직: 기존 구매 취소(원상복구) 후 신규 구매 내역 갱신 (복수 품목 지원 및 조정 이력 자동 기록)"""
    check_admin(request)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != "COMPLETED":
        return RedirectResponse(url="/admin/orders?error=invalid_order", status_code=status.HTTP_303_SEE_OTHER)

    student = order.student
    form_data = await request.form()
    action = form_data.get("action")
    admin_name = form_data.get("admin_name", "").strip()

    # 1. 처리 담당자 성명 필수값 엄격 검증
    if not admin_name:
        err_msg = urllib.parse.quote("수정/반품 처리를 진행한 담당자 성명을 반드시 입력해야 합니다.")
        return RedirectResponse(url=f"/admin/orders?error={err_msg}&student_id={student.id}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        # 기존 결제 상태 및 품목 요약 사전 백업
        old_items_summary = ", ".join([f"{it.item_name} × {it.quantity}개" for it in order.items])
        prev_total = order.total_points
        # 수정 전 학생 순수 보유 달란트 및 이 주문 취소 시 최대 가용 달란트
        student_current = student.current_talent
        max_available_talent = student_current + prev_total

        # 1. 기존 사용 달란트 및 재고 전액 원상복구 (Rollback)
        student.current_talent += order.total_points
        student.total_spent -= order.total_points
        for o_item in order.items:
            if o_item.item:
                o_item.item.stock += o_item.quantity
            elif o_item.item_id:
                it = db.query(Item).filter(Item.id == o_item.item_id).first()
                if it:
                    it.stock += o_item.quantity

        if action == "refund":
            # 단순 반품/환불 처리
            order.status = "REFUNDED"
            order.updated_at = get_kst_now()

            # 조정 감사 이력 기록
            adj_log = OrderAdjustmentLog(
                order_id=order.id,
                order_number=order.order_number,
                student_id=student.id,
                action_type="REFUND",
                prev_total_points=prev_total,
                new_total_points=0,
                diff_points=prev_total,  # 전액 환불 반환
                details=f"전체 반품/환불 완료 (취소 품목: {old_items_summary}, +{prev_total}달란트 잔액 복구)",
                admin_name=admin_name,
                adjusted_at=get_kst_now()
            )
            db.add(adj_log)
            db.commit()

            redirect_url = f"/admin/orders?msg=refunded&student_id={student.id}"
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        elif action == "update":
            # 다중 품목 파싱
            raw_item_ids = form_data.getlist("item_ids")
            raw_item_names = form_data.getlist("item_names")
            raw_unit_prices = form_data.getlist("unit_prices")
            raw_quantities = form_data.getlist("quantities")

            # 기존 단일 폼 호환
            if not raw_item_ids and form_data.get("new_item_id"):
                raw_item_ids = [form_data.get("new_item_id")]
                raw_quantities = [form_data.get("new_quantity", 1)]

            # 품목 데이터 정규화 및 수량 유효성 검사
            items_parsed = []
            for idx in range(len(raw_quantities)):
                r_qty = raw_quantities[idx]
                r_id = raw_item_ids[idx] if idx < len(raw_item_ids) else "0"
                r_name = raw_item_names[idx].strip() if idx < len(raw_item_names) else ""
                r_price = raw_unit_prices[idx] if idx < len(raw_unit_prices) else "0"

                try:
                    qty = int(r_qty)
                    if qty <= 0:
                        continue
                    iid = int(r_id) if r_id else 0
                    uprice = int(r_price) if r_price else 0
                except (ValueError, TypeError):
                    continue

                items_parsed.append({
                    "id": iid,
                    "name": r_name,
                    "price": uprice,
                    "quantity": qty
                })

            if not items_parsed:
                db.rollback()
                err_msg = urllib.parse.quote("주문 품목이 최소 1개 이상 존재해야 합니다. (전체 취소는 '반품/환불' 기능을 이용해 주세요)")
                return RedirectResponse(url=f"/admin/orders?error={err_msg}&student_id={student.id}", status_code=status.HTTP_303_SEE_OTHER)

            # 품목 객체 매핑 및 재고/가격 검증
            new_total = 0
            items_to_process = []
            for entry in items_parsed:
                iid = entry["id"]
                iname = entry["name"]
                qty = entry["quantity"]
                uprice = entry["price"]

                item = None
                if iid > 0:
                    item = db.query(Item).filter(Item.id == iid).first()
                if not item and iname:
                    item = db.query(Item).filter(Item.name == iname).first()

                if item:
                    if item.stock < qty:
                        db.rollback()
                        err_msg = urllib.parse.quote(f"'{item.name}' 상품의 매점 재고가 부족합니다. (현재 재고: {item.stock}개, 요청 수량: {qty}개)")
                        return RedirectResponse(
                            url=f"/admin/orders?error={err_msg}&student_id={student.id}",
                            status_code=status.HTTP_303_SEE_OTHER
                        )
                    unit_cost = item.price
                    actual_name = item.name
                    actual_id = item.id
                else:
                    # 마스터 품목이 없는 경우 (과거 품목 보존용)
                    unit_cost = max(0, uprice)
                    actual_name = iname or "지정 품목"
                    actual_id = None

                subtotal = unit_cost * qty
                new_total += subtotal
                items_to_process.append((item, actual_id, actual_name, unit_cost, qty, subtotal))

            # 2. 학생 잔여 달란트 정밀 검증 (수량 증가로 인해 잔고가 부족한 경우 원천 차단)
            if student.current_talent < new_total:
                db.rollback()
                shortage = new_total - max_available_talent
                needed_diff = new_total - prev_total
                err_msg = urllib.parse.quote(
                    f"학생({student.name})의 달란트 잔고가 부족하여 수량을 증가시킬 수 없습니다. "
                    f"(수정 전 보유 잔고: {student_current}달란트, 추가 필요: {needed_diff}달란트 / {shortage}달란트 부족)"
                )
                return RedirectResponse(url=f"/admin/orders?error={err_msg}&student_id={student.id}", status_code=status.HTTP_303_SEE_OTHER)

            # 새 차감 적용
            student.current_talent -= new_total
            student.total_spent += new_total
            for item, _, _, _, qty, _ in items_to_process:
                if item:
                    item.stock -= qty

            # 기존 주문 세부 품목 삭제 (안전한 cascade 처리)
            for o_item in list(order.items):
                db.delete(o_item)
            db.flush()

            # 신규 품목 추가
            for _, actual_id, actual_name, unit_cost, qty, subtotal in items_to_process:
                new_order_item = OrderItem(
                    order_id=order.id,
                    item_id=actual_id,
                    item_name=actual_name,
                    unit_price=unit_cost,
                    quantity=qty,
                    subtotal_points=subtotal
                )
                db.add(new_order_item)

            new_items_summary = ", ".join([f"{actual_name} × {qty}개" for _, _, actual_name, _, qty, _ in items_to_process])
            diff = prev_total - new_total

            diff_desc = f"+{diff}달란트 환불 반환" if diff > 0 else (f"{abs(diff)}달란트 추가 차감" if diff < 0 else "금액 변동 없음")
            adj_log = OrderAdjustmentLog(
                order_id=order.id,
                order_number=order.order_number,
                student_id=student.id,
                action_type="UPDATE",
                prev_total_points=prev_total,
                new_total_points=new_total,
                diff_points=diff,
                details=f"품목/수량 수정: [{old_items_summary}] ➔ [{new_items_summary}] (결제: {prev_total} ➔ {new_total}달란트, {diff_desc})",
                admin_name=admin_name,
                adjusted_at=get_kst_now()
            )
            db.add(adj_log)

            order.total_points = new_total
            order.status = "COMPLETED"
            order.updated_at = get_kst_now()
            db.commit()
            return RedirectResponse(url=f"/admin/orders?msg=modified&student_id={student.id}", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        err_msg = urllib.parse.quote(f"주문 수정 처리 중 오류가 발생했습니다: {str(e)}")
        return RedirectResponse(url=f"/admin/orders?error={err_msg}&student_id={student.id}", status_code=status.HTTP_303_SEE_OTHER)

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


# -------------------------------------------------------------
# 11. 시스템 환경 설정 (소속부서 및 지급 기준 분류 관리)
# -------------------------------------------------------------
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    departments = db.query(Department).order_by(Department.display_order.asc(), Department.id.asc()).all()
    categories = db.query(RuleCategory).order_by(RuleCategory.display_order.asc(), RuleCategory.id.asc()).all()
    item_categories = db.query(ItemCategory).order_by(ItemCategory.display_order.asc(), ItemCategory.id.asc()).all()

    # 상품 카테고리가 비어있는 경우 기본 카테고리 자동 시딩 보장
    if not item_categories:
        default_names = ["먹거리", "문화생활", "문구/완구", "도서/학용품", "기타"]
        for idx, cname in enumerate(default_names, 1):
            db.add(ItemCategory(name=cname, display_order=idx, is_active=True, created_at=get_kst_now()))
        db.commit()
        item_categories = db.query(ItemCategory).order_by(ItemCategory.display_order.asc(), ItemCategory.id.asc()).all()

    kiosk_auto_logout_seconds = int(get_system_config(db, "kiosk_auto_logout_seconds", "10"))
    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "departments": departments,
        "categories": categories,
        "item_categories": item_categories,
        "kiosk_auto_logout_seconds": kiosk_auto_logout_seconds
    })



@router.post("/settings/kiosk")
async def update_kiosk_settings(
    request: Request,
    kiosk_auto_logout_seconds: int = Form(...),
    db: Session = Depends(get_db)
):
    """매점 키오스크 환경설정 (자동 로그아웃 시간 등) 갱신"""
    check_admin(request)
    if kiosk_auto_logout_seconds < 5:
        kiosk_auto_logout_seconds = 5
    elif kiosk_auto_logout_seconds > 600:
        kiosk_auto_logout_seconds = 600

    set_system_config(
        db,
        key="kiosk_auto_logout_seconds",
        value=str(kiosk_auto_logout_seconds),
        description="매점 키오스크 로그인 세션 자동 로그아웃 대기 시간 (초)"
    )
    return RedirectResponse(url="/admin/settings?msg=kiosk_updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/departments/create")
async def create_department(
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    db: Session = Depends(get_db)
):
    check_admin(request)
    clean_name = name.strip()
    if db.query(Department).filter(Department.name == clean_name).first():
        return RedirectResponse(url="/admin/settings?error=dept_duplicate", status_code=status.HTTP_303_SEE_OTHER)
    new_dept = Department(name=clean_name, display_order=display_order, is_active=True, created_at=get_kst_now())
    db.add(new_dept)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=dept_created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/departments/{dept_id}/edit")
async def edit_department(
    dept_id: int,
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    check_admin(request)
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if dept:
        clean_name = name.strip()
        existing = db.query(Department).filter(Department.name == clean_name, Department.id != dept_id).first()
        if existing:
            return RedirectResponse(url="/admin/settings?error=dept_duplicate", status_code=status.HTTP_303_SEE_OTHER)
        dept.name = clean_name
        dept.display_order = display_order
        dept.is_active = (is_active == "true" or is_active is True)
        db.commit()
    return RedirectResponse(url="/admin/settings?msg=dept_updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/departments/{dept_id}/delete")
async def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if dept:
        db.delete(dept)
        db.commit()
    return RedirectResponse(url="/admin/settings?msg=dept_deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/categories/create")
async def create_category(
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    db: Session = Depends(get_db)
):
    check_admin(request)
    clean_name = name.strip()
    if db.query(RuleCategory).filter(RuleCategory.name == clean_name).first():
        return RedirectResponse(url="/admin/settings?error=cat_duplicate", status_code=status.HTTP_303_SEE_OTHER)
    new_cat = RuleCategory(name=clean_name, display_order=display_order, is_active=True, created_at=get_kst_now())
    db.add(new_cat)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=cat_created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/categories/{cat_id}/edit")
async def edit_category(
    cat_id: int,
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    check_admin(request)
    cat = db.query(RuleCategory).filter(RuleCategory.id == cat_id).first()
    if cat:
        clean_name = name.strip()
        existing = db.query(RuleCategory).filter(RuleCategory.name == clean_name, RuleCategory.id != cat_id).first()
        if existing:
            return RedirectResponse(url="/admin/settings?error=cat_duplicate", status_code=status.HTTP_303_SEE_OTHER)
        cat.name = clean_name
        cat.display_order = display_order
        cat.is_active = (is_active == "true" or is_active is True)
        db.commit()
    return RedirectResponse(url="/admin/settings?msg=cat_updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/categories/{cat_id}/delete")
async def delete_category(cat_id: int, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    cat = db.query(RuleCategory).filter(RuleCategory.id == cat_id).first()
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse(url="/admin/settings?msg=cat_deleted", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 매점 물품/상품 분류(카테고리) 설정 CRUD
# -------------------------------------------------------------
@router.post("/settings/item_categories/create")
async def create_item_category(
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    db: Session = Depends(get_db)
):
    check_admin(request)
    clean_name = name.strip()
    if db.query(ItemCategory).filter(ItemCategory.name == clean_name).first():
        return RedirectResponse(url="/admin/settings?error=item_cat_duplicate#item-categories", status_code=status.HTTP_303_SEE_OTHER)
    new_cat = ItemCategory(name=clean_name, display_order=display_order, is_active=True, created_at=get_kst_now())
    db.add(new_cat)
    db.commit()
    return RedirectResponse(url="/admin/settings?msg=item_cat_created#item-categories", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/item_categories/{cat_id}/edit")
async def edit_item_category(
    cat_id: int,
    request: Request,
    name: str = Form(...),
    display_order: int = Form(1),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    check_admin(request)
    cat = db.query(ItemCategory).filter(ItemCategory.id == cat_id).first()
    if cat:
        clean_name = name.strip()
        existing = db.query(ItemCategory).filter(ItemCategory.name == clean_name, ItemCategory.id != cat_id).first()
        if existing:
            return RedirectResponse(url="/admin/settings?error=item_cat_duplicate#item-categories", status_code=status.HTTP_303_SEE_OTHER)
        
        old_name = cat.name
        cat.name = clean_name
        cat.display_order = display_order
        cat.is_active = (is_active == "true" or is_active is True)

        # 기존 상품의 카테고리명도 함께 일괄 업데이트하여 일관성 유지
        if old_name != clean_name:
            items_to_update = db.query(Item).filter(Item.category == old_name).all()
            for it in items_to_update:
                it.category = clean_name

        db.commit()
    return RedirectResponse(url="/admin/settings?msg=item_cat_updated#item-categories", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/item_categories/{cat_id}/delete")
async def delete_item_category(cat_id: int, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    cat = db.query(ItemCategory).filter(ItemCategory.id == cat_id).first()
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse(url="/admin/settings?msg=item_cat_deleted#item-categories", status_code=status.HTTP_303_SEE_OTHER)


# -------------------------------------------------------------
# 12. 달란트 톡톡 (소통 공간) 관리
# -------------------------------------------------------------
@router.get("/talks", response_class=HTMLResponse)
async def manage_talks(
    request: Request,
    q: Optional[str] = None,
    filter_status: Optional[str] = "all",
    db: Session = Depends(get_db)
):
    """달란트 톡톡 글 전체 모니터링 및 부적절한 글 관리자 삭제"""
    check_admin(request)
    query = db.query(TalentTalk)

    if filter_status == "active":
        query = query.filter(TalentTalk.is_deleted == False)
    elif filter_status == "deleted":
        query = query.filter(TalentTalk.is_deleted == True)

    if q:
        clean_q = q.strip()
        query = query.join(Student).filter(
            (TalentTalk.content.ilike(f"%{clean_q}%")) |
            (Student.name.ilike(f"%{clean_q}%")) |
            (Student.student_code.ilike(f"%{clean_q}%")) |
            (TalentTalk.deleted_by.ilike(f"%{clean_q}%"))
        )

    talks = query.order_by(TalentTalk.created_at.desc()).all()
    total_count = db.query(TalentTalk).count()
    active_count = db.query(TalentTalk).filter(TalentTalk.is_deleted == False).count()
    deleted_count = db.query(TalentTalk).filter(TalentTalk.is_deleted == True).count()

    return templates.TemplateResponse("admin/talks.html", {
        "request": request,
        "talks": talks,
        "q": q or "",
        "filter_status": filter_status,
        "total_count": total_count,
        "active_count": active_count,
        "deleted_count": deleted_count
    })


@router.post("/talks/{talk_id}/delete")
async def delete_talk_by_admin(
    talk_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """관리자 실명 입력 기반 부적절 글 삭제 (감사 이력 영구 보존)"""
    check_admin(request)
    form_data = await request.form()
    admin_name = form_data.get("admin_name", "").strip()
    delete_reason = form_data.get("delete_reason", "").strip() or "부적절한 내용 (관리자 조치)"

    if not admin_name:
        err = urllib.parse.quote("삭제 처리를 진행하는 담당자 성명을 반드시 입력해야 합니다.")
        return RedirectResponse(url=f"/admin/talks?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    talk = db.query(TalentTalk).filter(TalentTalk.id == talk_id).first()
    if talk:
        talk.is_deleted = True
        talk.deleted_by = admin_name
        talk.deleted_by_role = "ADMIN"
        talk.delete_reason = delete_reason
        talk.deleted_at = get_kst_now()
        db.commit()

    return RedirectResponse(url="/admin/talks?msg=deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/talks/{talk_id}/restore")
async def restore_talk_by_admin(
    talk_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """삭제된 글 관리자 원클릭 복구"""
    check_admin(request)
    talk = db.query(TalentTalk).filter(TalentTalk.id == talk_id).first()
    if talk:
        talk.is_deleted = False
        talk.deleted_by = None
        talk.deleted_by_role = None
        talk.delete_reason = None
        talk.deleted_at = None
        db.commit()

    return RedirectResponse(url="/admin/talks?msg=restored", status_code=status.HTTP_303_SEE_OTHER)



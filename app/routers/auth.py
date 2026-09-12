from typing import Optional
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Student
from app.config import ADMIN_PW

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/gate")
async def verify_gate(request: Request, gate_pw: str = Form(...)):
    """시스템 진입 보안 패스워드(ADMIN_PW) 검증"""
    if gate_pw == ADMIN_PW:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="yuljeon_gate_auth", value="authenticated", max_age=86400 * 7, httponly=True)
        return response
    return RedirectResponse(url="/gate?error=invalid_password", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    """관리자 콘솔 로그인 (ADMIN_PW)"""
    if password == ADMIN_PW:
        response = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="yuljeon_admin_auth", value="authenticated", max_age=86400, httponly=True)
        return response
    return RedirectResponse(url="/admin/login?error=invalid_password", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin/logout")
async def admin_logout():
    """관리자 로그아웃"""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("yuljeon_admin_auth", path="/")
    response.delete_cookie("yuljeon_admin_auth", path="/admin")
    return response


import urllib.parse

@router.post("/student/login")
async def student_login(
    student_code: Optional[str] = Form(None),
    student_id: Optional[int] = Form(None),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """학생 로그인 (학생 ID 또는 이름 지원, 동명이인 분기)"""
    student = None
    
    # 1. 학생 ID(PK)가 명시적으로 넘어온 경우 (동명이인 목록에서 선택한 경우)
    if student_id:
        student = db.query(Student).filter(Student.id == student_id).first()
    elif student_code and student_code.strip():
        val = student_code.strip()
        # 1-1. 고유번호(student_code)로 먼저 조회
        code_match = db.query(Student).filter(Student.student_code.ilike(val)).first()
        if code_match:
            student = code_match
        else:
            # 1-2. 이름(name)으로 조회
            name_matches = db.query(Student).filter(Student.name == val).all()
            if len(name_matches) == 1:
                student = name_matches[0]
            elif len(name_matches) > 1:
                # 동명이인이 2명 이상인 경우 -> 선택 화면으로 리다이렉트
                encoded_name = urllib.parse.quote(val)
                return RedirectResponse(
                    url=f"/student/login?error=multiple_candidates&name={encoded_name}",
                    status_code=status.HTTP_303_SEE_OTHER
                )

    if not student or student.password_hash != password:
        return RedirectResponse(url="/student/login?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)
    
    if not student.is_active:
        return RedirectResponse(url="/student/login?error=pending_approval", status_code=status.HTTP_303_SEE_OTHER)

    # 초기 비밀번호(0000)인 경우 최초 4자리 비밀번호 변경 화면으로 강제 이동
    if student.password_hash == "0000":
        response = RedirectResponse(url="/student/change_password?first_login=true", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="yuljeon_student_id", value=str(student.id), max_age=86400 * 3, httponly=True)
        return response

    response = RedirectResponse(url="/student/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="yuljeon_student_id", value=str(student.id), max_age=86400 * 3, httponly=True)
    return response


@router.get("/student/logout")
async def student_logout():
    """학생 로그아웃 (학생 포털 로그인 화면으로 복귀)"""
    response = RedirectResponse(url="/student/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("yuljeon_student_id")
    return response

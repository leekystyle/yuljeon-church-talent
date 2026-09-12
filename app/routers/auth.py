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
    response.delete_cookie("yuljeon_admin_auth")
    return response


@router.post("/student/login")
async def student_login(
    student_code: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """학생 로그인"""
    student = db.query(Student).filter(Student.student_code == student_code.strip()).first()
    if not student or student.password_hash != password:
        return RedirectResponse(url="/student/login?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)
    
    if not student.is_active:
        return RedirectResponse(url="/student/login?error=pending_approval", status_code=status.HTTP_303_SEE_OTHER)

    response = RedirectResponse(url="/student/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="yuljeon_student_id", value=str(student.id), max_age=86400 * 3, httponly=True)
    return response


@router.get("/student/logout")
async def student_logout():
    """학생 로그아웃"""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("yuljeon_student_id")
    return response

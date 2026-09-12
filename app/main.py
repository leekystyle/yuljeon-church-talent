import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import Student
from app.routers import auth, student, kiosk, admin
from seed_data import init_db_and_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 기동 시 DB 테이블 생성 및 더미 데이터(3건씩) 시딩 보장
    print("[서버 시작] 율전중앙교회 달란트 시스템 초기화 시작...")
    init_db_and_seed()
    yield
    print("[서버 종료] 시스템 종료")


app = FastAPI(
    title="율전중앙교회 교회학교 달란트 시스템",
    version="2.0.0",
    lifespan=lifespan
)

# 정적 파일 서빙 (static 디렉터리)
os.makedirs("static/uploads/profiles", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


# 관리자 콘솔 세션 격리 및 메뉴 이탈 시 자동 로그아웃 미들웨어
@app.middleware("http")
async def admin_session_isolation_middleware(request: Request, call_next):
    path = request.url.path
    response = await call_next(request)

    # 관리자 경로(/admin, /auth/admin), 정적 파일이 아닌 일반 화면(학생 포털, 키오스크 등)으로 벗어난 경우
    if not path.startswith(("/admin", "/auth/admin", "/static", "/health")):
        # 관리자 인증 쿠키가 남아 있다면 즉시 완전 파기 (학생/키오스크 세션과 철저히 격리)
        if "yuljeon_admin_auth" in request.cookies:
            response.delete_cookie("yuljeon_admin_auth", path="/")
            response.delete_cookie("yuljeon_admin_auth", path="/admin")

    return response


# 라우터 등록
app.include_router(auth.router)
app.include_router(student.router)
app.include_router(kiosk.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "system": "yuljeon-church-talent"}


@app.get("/gate")
async def gate_redirect():
    """기존 게이트 URL 접근 시 관리자 로그인으로 리다이렉트"""
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


@app.get("/")
async def root_redirect(request: Request, db: Session = Depends(get_db)):
    """사이트 첫 화면: 학생 메뉴 (로그인 시 학생 대시보드, 미로그인 시 학생 로그인)"""
    student_id = request.cookies.get("yuljeon_student_id")
    if student_id:
        try:
            student = db.query(Student).filter(Student.id == int(student_id), Student.is_active == True).first()
            if student:
                return RedirectResponse(url="/student/dashboard", status_code=status.HTTP_302_FOUND)
        except (ValueError, TypeError):
            pass
    return RedirectResponse(url="/student/login", status_code=status.HTTP_302_FOUND)


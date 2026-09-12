import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import engine, Base
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


# 보안 게이트 미들웨어 (접속 시 ADMIN_PW 보안 인증 확인)
@app.middleware("http")
async def gate_security_middleware(request: Request, call_next):
    path = request.url.path
    # 예외 경로: 정적 파일, 게이트 페이지, 게이트 인증 API
    if path.startswith("/static") or path in ["/gate", "/auth/gate", "/health"]:
        return await call_next(request)

    gate_cookie = request.cookies.get("yuljeon_gate_auth")
    if gate_cookie != "authenticated":
        return RedirectResponse(url="/gate", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return await call_next(request)


# 관리자 콘솔 세션 격리 및 메뉴 이탈 시 자동 로그아웃 미들웨어
@app.middleware("http")
async def admin_session_isolation_middleware(request: Request, call_next):
    path = request.url.path
    response = await call_next(request)

    # 관리자 경로(/admin, /auth/admin), 정적 파일, 게이트가 아닌 일반 화면(홈, 학생 포털, 키오스크 등)으로 벗어난 경우
    if not path.startswith(("/admin", "/auth/admin", "/static", "/gate", "/health")):
        # 관리자 인증 쿠키가 남아 있다면 즉시 완전 파기 (학생 세션과 철저히 격리)
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


@app.get("/gate", response_class=HTMLResponse)
async def gate_page(request: Request):
    """시스템 최초 진입 보안 게이트 화면 (ADMIN_PW)"""
    error = request.query_params.get("error")
    return templates.TemplateResponse("gate.html", {"request": request, "error": error})


@app.get("/", response_class=HTMLResponse)
async def home_portal(request: Request):
    """메인 통합 포털 허브 화면"""
    return templates.TemplateResponse("index.html", {"request": request})

import json
from typing import List, Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Student, Item, Order, OrderItem
from app.timezone import get_kst_now

router = APIRouter(prefix="/kiosk", tags=["kiosk"])
templates = Jinja2Templates(directory="templates")


class CheckoutItem(BaseModel):
    item_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    student_id: int
    password: str
    items: List[CheckoutItem]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def kiosk_main(request: Request, db: Session = Depends(get_db)):
    """매점 키오스크 메인 화면 (태블릿/iPad 및 PC 최적화)"""
    items = db.query(Item).filter(Item.is_active == True).all()
    student_id = request.cookies.get("yuljeon_kiosk_student_id")
    student = None
    if student_id:
        try:
            student = db.query(Student).filter(Student.id == int(student_id), Student.is_active == True).first()
        except (ValueError, TypeError):
            student = None

    return templates.TemplateResponse("kiosk/shop.html", {
        "request": request,
        "items": items,
        "student": student
    })


@router.post("/login")
async def kiosk_login(
    student_code: Optional[str] = Form(None),
    student_id: Optional[int] = Form(None),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """키오스크 학생 간편 로그인 (이름/학생ID 및 동명이인 지원)"""
    student = None
    if student_id:
        student = db.query(Student).filter(Student.id == student_id).first()
    elif student_code and student_code.strip():
        val = student_code.strip()
        code_match = db.query(Student).filter(Student.student_code.ilike(val)).first()
        if code_match:
            student = code_match
        else:
            name_matches = db.query(Student).filter(Student.name == val).all()
            if len(name_matches) == 1:
                student = name_matches[0]
            elif len(name_matches) > 1:
                candidates = [
                    {
                        "id": s.id,
                        "name": s.name,
                        "student_code": s.student_code,
                        "department": s.department or "미지정",
                        "age": s.age,
                        "photo_url": s.photo_url or "/static/uploads/profiles/default_avatar.svg"
                    }
                    for s in name_matches
                ]
                return JSONResponse(content={
                    "success": False, 
                    "multiple": True, 
                    "candidates": candidates,
                    "message": "동명이인 학생이 여러 명 있습니다. 아래에서 본인을 선택해 주세요."
                })

    if not student or student.password_hash != password.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "이름(또는 ID)과 비밀번호가 일치하지 않습니다."})
    
    if not student.is_active:
        return JSONResponse(status_code=403, content={"success": False, "message": "가입 승인 대기 중인 학생입니다. 선생님께 문의해 주세요."})

    response = JSONResponse(content={
        "success": True,
        "student": {
            "id": student.id,
            "student_code": student.student_code,
            "name": student.name,
            "photo_url": student.photo_url or "/static/uploads/profiles/default_avatar.svg",
            "current_talent": student.current_talent,
            "department": student.department or ""
        }
    })
    response.set_cookie(key="yuljeon_kiosk_student_id", value=str(student.id), max_age=1800)
    return response


@router.get("/logout")
async def kiosk_logout():
    """키오스크 학생 로그아웃"""
    response = RedirectResponse(url="/kiosk", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("yuljeon_kiosk_student_id")
    return response


@router.post("/checkout")
async def kiosk_checkout(req: CheckoutRequest, db: Session = Depends(get_db)):
    """키오스크 장바구니 결제 처리 (2차 비밀번호 검증 + 잔액 부족 검증 + DB 원자적 트랜잭션)"""
    student = db.query(Student).filter(Student.id == req.student_id).first()
    if not student:
        return JSONResponse(status_code=404, content={"success": False, "message": "학생 정보를 찾을 수 없습니다."})

    # 2차 비밀번호 검증
    if student.password_hash != req.password.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "비밀번호가 일치하지 않습니다. 다시 입력해 주세요."})

    if not req.items:
        return JSONResponse(status_code=400, content={"success": False, "message": "구매할 물품을 장바구니에 담아주세요."})

    # 총 필요 달란트 및 재고 유효성 계산
    total_needed = 0
    item_details = []
    for order_item_req in req.items:
        if order_item_req.quantity <= 0:
            continue
        item = db.query(Item).filter(Item.id == order_item_req.item_id, Item.is_active == True).first()
        if not item:
            return JSONResponse(status_code=400, content={"success": False, "message": "판매 중이 아닌 물품이 포함되어 있습니다."})
        if item.stock < order_item_req.quantity:
            return JSONResponse(status_code=400, content={
                "success": False,
                "message": f"'{item.name}'의 재고가 부족합니다. (현재 재고: {item.stock}개, 요청: {order_item_req.quantity}개)"
            })
        subtotal = item.price * order_item_req.quantity
        total_needed += subtotal
        item_details.append({
            "item": item,
            "quantity": order_item_req.quantity,
            "unit_price": item.price,
            "subtotal": subtotal
        })

    # 잔액 부족 검증 (요구사항 11)
    if total_needed > student.current_talent:
        return JSONResponse(status_code=400, content={
            "success": False,
            "message": f"달란트가 부족합니다! (보유: {student.current_talent}달란트, 필요: {total_needed}달란트)"
        })

    # 원자적 트랜잭션 실행
    now = get_kst_now()
    order_num = f"ORD-{now.strftime('%Y%m%d%H%M%S')}-{student.id:04d}"

    # 1. 학생 달란트 차감
    student.current_talent -= total_needed
    student.total_spent += total_needed

    # 2. 주문 레코드 생성
    order = Order(
        order_number=order_num,
        student_id=student.id,
        total_points=total_needed,
        status="COMPLETED",
        created_at=now,
        updated_at=now
    )
    db.add(order)
    db.flush()

    # 3. 재고 차감 및 주문 세부 품목 생성
    for det in item_details:
        det["item"].stock -= det["quantity"]
        order_item = OrderItem(
            order_id=order.id,
            item_id=det["item"].id,
            item_name=det["item"].name,
            unit_price=det["unit_price"],
            quantity=det["quantity"],
            subtotal_points=det["subtotal"]
        )
        db.add(order_item)

    db.commit()

    return JSONResponse(content={
        "success": True,
        "message": "구매가 성공적으로 완료되었습니다!",
        "order_number": order_num,
        "total_spent": total_needed,
        "remaining_talent": student.current_talent
    })

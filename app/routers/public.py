from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    District,
    EmployeeCard,
    Inquiry,
    Notification,
    Property,
    PropertyCategory,
    PropertyStatus,
    Review,
    Role,
    User,
)
from app.security import ROLE_REALTOR, get_current_user_optional
from app.templating import build_context, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def about_page(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    employees = (
        db.query(EmployeeCard)
        .options(joinedload(EmployeeCard.user), joinedload(EmployeeCard.position))
        .order_by(EmployeeCard.experience_years.desc())
        .all()
    )
    approved_reviews = (
        db.query(Review)
        .options(joinedload(Review.author), joinedload(Review.target))
        .filter(Review.is_approved.is_(True))
        .order_by(Review.created_date.desc())
        .limit(6)
        .all()
    )
    available_properties = (
        db.query(Property)
        .options(joinedload(Property.district), joinedload(Property.category))
        .order_by(Property.id_property.desc())
        .limit(3)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="about",
            employees=employees,
            reviews=approved_reviews,
            featured_properties=available_properties,
        ),
    )


@router.get("/catalog", response_class=HTMLResponse)
def public_catalog_page(
    request: Request,
    district_id: Optional[str] = None,
    category_id: Optional[str] = None,
    max_price: Optional[str] = None,
    rooms: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    query = db.query(Property).options(
        joinedload(Property.district),
        joinedload(Property.category),
        joinedload(Property.building_type),
        joinedload(Property.repair_type),
        joinedload(Property.status),
    )

    d_id = int(district_id) if district_id and district_id.isdigit() else None
    c_id = int(category_id) if category_id and category_id.isdigit() else None
    m_price = float(max_price) if max_price and max_price.replace(".", "", 1).isdigit() else None
    r_cnt = int(rooms) if rooms and rooms.isdigit() else None

    if d_id:
        query = query.filter(Property.id_district == d_id)
    if c_id:
        query = query.filter(Property.id_property_type == c_id)
    if m_price:
        query = query.filter(Property.price <= m_price)
    if r_cnt:
        query = query.filter(Property.rooms_count == r_cnt)

    items = query.order_by(Property.id_property.desc()).all()
    districts = db.query(District).order_by(District.name.asc()).all()
    categories = db.query(PropertyCategory).order_by(PropertyCategory.name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="catalog",
            properties=items,
            districts=districts,
            categories=categories,
            filters={
                "district_id": d_id,
                "category_id": c_id,
                "max_price": max_price or "",
                "rooms": r_cnt,
            },
        ),
    )


@router.post("/inquiries/submit")
def submit_public_inquiry(
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    inquiry_type: str = Form("Консультация и запись"),
    property_id: str = Form(""),
    message: str = Form(""),
    redirect_to: str = Form("/"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    clean_name = full_name.strip()
    clean_phone = phone.strip()
    if not clean_name or not clean_phone:
        err = quote("Пожалуйста, укажите имя и контактный телефон.")
        return RedirectResponse(url=f"{redirect_to}?error={err}", status_code=303)

    prop_id_int = int(property_id) if property_id.strip().isdigit() else None
    if prop_id_int == 0:
        prop_id_int = None

    # Назначаем первого активного риэлтора по умолчанию и отправляем ему оповещение
    realtor = (
        db.query(User)
        .join(Role)
        .filter(Role.name == ROLE_REALTOR, User.is_active.is_(True))
        .first()
    )

    inquiry = Inquiry(
        id_user=user.id_user if user else None,
        id_property=prop_id_int,
        full_name=clean_name,
        phone=clean_phone,
        email=email.strip() or None,
        inquiry_type=inquiry_type.strip() or "Консультация",
        message=message.strip() or None,
        status="Новое",
        assigned_realtor_id=realtor.id_user if realtor else None,
    )
    db.add(inquiry)

    if realtor:
        db.add(
            Notification(
                id_user=realtor.id_user,
                message_text=f"Новое обращение от {clean_name} ({clean_phone}): {inquiry.inquiry_type}",
            )
        )

    db.commit()

    safe_redirect = redirect_to if redirect_to.startswith("/") else "/"
    msg = quote("Ваше обращение принято! Риэлтор свяжется с вами в ближайшее время.")
    return RedirectResponse(url=f"{safe_redirect}?message={msg}", status_code=303)

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Client,
    ClientTier,
    District,
    Inquiry,
    LeadSource,
    Notification,
    PassportData,
    Property,
    PropertyShowing,
    Role,
    ShowingStatus,
    User,
)
from app.security import (
    ROLE_CLIENT,
    STAFF_ROLES,
    get_current_user,
    hash_password,
    require_roles,
)
from app.templating import build_context, templates

router = APIRouter()


# ---------------------------------------------------------------------------
# Обращения (Заявки)
# ---------------------------------------------------------------------------


@router.get("/inquiries", response_class=HTMLResponse)
def inquiries_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role_name = user.role.name if user.role else ROLE_CLIENT
    query = db.query(Inquiry).options(
        joinedload(Inquiry.property_obj),
        joinedload(Inquiry.assigned_realtor),
        joinedload(Inquiry.user),
    )
    if role_name not in STAFF_ROLES:
        query = query.filter(Inquiry.id_user == user.id_user)

    items = query.order_by(Inquiry.created_at.desc()).all()
    properties = db.query(Property).order_by(Property.address.asc()).all()
    realtors = (
        db.query(User)
        .join(Role)
        .filter(Role.name.in_(STAFF_ROLES), User.is_active.is_(True))
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="inquiries.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="inquiries",
            inquiries=items,
            properties=properties,
            realtors=realtors,
        ),
    )


@router.post("/inquiries/{inquiry_id}/status")
def update_inquiry_status(
    inquiry_id: int,
    status: str = Form(...),
    assigned_realtor_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    inquiry = db.query(Inquiry).filter(Inquiry.id_inquiry == inquiry_id).first()
    if not inquiry:
        err = quote("Обращение не найдено.")
        return RedirectResponse(url=f"/inquiries?error={err}", status_code=303)

    inquiry.status = status.strip()
    if assigned_realtor_id.strip().isdigit():
        inquiry.assigned_realtor_id = int(assigned_realtor_id)
    db.commit()
    msg = quote("Статус обращения обновлен.")
    return RedirectResponse(url=f"/inquiries?message={msg}", status_code=303)


# ---------------------------------------------------------------------------
# База клиентов (Use Case №10 из курсового)
# ---------------------------------------------------------------------------


@router.get("/clients", response_class=HTMLResponse)
def clients_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    clients = (
        db.query(Client)
        .join(User)
        .options(
            joinedload(Client.user).joinedload(User.passport),
            joinedload(Client.lead_source),
            joinedload(Client.client_tier),
            joinedload(Client.preferred_district),
        )
        .order_by(User.full_name.asc())
        .all()
    )
    lead_sources = db.query(LeadSource).order_by(LeadSource.name.asc()).all()
    client_tiers = db.query(ClientTier).order_by(ClientTier.name.asc()).all()
    districts = db.query(District).order_by(District.name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="clients",
            clients=clients,
            lead_sources=lead_sources,
            client_tiers=client_tiers,
            districts=districts,
        ),
    )


@router.post("/clients/create")
def create_client(
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    login: str = Form(...),
    inn: str = Form(""),
    lead_source_id: str = Form(""),
    client_tier_id: str = Form(""),
    preferred_district_id: str = Form(""),
    preferred_budget_max: str = Form(""),
    notes: str = Form(""),
    passport_series: str = Form(""),
    passport_number: str = Form(""),
    issue_date: str = Form(""),
    department_code: str = Form(""),
    issued_by: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    clean_login = login.strip()
    clean_phone = phone.strip()
    clean_email = email.strip()

    duplicate = (
        db.query(User)
        .filter(
            (User.login == clean_login)
            | (User.phone == clean_phone)
            | (User.email == clean_email)
        )
        .first()
    )
    if duplicate:
        err = quote("Дублирование данных: клиент с таким логином, телефоном или email уже существует.")
        return RedirectResponse(url=f"/clients?error={err}", status_code=303)

    client_role = db.query(Role).filter(Role.name == ROLE_CLIENT).first()
    new_user = User(
        id_role=client_role.id_role,
        login=clean_login,
        password_hash=hash_password("client123"),
        full_name=full_name.strip(),
        phone=clean_phone,
        email=clean_email,
        inn=inn.strip() or None,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    if passport_series.strip() and passport_number.strip() and issued_by.strip():
        try:
            parsed_date = datetime.strptime(issue_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_date = datetime.today().date()
        db.add(
            PassportData(
                id_user=new_user.id_user,
                passport_series=passport_series.strip()[:4],
                passport_number=passport_number.strip()[:6],
                issue_date=parsed_date,
                department_code=department_code.strip()[:7] or "000-000",
                issued_by=issued_by.strip()[:255],
            )
        )

    budget_val = None
    if preferred_budget_max.strip():
        try:
            budget_val = Decimal(preferred_budget_max.strip().replace(" ", ""))
        except Exception:
            budget_val = None

    db.add(
        Client(
            id_user=new_user.id_user,
            id_lead_source=int(lead_source_id) if lead_source_id.isdigit() else None,
            id_client_tier=int(client_tier_id) if client_tier_id.isdigit() else None,
            id_preferred_district=(
                int(preferred_district_id) if preferred_district_id.isdigit() else None
            ),
            preferred_budget_max=budget_val,
            notes=notes.strip() or None,
        )
    )
    db.commit()

    msg = quote(f"Клиент «{new_user.full_name}» зарегистрирован (пароль по умолчанию: client123).")
    return RedirectResponse(url=f"/clients?message={msg}", status_code=303)


# ---------------------------------------------------------------------------
# График показов и календарь (Use Case №5 и №11 из курсового)
# ---------------------------------------------------------------------------


@router.get("/showings", response_class=HTMLResponse)
def showings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role_name = user.role.name if user.role else ROLE_CLIENT
    query = db.query(PropertyShowing).options(
        joinedload(PropertyShowing.property_obj),
        joinedload(PropertyShowing.client).joinedload(Client.user),
        joinedload(PropertyShowing.realtor),
        joinedload(PropertyShowing.showing_status),
    )
    if role_name not in STAFF_ROLES:
        if user.client_profile:
            query = query.filter(PropertyShowing.id_client == user.client_profile.id_client)
        else:
            query = query.filter(PropertyShowing.id_showing == -1)

    showings = query.order_by(PropertyShowing.showing_datetime.desc()).all()
    properties = db.query(Property).order_by(Property.address.asc()).all()
    clients = (
        db.query(Client)
        .join(User)
        .options(joinedload(Client.user))
        .order_by(User.full_name.asc())
        .all()
    )
    realtors = (
        db.query(User)
        .join(Role)
        .filter(Role.name.in_(STAFF_ROLES), User.is_active.is_(True))
        .order_by(User.full_name.asc())
        .all()
    )
    showing_statuses = db.query(ShowingStatus).order_by(ShowingStatus.id_showing_status.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="showings.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="showings",
            showings=showings,
            properties=properties,
            clients=clients,
            realtors=realtors,
            showing_statuses=showing_statuses,
        ),
    )


@router.post("/showings/create")
def create_showing(
    property_id: int = Form(...),
    client_id: int = Form(...),
    realtor_id: int = Form(...),
    showing_datetime: str = Form(...),
    result_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    try:
        dt = datetime.strptime(showing_datetime, "%Y-%m-%dT%H:%M")
    except ValueError:
        err = quote("Некорректный формат даты и времени показа.")
        return RedirectResponse(url=f"/showings?error={err}", status_code=303)

    # Проверка накладки в расписании (+/- 45 минут для риэлтора, кроме отмененных)
    canceled = db.query(ShowingStatus).filter(ShowingStatus.name == "Отменен").first()
    window_start = dt - timedelta(minutes=45)
    window_end = dt + timedelta(minutes=45)

    conflict_q = db.query(PropertyShowing).filter(
        PropertyShowing.id_realtor == realtor_id,
        PropertyShowing.showing_datetime >= window_start,
        PropertyShowing.showing_datetime <= window_end,
    )
    if canceled:
        conflict_q = conflict_q.filter(
            PropertyShowing.id_showing_status != canceled.id_showing_status
        )
    if conflict_q.first():
        err = quote(
            "Накладка в расписании: у выбранного сотрудника уже запланирован показ в это время (±45 мин)."
        )
        return RedirectResponse(url=f"/showings?error={err}", status_code=303)

    planned_status = db.query(ShowingStatus).filter(ShowingStatus.name == "Запланирован").first()
    if not planned_status:
        planned_status = db.query(ShowingStatus).first()

    showing = PropertyShowing(
        id_property=property_id,
        id_client=client_id,
        id_realtor=realtor_id,
        id_showing_status=planned_status.id_showing_status,
        showing_datetime=dt,
        result_comment=result_comment.strip() or None,
    )
    db.add(showing)

    # Отправляем персональное оповещение клиенту (Use Case №6 и №11)
    client_obj = db.query(Client).options(joinedload(Client.user)).filter(
        Client.id_client == client_id
    ).first()
    prop_obj = db.query(Property).filter(Property.id_property == property_id).first()
    if client_obj and client_obj.user and prop_obj:
        db.add(
            Notification(
                id_user=client_obj.user.id_user,
                message_text=(
                    f"Запланирован показ объекта ({prop_obj.address}) на "
                    f"{dt.strftime('%d.%m.%Y в %H:%M')}."
                ),
            )
        )

    db.commit()
    msg = quote("Показ запланирован, клиенту отправлено персональное уведомление.")
    return RedirectResponse(url=f"/showings?message={msg}", status_code=303)


@router.post("/showings/{showing_id}/status")
def update_showing_status(
    showing_id: int,
    showing_status_id: int = Form(...),
    result_comment: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    showing = db.query(PropertyShowing).filter(PropertyShowing.id_showing == showing_id).first()
    if not showing:
        err = quote("Запись показа не найдена.")
        return RedirectResponse(url=f"/showings?error={err}", status_code=303)

    showing.id_showing_status = showing_status_id
    if result_comment.strip():
        showing.result_comment = result_comment.strip()
    db.commit()
    msg = quote("Статус показа обновлен.")
    return RedirectResponse(url=f"/showings?message={msg}", status_code=303)

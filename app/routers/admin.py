from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AppSettings, Client, Role, User
from app.security import ROLE_ADMIN, ROLE_CLIENT, hash_password, require_roles
from app.templating import build_context, templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles([ROLE_ADMIN])),
):
    users = (
        db.query(User)
        .options(joinedload(User.role))
        .order_by(User.id_user.asc())
        .all()
    )
    roles = db.query(Role).order_by(Role.id_role.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="admin",
            users=users,
            roles=roles,
        ),
    )


@router.post("/admin/users/create")
def admin_create_user(
    login: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    inn: str = Form(""),
    role_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles([ROLE_ADMIN])),
):
    clean_login = login.strip()
    clean_phone = phone.strip()
    clean_email = email.strip()

    if len(password) < 4:
        err = quote("Пароль должен содержать не менее 4 символов.")
        return RedirectResponse(url=f"/admin?error={err}", status_code=303)

    exists = (
        db.query(User)
        .filter(
            (User.login == clean_login)
            | (User.phone == clean_phone)
            | (User.email == clean_email)
        )
        .first()
    )
    if exists:
        err = quote("Пользователь с таким логином, телефоном или email уже существует.")
        return RedirectResponse(url=f"/admin?error={err}", status_code=303)

    role = db.query(Role).filter(Role.id_role == role_id).first()
    new_user = User(
        id_role=role_id,
        login=clean_login,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        phone=clean_phone,
        email=clean_email,
        inn=inn.strip() or None,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    if role and role.name == ROLE_CLIENT:
        db.add(Client(id_user=new_user.id_user))

    db.commit()
    msg = quote(f"Пользователь «{new_user.full_name}» создан.")
    return RedirectResponse(url=f"/admin?message={msg}", status_code=303)


@router.post("/admin/users/{target_user_id}/update")
def admin_update_user(
    target_user_id: int,
    role_id: int = Form(...),
    is_active: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles([ROLE_ADMIN])),
):
    target = db.query(User).filter(User.id_user == target_user_id).first()
    if not target:
        err = quote("Пользователь не найден.")
        return RedirectResponse(url=f"/admin?error={err}", status_code=303)

    active_bool = is_active == "1"
    if target.id_user == user.id_user and not active_bool:
        err = quote("Нельзя заблокировать собственную учетную запись администратора.")
        return RedirectResponse(url=f"/admin?error={err}", status_code=303)

    target.id_role = role_id
    target.is_active = active_bool

    role = db.query(Role).filter(Role.id_role == role_id).first()
    if role and role.name == ROLE_CLIENT and not target.client_profile:
        db.add(Client(id_user=target.id_user))

    db.commit()
    msg = quote(f"Права и статус пользователя «{target.full_name}» обновлены.")
    return RedirectResponse(url=f"/admin?message={msg}", status_code=303)


@router.post("/admin/settings")
def admin_update_settings(
    agency_name: str = Form(...),
    hero_title: str = Form(...),
    hero_subtitle: str = Form(...),
    about_text: str = Form(...),
    stat_years: str = Form(...),
    stat_deals: str = Form(...),
    stat_clients: str = Form(...),
    stat_satisfaction: str = Form(...),
    agency_inn: str = Form(...),
    agency_phone: str = Form(...),
    agency_email: str = Form(...),
    agency_address: str = Form(...),
    reviews_require_moderation: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles([ROLE_ADMIN])),
):
    app_settings = db.query(AppSettings).first()
    if not app_settings:
        app_settings = AppSettings()
        db.add(app_settings)

    app_settings.agency_name = agency_name.strip()
    app_settings.hero_title = hero_title.strip()
    app_settings.hero_subtitle = hero_subtitle.strip()
    app_settings.about_text = about_text.strip()
    app_settings.stat_years = stat_years.strip()
    app_settings.stat_deals = stat_deals.strip()
    app_settings.stat_clients = stat_clients.strip()
    app_settings.stat_satisfaction = stat_satisfaction.strip()
    app_settings.agency_inn = agency_inn.strip()
    app_settings.agency_phone = agency_phone.strip()
    app_settings.agency_email = agency_email.strip()
    app_settings.agency_address = agency_address.strip()
    app_settings.reviews_require_moderation = reviews_require_moderation == "1"

    db.commit()
    msg = quote("Настройки приложения и данные страницы «О себе» сохранены.")
    return RedirectResponse(url=f"/admin?message={msg}", status_code=303)

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Client, Role, User
from app.security import (
    COOKIE_NAME,
    ROLE_CLIENT,
    create_access_token,
    get_current_user_optional,
    hash_password,
    verify_password,
)
from app.templating import build_context, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/properties", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth_login.html",
        context=build_context(request, db, None, active_nav="login"),
    )


@router.post("/login")
def login_submit(
    login: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    clean_login = login.strip()
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.login == clean_login)
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        err = quote("Неверный логин или пароль.")
        return RedirectResponse(url=f"/login?error={err}", status_code=303)
    if not user.is_active:
        err = quote("Учетная запись заблокирована администратором.")
        return RedirectResponse(url=f"/login?error={err}", status_code=303)

    token = create_access_token(user)
    target = "/admin" if user.role and user.role.name == "Администратор" else "/properties"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/properties", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth_register.html",
        context=build_context(request, db, None, active_nav="register"),
    )


@router.post("/register")
def register_submit(
    login: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    inn: str = Form(""),
    db: Session = Depends(get_db),
):
    clean_login = login.strip()
    clean_phone = phone.strip()
    clean_email = email.strip()

    if len(password) < 6:
        err = quote("Пароль должен содержать минимум 6 символов.")
        return RedirectResponse(url=f"/register?error={err}", status_code=303)

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
        return RedirectResponse(url=f"/register?error={err}", status_code=303)

    client_role = db.query(Role).filter(Role.name == ROLE_CLIENT).first()
    if not client_role:
        client_role = Role(name=ROLE_CLIENT)
        db.add(client_role)
        db.flush()

    new_user = User(
        id_role=client_role.id_role,
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

    db.add(Client(id_user=new_user.id_user))
    db.commit()

    db.refresh(new_user)
    new_user.role = client_role
    token = create_access_token(new_user)
    msg = quote("Регистрация прошла успешно! Добро пожаловать в личный кабинет.")
    response = RedirectResponse(url=f"/profile?message={msg}", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.post("/logout")
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response

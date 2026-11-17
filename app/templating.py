from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models import AppSettings, User
from app.security import (
    ROLE_ADMIN,
    ROLE_ASSISTANT,
    ROLE_CLIENT,
    ROLE_REALTOR,
    get_unread_notifications_count,
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def build_context(
    request: Request,
    db: Session,
    user: Optional[User],
    active_nav: str = "",
    **extra,
) -> dict:
    agency = db.query(AppSettings).first()
    role_name = user.role.name if (user and user.role) else "Гость"
    is_staff = role_name in (ROLE_ASSISTANT, ROLE_REALTOR, ROLE_ADMIN)
    is_senior = role_name in (ROLE_REALTOR, ROLE_ADMIN)
    is_admin = role_name == ROLE_ADMIN
    is_client = role_name == ROLE_CLIENT

    ctx = {
        "request": request,
        "agency": agency,
        "current_user": user,
        "role_name": role_name,
        "is_staff": is_staff,
        "is_senior": is_senior,
        "is_admin": is_admin,
        "is_client": is_client,
        "active_nav": active_nav,
        "unread_count": get_unread_notifications_count(db, user),
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
    }
    ctx.update(extra)
    return ctx

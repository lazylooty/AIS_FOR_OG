from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Client,
    ClientRole,
    Deal,
    DealParticipant,
    DealStatus,
    DealType,
    EscrowStatus,
    Notification,
    Property,
    Role,
    User,
)
from app.security import ROLE_CLIENT, SENIOR_ROLES, STAFF_ROLES, get_current_user, require_roles
from app.templating import build_context, templates

router = APIRouter()


@router.get("/deals", response_class=HTMLResponse)
def deals_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role_name = user.role.name if user.role else ROLE_CLIENT

    query = db.query(Deal).options(
        joinedload(Deal.property_obj),
        joinedload(Deal.realtor),
        joinedload(Deal.deal_type),
        joinedload(Deal.deal_status),
        joinedload(Deal.escrow_status),
        joinedload(Deal.participants).joinedload(DealParticipant.client).joinedload(Client.user),
        joinedload(Deal.participants).joinedload(DealParticipant.client_role),
        joinedload(Deal.contracts),
    )

    if role_name not in STAFF_ROLES:
        if user.client_profile:
            query = query.join(DealParticipant).filter(
                DealParticipant.id_client == user.client_profile.id_client
            )
        else:
            query = query.filter(Deal.id_deal == -1)

    deals = query.order_by(Deal.id_deal.desc()).all()
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
    deal_types = db.query(DealType).order_by(DealType.id_deal_type.asc()).all()
    deal_statuses = db.query(DealStatus).order_by(DealStatus.id_deal_status.asc()).all()
    escrow_statuses = db.query(EscrowStatus).order_by(EscrowStatus.id_escrow_status.asc()).all()
    client_roles = db.query(ClientRole).order_by(ClientRole.id_client_role.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="deals.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="deals",
            deals=deals,
            properties=properties,
            clients=clients,
            realtors=realtors,
            deal_types=deal_types,
            deal_statuses=deal_statuses,
            escrow_statuses=escrow_statuses,
            client_roles=client_roles,
        ),
    )


@router.post("/deals/create")
def create_deal(
    property_id: int = Form(...),
    realtor_id: int = Form(...),
    deal_type_id: int = Form(...),
    deal_status_id: int = Form(...),
    escrow_status_id: int = Form(...),
    final_price: float = Form(...),
    commission_rate: float = Form(2.5),
    client_1_id: int = Form(...),
    client_1_role_id: int = Form(...),
    client_2_id: str = Form("0"),
    client_2_role_id: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    if final_price <= 0:
        err = quote("Сумма сделки должна быть положительной.")
        return RedirectResponse(url=f"/deals?error={err}", status_code=303)

    deal = Deal(
        id_property=property_id,
        responsible_realtor_id=realtor_id,
        id_deal_type=deal_type_id,
        id_deal_status=deal_status_id,
        id_escrow_status=escrow_status_id,
        final_price=Decimal(str(round(final_price, 2))),
        commission_rate=Decimal(str(min(max(commission_rate, 0.0), 100.0))),
        start_date=date.today(),
    )
    db.add(deal)
    db.flush()

    db.add(
        DealParticipant(
            id_deal=deal.id_deal,
            id_client=client_1_id,
            id_client_role=client_1_role_id,
        )
    )
    if client_2_id.isdigit() and int(client_2_id) > 0 and client_2_role_id.isdigit():
        c2 = int(client_2_id)
        r2 = int(client_2_role_id)
        if c2 != client_1_id:
            db.add(
                DealParticipant(
                    id_deal=deal.id_deal,
                    id_client=c2,
                    id_client_role=r2,
                )
            )

    # Оповещаем первого клиента
    c1_obj = db.query(Client).options(joinedload(Client.user)).filter(
        Client.id_client == client_1_id
    ).first()
    if c1_obj and c1_obj.user:
        db.add(
            Notification(
                id_user=c1_obj.user.id_user,
                message_text=f"Открыта новая сделка №{deal.id_deal} на сумму {final_price:,.0f} ₽.".replace(",", " "),
            )
        )

    db.commit()
    msg = quote(f"Сделка №{deal.id_deal} успешно создана.")
    return RedirectResponse(url=f"/deals?message={msg}", status_code=303)


@router.post("/deals/{deal_id}/update")
def update_deal_status(
    deal_id: int,
    deal_status_id: int = Form(...),
    escrow_status_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    deal = (
        db.query(Deal)
        .options(joinedload(Deal.participants).joinedload(DealParticipant.client))
        .filter(Deal.id_deal == deal_id)
        .first()
    )
    if not deal:
        err = quote("Сделка не найдена.")
        return RedirectResponse(url=f"/deals?error={err}", status_code=303)

    deal.id_deal_status = deal_status_id
    deal.id_escrow_status = escrow_status_id

    done_status = db.query(DealStatus).filter(DealStatus.id_deal_status == deal_status_id).first()
    if done_status and done_status.name == "Завершена":
        deal.end_date = date.today()

    for part in deal.participants:
        if part.client:
            db.add(
                Notification(
                    id_user=part.client.id_user,
                    message_text=f"Обновлен статус вашей сделки №{deal.id_deal}: {done_status.name if done_status else ''}.",
                )
            )

    db.commit()
    msg = quote(f"Статус сделки №{deal_id} обновлен.")
    return RedirectResponse(url=f"/deals?message={msg}", status_code=303)


@router.post("/deals/{deal_id}/delete")
def delete_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(SENIOR_ROLES)),
):
    deal = db.query(Deal).filter(Deal.id_deal == deal_id).first()
    if not deal:
        err = quote("Сделка не найдена.")
        return RedirectResponse(url=f"/deals?error={err}", status_code=303)

    db.delete(deal)
    db.commit()
    msg = quote(f"Сделка №{deal_id} удалена.")
    return RedirectResponse(url=f"/deals?message={msg}", status_code=303)

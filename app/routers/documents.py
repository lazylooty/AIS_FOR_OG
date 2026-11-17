from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import (
    AppSettings,
    Client,
    Contract,
    ContractTemplate,
    Deal,
    DealParticipant,
    Notification,
    Property,
    User,
)
from app.security import (
    ROLE_CLIENT,
    SENIOR_ROLES,
    STAFF_ROLES,
    get_current_user,
    require_roles,
)
from app.services.docx_service import (
    create_sample_template_docx,
    extract_tags_from_docx,
    render_contract_docx,
)
from app.templating import build_context, templates

router = APIRouter()


def _parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _attachment_headers(download_name: str, fallback_ascii: str = "document.docx") -> dict:
    encoded = quote(download_name)
    return {
        "Content-Disposition": f'attachment; filename="{fallback_ascii}"; filename*=UTF-8\'\'{encoded}'
    }


@router.get("/contracts", response_class=HTMLResponse)
def contracts_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    role_name = user.role.name if user.role else ROLE_CLIENT
    is_staff = role_name in STAFF_ROLES

    contract_templates = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.is_active.is_(True))
        .order_by(ContractTemplate.created_date.desc())
        .all()
    )
    for tpl in contract_templates:
        tpl.tags_list = _parse_tags(tpl.detected_tags)

    clients = (
        db.query(Client)
        .join(User)
        .options(joinedload(Client.user).joinedload(User.passport))
        .order_by(User.full_name.asc())
        .all()
    )
    properties = (
        db.query(Property)
        .options(joinedload(Property.district), joinedload(Property.category))
        .order_by(Property.id_property.desc())
        .all()
    )
    deals = (
        db.query(Deal)
        .options(
            joinedload(Deal.property_obj),
            joinedload(Deal.deal_type),
            joinedload(Deal.participants).joinedload(DealParticipant.client).joinedload(Client.user),
        )
        .order_by(Deal.id_deal.desc())
        .all()
    )

    contracts_query = db.query(Contract).options(
        joinedload(Contract.template),
        joinedload(Contract.property_obj),
        joinedload(Contract.deal),
    )
    if not is_staff:
        if user.client_profile:
            deal_ids = [
                dp.id_deal
                for dp in db.query(DealParticipant)
                .filter(DealParticipant.id_client == user.client_profile.id_client)
                .all()
            ]
            contracts_query = contracts_query.filter(
                (Contract.id_deal.in_(deal_ids))
                | (Contract.client_names.ilike(f"%{user.full_name}%"))
            )
        else:
            contracts_query = contracts_query.filter(Contract.id_contract == -1)

    contracts = contracts_query.order_by(Contract.generation_date.desc()).limit(30).all()

    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context=build_context(
            request,
            db,
            user,
            active_nav="contracts",
            contract_templates=contract_templates,
            clients=clients,
            properties=properties,
            deals=deals,
            contracts=contracts,
        ),
    )


@router.post("/templates/upload")
async def upload_template(
    template_name: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    original_name = (file.filename or "").strip()
    if not original_name.lower().endswith(".docx"):
        err = quote("Поддерживаются только файлы формата .docx (Word).")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    stored_filename = f"{uuid.uuid4().hex}.docx"
    dest_path = settings.templates_dir / stored_filename

    content = await file.read()
    if not content:
        err = quote("Загруженный файл пуст.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    dest_path.write_bytes(content)

    try:
        tags = extract_tags_from_docx(dest_path)
    except Exception:
        dest_path.unlink(missing_ok=True)
        err = quote("Не удалось прочитать .docx файл. Проверьте, что файл не поврежден.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    clean_name = template_name.strip() or Path(original_name).stem
    tpl = ContractTemplate(
        template_name=clean_name,
        file_path=stored_filename,
        detected_tags=json.dumps(tags, ensure_ascii=False),
        is_active=True,
    )
    db.add(tpl)
    db.commit()

    msg = quote(f"Шаблон «{clean_name}» загружен. Найдено тегов: {len(tags)}.")
    return RedirectResponse(url=f"/contracts?message={msg}", status_code=303)


@router.post("/templates/{template_id}/delete")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(SENIOR_ROLES)),
):
    tpl = db.query(ContractTemplate).filter(ContractTemplate.id_template == template_id).first()
    if not tpl:
        err = quote("Шаблон не найден.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    tpl.is_active = False
    db.commit()
    msg = quote(f"Шаблон «{tpl.template_name}» удален из списка активных.")
    return RedirectResponse(url=f"/contracts?message={msg}", status_code=303)


@router.get("/templates/sample")
def download_sample_template(user: User = Depends(get_current_user)):
    sample_path = settings.templates_dir / "_sample_download.docx"
    create_sample_template_docx(sample_path)
    return FileResponse(
        path=str(sample_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers("Шаблон_договора_пример.docx", "sample_template.docx"),
    )


@router.post("/contracts/generate")
def generate_contract(
    template_id: int = Form(...),
    deal_id: str = Form("0"),
    client_ids: List[int] = Form([]),
    property_id: str = Form("0"),
    contract_number: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    tpl = (
        db.query(ContractTemplate)
        .filter(
            ContractTemplate.id_template == template_id,
            ContractTemplate.is_active.is_(True),
        )
        .first()
    )
    if not tpl:
        err = quote("Выбранный шаблон не найден.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    template_path = settings.templates_dir / tpl.file_path
    if not template_path.exists():
        err = quote("Файл шаблона отсутствует на сервере.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    deal_obj: Optional[Deal] = None
    selected_clients: List[Client] = []
    prop: Optional[Property] = None

    if deal_id.isdigit() and int(deal_id) > 0:
        deal_obj = (
            db.query(Deal)
            .options(
                joinedload(Deal.property_obj).joinedload(Property.district),
                joinedload(Deal.property_obj).joinedload(Property.category),
                joinedload(Deal.property_obj).joinedload(Property.building_type),
                joinedload(Deal.property_obj).joinedload(Property.repair_type),
                joinedload(Deal.property_obj).joinedload(Property.status),
                joinedload(Deal.deal_type),
                joinedload(Deal.deal_status),
                joinedload(Deal.escrow_status),
                joinedload(Deal.realtor),
                joinedload(Deal.participants)
                .joinedload(DealParticipant.client)
                .joinedload(Client.user)
                .joinedload(User.passport),
            )
            .filter(Deal.id_deal == int(deal_id))
            .first()
        )
        if deal_obj:
            prop = deal_obj.property_obj
            selected_clients = [p.client for p in deal_obj.participants if p.client]

    if not selected_clients:
        ordered_client_ids = [cid for cid in client_ids if cid > 0]
        if not ordered_client_ids:
            err = quote("Выберите сделку или хотя бы одного клиента.")
            return RedirectResponse(url=f"/contracts?error={err}", status_code=303)
        clients_map = {
            c.id_client: c
            for c in db.query(Client)
            .options(joinedload(Client.user).joinedload(User.passport))
            .filter(Client.id_client.in_(ordered_client_ids))
            .all()
        }
        selected_clients = [clients_map[cid] for cid in ordered_client_ids if cid in clients_map]

    if prop is None and property_id.isdigit() and int(property_id) > 0:
        prop = (
            db.query(Property)
            .options(
                joinedload(Property.district),
                joinedload(Property.category),
                joinedload(Property.building_type),
                joinedload(Property.repair_type),
                joinedload(Property.status),
            )
            .filter(Property.id_property == int(property_id))
            .first()
        )

    if not selected_clients or prop is None:
        err = quote("Необходимо выбрать клиентов и объект недвижимости (или готовую сделку).")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    agency = db.query(AppSettings).first()
    clean_number = contract_number.strip() or f"ДГ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    output_filename = f"{uuid.uuid4().hex}.docx"
    output_path = settings.contracts_dir / output_filename

    render_contract_docx(
        template_path=template_path,
        output_path=output_path,
        clients=selected_clients,
        prop=prop,
        agency=agency,
        contract_number=clean_number,
        deal=deal_obj,
    )

    client_names_str = ", ".join(c.user.full_name for c in selected_clients)
    contract_record = Contract(
        id_deal=deal_obj.id_deal if deal_obj else None,
        id_template=tpl.id_template,
        id_property=prop.id_property,
        client_names=client_names_str[:500],
        contract_number=clean_number[:128],
        file_path=output_filename,
        is_signed=False,
    )
    db.add(contract_record)

    for cl in selected_clients:
        if cl.user:
            db.add(
                Notification(
                    id_user=cl.user.id_user,
                    message_text=f"Сформирован договор №{clean_number} ({tpl.template_name}).",
                )
            )

    db.commit()

    download_name = f"{tpl.template_name}_{clean_number}.docx".replace("/", "-")
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers(download_name, f"contract_{contract_record.id_contract}.docx"),
    )


@router.post("/contracts/{contract_id}/sign")
def toggle_contract_signed(
    contract_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(STAFF_ROLES)),
):
    contract = db.query(Contract).filter(Contract.id_contract == contract_id).first()
    if not contract:
        err = quote("Договор не найден.")
        return RedirectResponse(url=f"/contracts?error={err}", status_code=303)

    contract.is_signed = not contract.is_signed
    db.commit()
    msg = quote("Статус подписания договора обновлен.")
    return RedirectResponse(url=f"/contracts?message={msg}", status_code=303)


@router.get("/contracts/{contract_id}/download")
def download_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contract = (
        db.query(Contract)
        .options(joinedload(Contract.template))
        .filter(Contract.id_contract == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Договор не найден")

    role_name = user.role.name if user.role else ROLE_CLIENT
    if role_name not in STAFF_ROLES:
        allowed = user.full_name in contract.client_names
        if not allowed and contract.id_deal and user.client_profile:
            allowed = (
                db.query(DealParticipant)
                .filter(
                    DealParticipant.id_deal == contract.id_deal,
                    DealParticipant.id_client == user.client_profile.id_client,
                )
                .first()
                is not None
            )
        if not allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к этому документу")

    file_path = settings.contracts_dir / contract.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл договора отсутствует на диске")

    tpl_name = contract.template.template_name if contract.template else "Договор"
    download_name = f"{tpl_name}_{contract.contract_number}.docx".replace("/", "-")
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers(download_name, f"contract_{contract.id_contract}.docx"),
    )

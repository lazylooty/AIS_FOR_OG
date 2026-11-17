from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import AppSettings, Client, Contract, ContractTemplate, Property, User
from app.services.docx_service import (
    create_sample_template_docx,
    extract_tags_from_docx,
    render_contract_docx,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


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


@router.get("/", response_class=HTMLResponse)
def documents_page(
    request: Request,
    message: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
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
    contracts = (
        db.query(Contract)
        .options(joinedload(Contract.template), joinedload(Contract.property_obj))
        .order_by(Contract.generation_date.desc())
        .limit(20)
        .all()
    )
    agency = db.query(AppSettings).first()

    return templates.TemplateResponse(
        request=request,
        name="documents.html",
        context={
            "agency": agency,
            "contract_templates": contract_templates,
            "clients": clients,
            "properties": properties,
            "contracts": contracts,
            "message": message,
            "error": error,
        },
    )


@router.post("/templates/upload")
async def upload_template(
    template_name: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    original_name = (file.filename or "").strip()
    if not original_name.lower().endswith(".docx"):
        err = quote("Поддерживаются только файлы формата .docx (Word).")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    stored_filename = f"{uuid.uuid4().hex}.docx"
    dest_path = settings.templates_dir / stored_filename

    content = await file.read()
    if not content:
        err = quote("Загруженный файл пуст.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    dest_path.write_bytes(content)

    try:
        tags = extract_tags_from_docx(dest_path)
    except Exception:
        dest_path.unlink(missing_ok=True)
        err = quote("Не удалось прочитать .docx файл. Проверьте, что файл не поврежден.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

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
    return RedirectResponse(url=f"/?message={msg}", status_code=303)


@router.post("/templates/{template_id}/delete")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    tpl = db.query(ContractTemplate).filter(ContractTemplate.id_template == template_id).first()
    if not tpl:
        err = quote("Шаблон не найден.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    tpl.is_active = False
    db.commit()
    msg = quote(f"Шаблон «{tpl.template_name}» удален из списка активных.")
    return RedirectResponse(url=f"/?message={msg}", status_code=303)


@router.get("/templates/sample")
def download_sample_template():
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
    client_ids: List[int] = Form(...),
    property_id: int = Form(...),
    contract_number: str = Form(""),
    db: Session = Depends(get_db),
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
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    template_path = settings.templates_dir / tpl.file_path
    if not template_path.exists():
        err = quote("Файл шаблона отсутствует на сервере.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    ordered_client_ids = [cid for cid in client_ids if cid > 0]
    if not ordered_client_ids:
        err = quote("Выберите хотя бы одного клиента.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    clients_map = {
        c.id_client: c
        for c in db.query(Client)
        .options(joinedload(Client.user).joinedload(User.passport))
        .filter(Client.id_client.in_(ordered_client_ids))
        .all()
    }
    selected_clients = [clients_map[cid] for cid in ordered_client_ids if cid in clients_map]
    if not selected_clients:
        err = quote("Выбранные клиенты не найдены в базе данных.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    prop = (
        db.query(Property)
        .options(
            joinedload(Property.district),
            joinedload(Property.category),
            joinedload(Property.building_type),
            joinedload(Property.repair_type),
            joinedload(Property.status),
        )
        .filter(Property.id_property == property_id)
        .first()
    )
    if not prop:
        err = quote("Выбранный объект недвижимости не найден.")
        return RedirectResponse(url=f"/?error={err}", status_code=303)

    agency = db.query(AppSettings).first()

    clean_number = contract_number.strip()
    if not clean_number:
        clean_number = f"ДГ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    output_filename = f"{uuid.uuid4().hex}.docx"
    output_path = settings.contracts_dir / output_filename

    render_contract_docx(
        template_path=template_path,
        output_path=output_path,
        clients=selected_clients,
        prop=prop,
        agency=agency,
        contract_number=clean_number,
    )

    client_names_str = ", ".join(c.user.full_name for c in selected_clients)
    contract_record = Contract(
        id_template=tpl.id_template,
        id_property=prop.id_property,
        client_names=client_names_str[:500],
        contract_number=clean_number[:128],
        file_path=output_filename,
        is_signed=False,
    )
    db.add(contract_record)
    db.commit()

    download_name = f"{tpl.template_name}_{clean_number}.docx".replace("/", "-")
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_attachment_headers(download_name, f"contract_{contract_record.id_contract}.docx"),
    )


@router.get("/contracts/{contract_id}/download")
def download_contract(contract_id: int, db: Session = Depends(get_db)):
    contract = (
        db.query(Contract)
        .options(joinedload(Contract.template))
        .filter(Contract.id_contract == contract_id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Договор не найден")

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

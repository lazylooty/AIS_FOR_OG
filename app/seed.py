from datetime import date
from decimal import Decimal
import json

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AppSettings,
    BuildingType,
    Client,
    ContractTemplate,
    District,
    PassportData,
    Property,
    PropertyCategory,
    PropertyStatus,
    RepairType,
    Role,
    User,
)
from app.services.docx_service import create_sample_template_docx, extract_tags_from_docx


def _get_or_create(db: Session, model, **kwargs):
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    instance = model(**kwargs)
    db.add(instance)
    db.flush()
    return instance


def seed_initial_data(db: Session) -> None:
    """Populate initial roles, dictionaries, agency settings, demo clients/properties, and a sample template."""
    # 1. Roles from coursework
    role_names = ["Гость", "Клиент", "Помощник риэлтора", "Риэлтор", "Администратор"]
    roles = {name: _get_or_create(db, Role, name=name) for name in role_names}

    # 2. Agency settings
    if db.query(AppSettings).count() == 0:
        db.add(
            AppSettings(
                agency_name=settings.agency_name,
                agency_inn="667109876543",
                agency_phone="+7 (922) 123-45-67",
                agency_email="golubina.realty@example.ru",
                agency_address="г. Екатеринбург, ул. Малышева, д. 51",
            )
        )

    # 3. Dictionaries
    districts = {
        name: _get_or_create(db, District, name=name)
        for name in ["Центр", "ВИЗ", "Ботаника", "Академический", "Уралмаш"]
    }
    categories = {
        name: _get_or_create(db, PropertyCategory, name=name)
        for name in ["Квартира", "Дом", "Апартаменты", "Коммерция"]
    }
    building_types = {
        name: _get_or_create(db, BuildingType, name=name)
        for name in ["Кирпичный", "Монолитный", "Панельный"]
    }
    repair_types = {
        name: _get_or_create(db, RepairType, name=name)
        for name in ["Дизайнерский", "Евроремонт", "Косметический", "Черновая отделка"]
    }
    statuses = {
        name: _get_or_create(db, PropertyStatus, name=name)
        for name in ["Доступен", "Забронирован", "Продан"]
    }

    # 4. Demo clients (only if no clients exist yet)
    if db.query(Client).count() == 0:
        demo_clients = [
            {
                "login": "client_ivanov",
                "full_name": "Иванов Сергей Петрович",
                "phone": "+7 (912) 111-22-33",
                "email": "ivanov.sp@example.ru",
                "inn": "665812345678",
                "passport": {
                    "passport_series": "6518",
                    "passport_number": "456789",
                    "issue_date": date(2018, 5, 14),
                    "department_code": "660-001",
                    "issued_by": "ГУ МВД России по Свердловской области",
                },
                "budget": Decimal("9500000.00"),
                "district": districts["Центр"].id_district,
                "notes": "Покупатель. Ищет 2-комнатную квартиру.",
            },
            {
                "login": "client_petrova",
                "full_name": "Петрова Анна Владимировна",
                "phone": "+7 (922) 444-55-66",
                "email": "petrova.av@example.ru",
                "inn": "667098765432",
                "passport": {
                    "passport_series": "6520",
                    "passport_number": "912345",
                    "issue_date": date(2020, 9, 21),
                    "department_code": "660-014",
                    "issued_by": "Отделением УФМС по Ленинскому району г. Екатеринбурга",
                },
                "budget": Decimal("12000000.00"),
                "district": districts["ВИЗ"].id_district,
                "notes": "Собственник / продавец объекта.",
            },
            {
                "login": "client_sidorov",
                "full_name": "Сидоров Алексей Дмитриевич",
                "phone": "+7 (904) 777-88-99",
                "email": "sidorov.ad@example.ru",
                "inn": "667155544433",
                "passport": {
                    "passport_series": "6515",
                    "passport_number": "102938",
                    "issue_date": date(2015, 3, 10),
                    "department_code": "660-007",
                    "issued_by": "ОУФМС России по Свердловской области в Чкаловском районе",
                },
                "budget": Decimal("6200000.00"),
                "district": districts["Ботаника"].id_district,
                "notes": "Арендатор коммерческого помещения.",
            },
        ]

        for item in demo_clients:
            user = User(
                id_role=roles["Клиент"].id_role,
                login=item["login"],
                password_hash="demo_placeholder_hash",
                full_name=item["full_name"],
                phone=item["phone"],
                email=item["email"],
                inn=item["inn"],
                is_active=True,
            )
            db.add(user)
            db.flush()

            p = item["passport"]
            db.add(
                PassportData(
                    id_user=user.id_user,
                    passport_series=p["passport_series"],
                    passport_number=p["passport_number"],
                    issue_date=p["issue_date"],
                    department_code=p["department_code"],
                    issued_by=p["issued_by"],
                )
            )
            db.add(
                Client(
                    id_user=user.id_user,
                    preferred_budget_max=item["budget"],
                    id_preferred_district=item["district"],
                    notes=item["notes"],
                )
            )

    # 5. Demo properties (only if none exist yet)
    if db.query(Property).count() == 0:
        db.add_all(
            [
                Property(
                    cadastral_number="66:41:0401005:1024",
                    address="г. Екатеринбург, ул. Радищева, д. 33, кв. 48",
                    id_district=districts["Центр"].id_district,
                    total_area=Decimal("64.50"),
                    rooms_count=2,
                    floor=7,
                    id_building_type=building_types["Монолитный"].id_building_type,
                    id_repair_type=repair_types["Евроремонт"].id_repair_type,
                    id_property_type=categories["Квартира"].id_property_type,
                    id_status=statuses["Доступен"].id_status,
                    price=Decimal("8950000.00"),
                    location_rating=Decimal("9.4"),
                    description="Светлая двухкомнатная квартира в центре города.",
                ),
                Property(
                    cadastral_number="66:41:0302011:518",
                    address="г. Екатеринбург, ул. Татищева, д. 77, кв. 112",
                    id_district=districts["ВИЗ"].id_district,
                    total_area=Decimal("82.00"),
                    rooms_count=3,
                    floor=12,
                    id_building_type=building_types["Кирпичный"].id_building_type,
                    id_repair_type=repair_types["Дизайнерский"].id_repair_type,
                    id_property_type=categories["Квартира"].id_property_type,
                    id_status=statuses["Доступен"].id_status,
                    price=Decimal("11400000.00"),
                    location_rating=Decimal("8.9"),
                    description="Просторная трехкомнатная квартира рядом с набережной.",
                ),
                Property(
                    cadastral_number="66:41:0504002:89",
                    address="г. Екатеринбург, ул. Белинского, д. 163, пом. 4",
                    id_district=districts["Ботаника"].id_district,
                    total_area=Decimal("115.00"),
                    rooms_count=4,
                    floor=1,
                    id_building_type=building_types["Монолитный"].id_building_type,
                    id_repair_type=repair_types["Косметический"].id_repair_type,
                    id_property_type=categories["Коммерция"].id_property_type,
                    id_status=statuses["Доступен"].id_status,
                    price=Decimal("14800000.00"),
                    location_rating=Decimal("9.1"),
                    description="Помещение свободного назначения с отдельным входом.",
                ),
            ]
        )

    # 6. Starter sample .docx template
    if db.query(ContractTemplate).count() == 0:
        sample_filename = "sample_contract_template.docx"
        sample_path = settings.templates_dir / sample_filename
        create_sample_template_docx(sample_path)
        tags = extract_tags_from_docx(sample_path)
        db.add(
            ContractTemplate(
                template_name="Договор оказания риэлторских услуг (пример)",
                file_path=sample_filename,
                detected_tags=json.dumps(tags, ensure_ascii=False),
                is_active=True,
            )
        )

    db.commit()

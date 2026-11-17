from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(Base):
    __tablename__ = "role"

    id_role: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id_user: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_role: Mapped[int] = mapped_column(ForeignKey("role.id_role"), nullable=False)
    login: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    passport: Mapped[Optional["PassportData"]] = relationship(
        "PassportData", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    client_profile: Mapped[Optional["Client"]] = relationship(
        "Client", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class PassportData(Base):
    __tablename__ = "passport_data"

    id_passport: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_user: Mapped[int] = mapped_column(
        ForeignKey("users.id_user", ondelete="CASCADE"), unique=True, nullable=False
    )
    passport_series: Mapped[str] = mapped_column(String(4), nullable=False)
    passport_number: Mapped[str] = mapped_column(String(6), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_code: Mapped[str] = mapped_column(String(7), nullable=False)
    issued_by: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="passport")


class District(Base):
    __tablename__ = "district"

    id_district: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class PropertyCategory(Base):
    __tablename__ = "property_category"

    id_property_type: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class BuildingType(Base):
    __tablename__ = "building_type"

    id_building_type: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class RepairType(Base):
    __tablename__ = "repair_type"

    id_repair_type: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class PropertyStatus(Base):
    __tablename__ = "property_status"

    id_status: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Property(Base):
    __tablename__ = "property"

    id_property: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cadastral_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    id_district: Mapped[int] = mapped_column(ForeignKey("district.id_district"), nullable=False)
    total_area: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    rooms_count: Mapped[int] = mapped_column(Integer, nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    id_building_type: Mapped[int] = mapped_column(
        ForeignKey("building_type.id_building_type"), nullable=False
    )
    id_repair_type: Mapped[int] = mapped_column(
        ForeignKey("repair_type.id_repair_type"), nullable=False
    )
    id_property_type: Mapped[int] = mapped_column(
        ForeignKey("property_category.id_property_type"), nullable=False
    )
    id_status: Mapped[int] = mapped_column(
        ForeignKey("property_status.id_status"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    location_rating: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("8.0"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    district: Mapped["District"] = relationship("District")
    building_type: Mapped["BuildingType"] = relationship("BuildingType")
    repair_type: Mapped["RepairType"] = relationship("RepairType")
    category: Mapped["PropertyCategory"] = relationship("PropertyCategory")
    status: Mapped["PropertyStatus"] = relationship("PropertyStatus")


class Client(Base):
    __tablename__ = "client"

    id_client: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_user: Mapped[int] = mapped_column(
        ForeignKey("users.id_user", ondelete="CASCADE"), unique=True, nullable=False
    )
    preferred_budget_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    id_preferred_district: Mapped[Optional[int]] = mapped_column(
        ForeignKey("district.id_district"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="client_profile")
    preferred_district: Mapped[Optional["District"]] = relationship("District")


class ContractTemplate(Base):
    __tablename__ = "contract_template"

    id_template: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    contracts: Mapped[List["Contract"]] = relationship("Contract", back_populates="template")


class Contract(Base):
    __tablename__ = "contract"

    id_contract: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_template: Mapped[int] = mapped_column(
        ForeignKey("contract_template.id_template"), nullable=False
    )
    id_property: Mapped[Optional[int]] = mapped_column(
        ForeignKey("property.id_property"), nullable=True
    )
    client_names: Mapped[str] = mapped_column(String(500), nullable=False)
    contract_number: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    generation_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    is_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    template: Mapped["ContractTemplate"] = relationship(
        "ContractTemplate", back_populates="contracts"
    )
    property_obj: Mapped[Optional["Property"]] = relationship("Property")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_name: Mapped[str] = mapped_column(
        String(255), default="ИП Голубина Ольга Геннадьевна", nullable=False
    )
    agency_inn: Mapped[str] = mapped_column(String(20), default="667100000000", nullable=False)
    agency_phone: Mapped[str] = mapped_column(
        String(30), default="+7 (900) 000-00-00", nullable=False
    )
    agency_email: Mapped[str] = mapped_column(
        String(120), default="info@golubina-realty.ru", nullable=False
    )
    agency_address: Mapped[str] = mapped_column(
        String(255), default="г. Екатеринбург", nullable=False
    )

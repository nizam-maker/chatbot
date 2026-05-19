# tenants/laman_auto/schema.py
# ─────────────────────────────────────────────────────────────
#  SQLAlchemy models for Laman Auto structured database
#  SQLite locally → PostgreSQL on Railway (change DATABASE_URL)
# ─────────────────────────────────────────────────────────────

import os
from sqlalchemy import (
    create_engine, Column, String, Float,
    Integer, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///laman_auto.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── Cars ─────────────────────────────────────────────────────
class Car(Base):
    __tablename__ = "cars"

    car_id       = Column(String(80), primary_key=True)
    # e.g. "PERODUA-AXIA-AV-2023"

    # Classification
    brand        = Column(String(40), nullable=False)   # Perodua, Proton, Honda, Toyota
    model        = Column(String(60), nullable=False)   # Axia, Myvi, Saga, City...
    variant      = Column(String(80), nullable=False)   # AV, SE, X, G, 1.5V...
    year         = Column(Integer,    nullable=False)
    body_type    = Column(String(30))                   # Hatchback, Sedan, SUV, MPV
    segment      = Column(String(5))                    # A, B, C, D

    # Pricing (MYR)
    price_otr    = Column(Float,   nullable=False)      # On-the-road price
    price_basic  = Column(Float)                        # Basic price before duties
    sst_exempt   = Column(Boolean, default=False)       # SST exemption status

    # Engine
    engine_cc    = Column(Integer)                      # e.g. 998, 1332, 1497
    transmission = Column(String(10))                   # CVT, MT, AT, DCT, D-CVT
    fuel_type    = Column(String(15), default="Petrol") # Petrol, Hybrid, EV
    power_hp     = Column(Integer)
    torque_nm    = Column(Integer)
    fuel_cons    = Column(Float)                        # km/l e.g. 27.4

    # Inventory
    stock        = Column(Integer, default=0)
    colour       = Column(String(40))
    condition    = Column(String(10), default="new")    # new, used, demo
    status       = Column(String(15), default="available")
    # available, reserved, sold

    # Metadata
    spec_pdf_url = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow)

    # Relationships
    rebates      = relationship("Rebate",   back_populates="car")


# ── Rebates ──────────────────────────────────────────────────
class Rebate(Base):
    __tablename__ = "rebates"

    rebate_id    = Column(String(60), primary_key=True)
    car_id       = Column(String(80), ForeignKey("cars.car_id"), nullable=False)
    amount       = Column(Float,  nullable=False)       # MYR e.g. 3000.0
    rebate_type  = Column(String(30))
    # bank, trade-in, govt, loyalty, staff
    description  = Column(Text)                         # e.g. "Maybank cash rebate"
    valid_from   = Column(DateTime)
    valid_until  = Column(DateTime)
    is_active    = Column(Boolean, default=True)

    car          = relationship("Car", back_populates="rebates")


# ── Customers ────────────────────────────────────────────────
class Customer(Base):
    __tablename__ = "customers"

    customer_id  = Column(String(60), primary_key=True)
    name         = Column(String(100))
    phone        = Column(String(20))
    email        = Column(String(100))
    state        = Column(String(30))                   # Selangor, Johor, KL...
    source       = Column(String(30))                   # whatsapp, walk-in, web
    created_at   = Column(DateTime, default=datetime.utcnow)


# ── Create all tables ────────────────────────────────────────
def init_db():
    Base.metadata.create_all(engine)
    print("[schema] Tables created ✓")


# ── Helper: get DB session ───────────────────────────────────
def get_session():
    return SessionLocal()


# ── Helper: query functions used by engine.py ────────────────
def get_car_by_model(model: str, variant: str = None) -> list:
    """Return cars matching model name, optionally filtered by variant."""
    with get_session() as s:
        q = s.query(Car).filter(
            Car.model.ilike(f"%{model}%"),
            Car.status == "available"
        )
        if variant:
            q = q.filter(Car.variant.ilike(f"%{variant}%"))
        return q.all()


def get_active_rebates(car_id: str) -> list:
    """Return all active rebates for a given car."""
    now = datetime.utcnow()
    with get_session() as s:
        return s.query(Rebate).filter(
            Rebate.car_id == car_id,
            Rebate.is_active == True,
            Rebate.valid_until >= now
        ).all()


def get_cars_by_brand(brand: str) -> list:
    """Return all available cars for a brand."""
    with get_session() as s:
        return s.query(Car).filter(
            Car.brand.ilike(f"%{brand}%"),
            Car.status == "available"
        ).order_by(Car.price_otr).all()


def search_cars(
    brand: str = None,
    max_price: float = None,
    body_type: str = None,
    segment: str = None
) -> list:
    """Flexible car search — used by chatbot for filtered queries."""
    with get_session() as s:
        q = s.query(Car).filter(Car.status == "available")
        if brand:
            q = q.filter(Car.brand.ilike(f"%{brand}%"))
        if max_price:
            q = q.filter(Car.price_otr <= max_price)
        if body_type:
            q = q.filter(Car.body_type.ilike(f"%{body_type}%"))
        if segment:
            q = q.filter(Car.segment == segment.upper())
        return q.order_by(Car.price_otr).all()


if __name__ == "__main__":
    init_db()
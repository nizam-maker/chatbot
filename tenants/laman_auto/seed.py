# tenants/laman_auto/seed.py
# ─────────────────────────────────────────────────────────────
#  Seed data — Perodua, Proton, Honda, Toyota
#  Run once: python -m tenants.laman_auto.seed
#  Prices are approximate OTR Peninsular Malaysia 2024
# ─────────────────────────────────────────────────────────────

from tenants.laman_auto.schema import (
    init_db, get_session, SessionLocal, Car, Rebate, Customer
)
from datetime import datetime, timedelta
import uuid


def seed_cars(s):
    cars = [

        # ── PERODUA ──────────────────────────────────────────
        Car(car_id="PERODUA-AXIA-G-2023",
            brand="Perodua", model="Axia", variant="G",
            year=2023, body_type="Hatchback", segment="A",
            price_otr=40_500, price_basic=34_800,
            sst_exempt=True,
            engine_cc=998, transmission="D-CVT",
            fuel_type="Petrol", power_hp=68, torque_nm=91,
            fuel_cons=25.3, stock=8, colour="Granite Grey",
            status="available"),

        Car(car_id="PERODUA-AXIA-X-2023",
            brand="Perodua", model="Axia", variant="X",
            year=2023, body_type="Hatchback", segment="A",
            price_otr=46_500, price_basic=40_200,
            sst_exempt=True,
            engine_cc=998, transmission="D-CVT",
            fuel_type="Petrol", power_hp=68, torque_nm=91,
            fuel_cons=27.4, stock=5, colour="Coral Blue",
            status="available"),

        Car(car_id="PERODUA-AXIA-AV-2023",
            brand="Perodua", model="Axia", variant="AV",
            year=2023, body_type="Hatchback", segment="A",
            price_otr=54_500, price_basic=47_100,
            sst_exempt=True,
            engine_cc=998, transmission="D-CVT",
            fuel_type="Petrol", power_hp=68, torque_nm=91,
            fuel_cons=27.4, stock=3, colour="Lava Red",
            status="available"),

        Car(car_id="PERODUA-MYVI-G-2024",
            brand="Perodua", model="Myvi", variant="1.3 G AT",
            year=2024, body_type="Hatchback", segment="B",
            price_otr=55_000, price_basic=48_000,
            sst_exempt=True,
            engine_cc=1329, transmission="AT",
            fuel_type="Petrol", power_hp=95, torque_nm=121,
            fuel_cons=19.8, stock=10, colour="Glittering Silver",
            status="available"),

        Car(car_id="PERODUA-MYVI-AV-2024",
            brand="Perodua", model="Myvi", variant="1.5 AV CVT",
            year=2024, body_type="Hatchback", segment="B",
            price_otr=70_000, price_basic=61_500,
            sst_exempt=True,
            engine_cc=1496, transmission="CVT",
            fuel_type="Petrol", power_hp=103, torque_nm=136,
            fuel_cons=18.9, stock=4, colour="Ivory White",
            status="available"),

        Car(car_id="PERODUA-BEZZA-G-2024",
            brand="Perodua", model="Bezza", variant="1.0 G MT",
            year=2024, body_type="Sedan", segment="A",
            price_otr=43_000, price_basic=37_000,
            sst_exempt=True,
            engine_cc=998, transmission="MT",
            fuel_type="Petrol", power_hp=68, torque_nm=91,
            fuel_cons=21.6, stock=6, colour="Granite Grey",
            status="available"),

        Car(car_id="PERODUA-BEZZA-AV-2024",
            brand="Perodua", model="Bezza", variant="1.3 AV CVT",
            year=2024, body_type="Sedan", segment="A",
            price_otr=57_000, price_basic=50_000,
            sst_exempt=True,
            engine_cc=1329, transmission="CVT",
            fuel_type="Petrol", power_hp=95, torque_nm=121,
            fuel_cons=21.6, stock=2, colour="Lava Red",
            status="available"),

        # ── PROTON ───────────────────────────────────────────
        Car(car_id="PROTON-SAGA-STANDARD-2024",
            brand="Proton", model="Saga", variant="Standard MT",
            year=2024, body_type="Sedan", segment="A",
            price_otr=40_300, price_basic=35_500,
            sst_exempt=True,
            engine_cc=1332, transmission="MT",
            fuel_type="Petrol", power_hp=95, torque_nm=120,
            fuel_cons=16.9, stock=12, colour="Snow White",
            status="available"),

        Car(car_id="PROTON-SAGA-PREMIUM-2024",
            brand="Proton", model="Saga", variant="Premium CVT",
            year=2024, body_type="Sedan", segment="A",
            price_otr=48_800, price_basic=42_500,
            sst_exempt=True,
            engine_cc=1332, transmission="CVT",
            fuel_type="Petrol", power_hp=95, torque_nm=120,
            fuel_cons=16.9, stock=7, colour="Armour Silver",
            status="available"),

        Car(car_id="PROTON-X50-STANDARD-2024",
            brand="Proton", model="X50", variant="Standard",
            year=2024, body_type="SUV", segment="B",
            price_otr=79_200, price_basic=70_000,
            sst_exempt=False,
            engine_cc=1499, transmission="DCT",
            fuel_type="Petrol", power_hp=148, torque_nm=226,
            fuel_cons=16.7, stock=5, colour="Jet Grey",
            status="available"),

        Car(car_id="PROTON-X50-FLAGSHIP-2024",
            brand="Proton", model="X50", variant="Flagship",
            year=2024, body_type="SUV", segment="B",
            price_otr=103_800, price_basic=91_000,
            sst_exempt=False,
            engine_cc=1499, transmission="DCT",
            fuel_type="Petrol", power_hp=148, torque_nm=226,
            fuel_cons=16.7, stock=2, colour="Flame Red",
            status="available"),

        Car(car_id="PROTON-X70-STANDARD-2024",
            brand="Proton", model="X70", variant="Standard 2WD",
            year=2024, body_type="SUV", segment="C",
            price_otr=112_800, price_basic=99_000,
            sst_exempt=False,
            engine_cc=1499, transmission="DCT",
            fuel_type="Petrol", power_hp=177, torque_nm=255,
            fuel_cons=14.7, stock=3, colour="Pearl White",
            status="available"),

        # ── HONDA ────────────────────────────────────────────
        Car(car_id="HONDA-CITY-S-2024",
            brand="Honda", model="City", variant="1.5 S",
            year=2024, body_type="Sedan", segment="B",
            price_otr=79_900, price_basic=71_000,
            sst_exempt=False,
            engine_cc=1497, transmission="CVT",
            fuel_type="Petrol", power_hp=119, torque_nm=145,
            fuel_cons=18.5, stock=6, colour="Lunar Silver",
            status="available"),

        Car(car_id="HONDA-CITY-V-2024",
            brand="Honda", model="City", variant="1.5 V",
            year=2024, body_type="Sedan", segment="B",
            price_otr=93_900, price_basic=83_000,
            sst_exempt=False,
            engine_cc=1497, transmission="CVT",
            fuel_type="Petrol", power_hp=119, torque_nm=145,
            fuel_cons=18.5, stock=4, colour="Meteoroid Grey",
            status="available"),

        Car(car_id="HONDA-HRV-S-2024",
            brand="Honda", model="HR-V", variant="1.5 S",
            year=2024, body_type="SUV", segment="B",
            price_otr=109_900, price_basic=97_000,
            sst_exempt=False,
            engine_cc=1498, transmission="CVT",
            fuel_type="Petrol", power_hp=129, torque_nm=153,
            fuel_cons=16.1, stock=3, colour="Platinum White",
            status="available"),

        Car(car_id="HONDA-HRV-E-HEV-2024",
            brand="Honda", model="HR-V", variant="e:HEV RS",
            year=2024, body_type="SUV", segment="B",
            price_otr=149_900, price_basic=133_000,
            sst_exempt=False,
            engine_cc=1498, transmission="e-CVT",
            fuel_type="Hybrid", power_hp=131, torque_nm=253,
            fuel_cons=27.0, stock=1, colour="Sonic Grey",
            status="available"),

        # ── TOYOTA ───────────────────────────────────────────
        Car(car_id="TOYOTA-VIOS-J-2024",
            brand="Toyota", model="Vios", variant="1.5 J",
            year=2024, body_type="Sedan", segment="B",
            price_otr=79_200, price_basic=70_500,
            sst_exempt=False,
            engine_cc=1496, transmission="CVT",
            fuel_type="Petrol", power_hp=107, torque_nm=140,
            fuel_cons=18.0, stock=7, colour="Silver Metallic",
            status="available"),

        Car(car_id="TOYOTA-VIOS-G-2024",
            brand="Toyota", model="Vios", variant="1.5 G",
            year=2024, body_type="Sedan", segment="B",
            price_otr=93_200, price_basic=83_000,
            sst_exempt=False,
            engine_cc=1496, transmission="CVT",
            fuel_type="Petrol", power_hp=107, torque_nm=140,
            fuel_cons=18.0, stock=5, colour="Attitude Black",
            status="available"),

        Car(car_id="TOYOTA-YARIS-J-2024",
            brand="Toyota", model="Yaris", variant="1.5 J",
            year=2024, body_type="Hatchback", segment="B",
            price_otr=83_800, price_basic=74_500,
            sst_exempt=False,
            engine_cc=1496, transmission="CVT",
            fuel_type="Petrol", power_hp=107, torque_nm=140,
            fuel_cons=18.8, stock=4, colour="Red Mica",
            status="available"),
    ]

    for car in cars:
        if not s.query(Car).filter_by(car_id=car.car_id).first():
            s.add(car)
    print(f"[seed] {len(cars)} cars seeded ✓")
    return cars


def seed_rebates(s):
    now   = datetime.utcnow()
    month_end = now.replace(day=28) + timedelta(days=4)

    rebates = [
        # Perodua rebates
        Rebate(rebate_id="RBT-AXIA-MAYBANK-2024",
               car_id="PERODUA-AXIA-AV-2023",
               amount=2000, rebate_type="bank",
               description="Maybank cash rebate for Axia AV",
               valid_from=now, valid_until=month_end,
               is_active=True),

        Rebate(rebate_id="RBT-MYVI-CIMB-2024",
               car_id="PERODUA-MYVI-AV-2024",
               amount=3000, rebate_type="bank",
               description="CIMB cash rebate for Myvi AV",
               valid_from=now, valid_until=month_end,
               is_active=True),

        Rebate(rebate_id="RBT-MYVI-TRADEIN-2024",
               car_id="PERODUA-MYVI-AV-2024",
               amount=1500, rebate_type="trade-in",
               description="Trade-in rebate for old car",
               valid_from=now, valid_until=month_end,
               is_active=True),

        # Proton rebates
        Rebate(rebate_id="RBT-SAGA-HLBANK-2024",
               car_id="PROTON-SAGA-PREMIUM-2024",
               amount=1500, rebate_type="bank",
               description="HLBank cash rebate for Saga Premium",
               valid_from=now, valid_until=month_end,
               is_active=True),

        Rebate(rebate_id="RBT-X50-BSN-2024",
               car_id="PROTON-X50-FLAGSHIP-2024",
               amount=4000, rebate_type="bank",
               description="BSN special rebate for X50 Flagship",
               valid_from=now, valid_until=month_end,
               is_active=True),

        # Honda rebates
        Rebate(rebate_id="RBT-CITY-RHB-2024",
               car_id="HONDA-CITY-V-2024",
               amount=2500, rebate_type="bank",
               description="RHB bank cash rebate for City V",
               valid_from=now, valid_until=month_end,
               is_active=True),
    ]

    for r in rebates:
        if not s.query(Rebate).filter_by(rebate_id=r.rebate_id).first():
            s.add(r)
    print(f"[seed] {len(rebates)} rebates seeded ✓")


def seed_customers(s):
    customers = [
        Customer(customer_id="CUST-ALI-001",
                 name="Ali bin Ahmad",
                 phone="0123456789",
                 email="ali@email.com",
                 state="Johor", source="whatsapp"),

        Customer(customer_id="CUST-SITI-002",
                 name="Siti Aminah",
                 phone="0198765432",
                 email="siti@email.com",
                 state="Selangor", source="web"),
    ]
    for c in customers:
        if not s.query(Customer).filter_by(customer_id=c.customer_id).first():
            s.add(c)
    print(f"[seed] {len(customers)} customers seeded ✓")


if __name__ == "__main__":
    init_db()
    with SessionLocal() as s:
        seed_cars(s)
        seed_rebates(s)
        seed_customers(s)
        s.commit()
    print("[seed] All done! ✓")
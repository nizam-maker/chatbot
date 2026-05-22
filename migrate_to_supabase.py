# migrate_to_supabase.py
# ─────────────────────────────────────────────────────────────
#  One-time migration — copies cars and rebates from
#  SQLite seed data into Supabase
#  Run once: python migrate_to_supabase.py
# ─────────────────────────────────────────────────────────────

from core.supabase_client import sb
from datetime import datetime, timedelta

TENANT_ID = "a0000000-0000-0000-0000-000000000001"  # Laman Auto


def migrate_cars():
    cars = [
        dict(car_id="PERODUA-AXIA-G-2023",    tenant_id=TENANT_ID, brand="Perodua", model="Axia",  variant="G",              year=2023, body_type="Hatchback", segment="A", price_otr=40500,  sst_exempt=True,  engine_cc=998,  transmission="D-CVT", fuel_type="Petrol", power_hp=68,  torque_nm=91,  fuel_cons=25.3, stock=8,  colour="Granite Grey",    status="available"),
        dict(car_id="PERODUA-AXIA-X-2023",    tenant_id=TENANT_ID, brand="Perodua", model="Axia",  variant="X",              year=2023, body_type="Hatchback", segment="A", price_otr=46500,  sst_exempt=True,  engine_cc=998,  transmission="D-CVT", fuel_type="Petrol", power_hp=68,  torque_nm=91,  fuel_cons=27.4, stock=5,  colour="Coral Blue",      status="available"),
        dict(car_id="PERODUA-AXIA-AV-2023",   tenant_id=TENANT_ID, brand="Perodua", model="Axia",  variant="AV",             year=2023, body_type="Hatchback", segment="A", price_otr=54500,  sst_exempt=True,  engine_cc=998,  transmission="D-CVT", fuel_type="Petrol", power_hp=68,  torque_nm=91,  fuel_cons=27.4, stock=3,  colour="Lava Red",        status="available"),
        dict(car_id="PERODUA-MYVI-G-2024",    tenant_id=TENANT_ID, brand="Perodua", model="Myvi",  variant="1.3 G AT",       year=2024, body_type="Hatchback", segment="B", price_otr=55000,  sst_exempt=True,  engine_cc=1329, transmission="AT",    fuel_type="Petrol", power_hp=95,  torque_nm=121, fuel_cons=19.8, stock=10, colour="Glittering Silver",status="available"),
        dict(car_id="PERODUA-MYVI-AV-2024",   tenant_id=TENANT_ID, brand="Perodua", model="Myvi",  variant="1.5 AV CVT",     year=2024, body_type="Hatchback", segment="B", price_otr=70000,  sst_exempt=True,  engine_cc=1496, transmission="CVT",   fuel_type="Petrol", power_hp=103, torque_nm=136, fuel_cons=18.9, stock=4,  colour="Ivory White",     status="available"),
        dict(car_id="PERODUA-BEZZA-G-2024",   tenant_id=TENANT_ID, brand="Perodua", model="Bezza", variant="1.0 G MT",       year=2024, body_type="Sedan",    segment="A", price_otr=43000,  sst_exempt=True,  engine_cc=998,  transmission="MT",    fuel_type="Petrol", power_hp=68,  torque_nm=91,  fuel_cons=21.6, stock=6,  colour="Granite Grey",    status="available"),
        dict(car_id="PERODUA-BEZZA-AV-2024",  tenant_id=TENANT_ID, brand="Perodua", model="Bezza", variant="1.3 AV CVT",     year=2024, body_type="Sedan",    segment="A", price_otr=57000,  sst_exempt=True,  engine_cc=1329, transmission="CVT",   fuel_type="Petrol", power_hp=95,  torque_nm=121, fuel_cons=21.6, stock=2,  colour="Lava Red",        status="available"),
        dict(car_id="PROTON-SAGA-STANDARD-2024", tenant_id=TENANT_ID, brand="Proton", model="Saga", variant="Standard MT",  year=2024, body_type="Sedan",    segment="A", price_otr=40300,  sst_exempt=True,  engine_cc=1332, transmission="MT",    fuel_type="Petrol", power_hp=95,  torque_nm=120, fuel_cons=16.9, stock=12, colour="Snow White",      status="available"),
        dict(car_id="PROTON-SAGA-PREMIUM-2024",  tenant_id=TENANT_ID, brand="Proton", model="Saga", variant="Premium CVT",  year=2024, body_type="Sedan",    segment="A", price_otr=48800,  sst_exempt=True,  engine_cc=1332, transmission="CVT",   fuel_type="Petrol", power_hp=95,  torque_nm=120, fuel_cons=16.9, stock=7,  colour="Armour Silver",   status="available"),
        dict(car_id="PROTON-X50-STANDARD-2024",  tenant_id=TENANT_ID, brand="Proton", model="X50",  variant="Standard",     year=2024, body_type="SUV",      segment="B", price_otr=79200,  sst_exempt=False, engine_cc=1499, transmission="DCT",   fuel_type="Petrol", power_hp=148, torque_nm=226, fuel_cons=16.7, stock=5,  colour="Jet Grey",        status="available"),
        dict(car_id="PROTON-X50-FLAGSHIP-2024",  tenant_id=TENANT_ID, brand="Proton", model="X50",  variant="Flagship",     year=2024, body_type="SUV",      segment="B", price_otr=103800, sst_exempt=False, engine_cc=1499, transmission="DCT",   fuel_type="Petrol", power_hp=148, torque_nm=226, fuel_cons=16.7, stock=2,  colour="Flame Red",       status="available"),
        dict(car_id="PROTON-X70-STANDARD-2024",  tenant_id=TENANT_ID, brand="Proton", model="X70",  variant="Standard 2WD", year=2024, body_type="SUV",      segment="C", price_otr=112800, sst_exempt=False, engine_cc=1499, transmission="DCT",   fuel_type="Petrol", power_hp=177, torque_nm=255, fuel_cons=14.7, stock=3,  colour="Pearl White",     status="available"),
        dict(car_id="HONDA-CITY-S-2024",      tenant_id=TENANT_ID, brand="Honda",   model="City",  variant="1.5 S",         year=2024, body_type="Sedan",    segment="B", price_otr=79900,  sst_exempt=False, engine_cc=1497, transmission="CVT",   fuel_type="Petrol", power_hp=119, torque_nm=145, fuel_cons=18.5, stock=6,  colour="Lunar Silver",    status="available"),
        dict(car_id="HONDA-CITY-V-2024",      tenant_id=TENANT_ID, brand="Honda",   model="City",  variant="1.5 V",         year=2024, body_type="Sedan",    segment="B", price_otr=93900,  sst_exempt=False, engine_cc=1497, transmission="CVT",   fuel_type="Petrol", power_hp=119, torque_nm=145, fuel_cons=18.5, stock=4,  colour="Meteoroid Grey",  status="available"),
        dict(car_id="HONDA-HRV-S-2024",       tenant_id=TENANT_ID, brand="Honda",   model="HR-V",  variant="1.5 S",         year=2024, body_type="SUV",      segment="B", price_otr=109900, sst_exempt=False, engine_cc=1498, transmission="CVT",   fuel_type="Petrol", power_hp=129, torque_nm=153, fuel_cons=16.1, stock=3,  colour="Platinum White",  status="available"),
        dict(car_id="HONDA-HRV-E-HEV-2024",   tenant_id=TENANT_ID, brand="Honda",   model="HR-V",  variant="e:HEV RS",      year=2024, body_type="SUV",      segment="B", price_otr=149900, sst_exempt=False, engine_cc=1498, transmission="e-CVT", fuel_type="Hybrid", power_hp=131, torque_nm=253, fuel_cons=27.0, stock=1,  colour="Sonic Grey",      status="available"),
        dict(car_id="TOYOTA-VIOS-J-2024",     tenant_id=TENANT_ID, brand="Toyota",  model="Vios",  variant="1.5 J",         year=2024, body_type="Sedan",    segment="B", price_otr=79200,  sst_exempt=False, engine_cc=1496, transmission="CVT",   fuel_type="Petrol", power_hp=107, torque_nm=140, fuel_cons=18.0, stock=7,  colour="Silver Metallic", status="available"),
        dict(car_id="TOYOTA-VIOS-G-2024",     tenant_id=TENANT_ID, brand="Toyota",  model="Vios",  variant="1.5 G",         year=2024, body_type="Sedan",    segment="B", price_otr=93200,  sst_exempt=False, engine_cc=1496, transmission="CVT",   fuel_type="Petrol", power_hp=107, torque_nm=140, fuel_cons=18.0, stock=5,  colour="Attitude Black",  status="available"),
        dict(car_id="TOYOTA-YARIS-J-2024",    tenant_id=TENANT_ID, brand="Toyota",  model="Yaris", variant="1.5 J",         year=2024, body_type="Hatchback", segment="B", price_otr=83800, sst_exempt=False, engine_cc=1496, transmission="CVT",   fuel_type="Petrol", power_hp=107, torque_nm=140, fuel_cons=18.8, stock=4,  colour="Red Mica",        status="available"),
    ]

    res = sb.table("cars").upsert(cars).execute()
    print(f"[migrate] {len(cars)} cars migrated ✓")


def migrate_rebates():
    now      = datetime.utcnow().isoformat()
    month_end = (datetime.utcnow().replace(day=28) + timedelta(days=4)).isoformat()

    rebates = [
        dict(tenant_id=TENANT_ID, car_id="PERODUA-AXIA-AV-2023",    amount=2000, rebate_type="bank",     description="Maybank cash rebate for Axia AV",        valid_from=now, valid_until=month_end, is_active=True),
        dict(tenant_id=TENANT_ID, car_id="PERODUA-MYVI-AV-2024",    amount=3000, rebate_type="bank",     description="CIMB cash rebate for Myvi AV",            valid_from=now, valid_until=month_end, is_active=True),
        dict(tenant_id=TENANT_ID, car_id="PERODUA-MYVI-AV-2024",    amount=1500, rebate_type="trade-in", description="Trade-in rebate for old car",             valid_from=now, valid_until=month_end, is_active=True),
        dict(tenant_id=TENANT_ID, car_id="PROTON-SAGA-PREMIUM-2024", amount=1500, rebate_type="bank",    description="HLBank cash rebate for Saga Premium",     valid_from=now, valid_until=month_end, is_active=True),
        dict(tenant_id=TENANT_ID, car_id="PROTON-X50-FLAGSHIP-2024", amount=4000, rebate_type="bank",    description="BSN special rebate for X50 Flagship",     valid_from=now, valid_until=month_end, is_active=True),
        dict(tenant_id=TENANT_ID, car_id="HONDA-CITY-V-2024",        amount=2500, rebate_type="bank",    description="RHB bank cash rebate for City V",         valid_from=now, valid_until=month_end, is_active=True),
    ]

    res = sb.table("rebates").upsert(rebates).execute()
    print(f"[migrate] {len(rebates)} rebates migrated ✓")


def migrate_api_keys():
    from core.supabase_client import generate_api_key
    pub = generate_api_key(TENANT_ID, "public")
    sec = generate_api_key(TENANT_ID, "secret")
    print(f"[migrate] API keys generated ✓")
    print(f"  Public:  {pub}")
    print(f"  Secret:  {sec}")


if __name__ == "__main__":
    migrate_cars()
    migrate_rebates()
    migrate_api_keys()
    print("\n[migrate] All done — Supabase is fully seeded ✓")
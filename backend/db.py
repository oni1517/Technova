import logging

import asyncpg

from backend.models import HospitalRecord

logger = logging.getLogger(__name__)


def sample_hospitals() -> list[HospitalRecord]:
    return [
        HospitalRecord(
            id=1,
            name="Ruby Hall Clinic",
            lat=18.5362,
            lon=73.8826,
            departments=["emergency", "trauma", "cardiology", "icu"],
            available_beds=7,
            icu_available=True,
        ),
        HospitalRecord(
            id=2,
            name="Sahyadri Hospital Deccan Gymkhana",
            lat=18.5156,
            lon=73.8417,
            departments=["emergency", "trauma", "neurology", "icu"],
            available_beds=5,
            icu_available=True,
        ),
        HospitalRecord(
            id=3,
            name="Jehangir Hospital",
            lat=18.5308,
            lon=73.8747,
            departments=["emergency", "cardiology", "pulmonology", "icu"],
            available_beds=6,
            icu_available=True,
        ),
        HospitalRecord(
            id=4,
            name="Poona Hospital & Research Centre",
            lat=18.5016,
            lon=73.8385,
            departments=["emergency", "general_surgery", "orthopedics", "icu"],
            available_beds=8,
            icu_available=True,
        ),
        HospitalRecord(
            id=5,
            name="Sancheti Hospital",
            lat=18.5286,
            lon=73.8563,
            departments=["orthopedics", "trauma", "emergency"],
            available_beds=10,
            icu_available=False,
        ),
        HospitalRecord(
            id=6,
            name="Noble Hospital",
            lat=18.4960,
            lon=73.9130,
            departments=["emergency", "general_surgery", "pulmonology", "icu"],
            available_beds=9,
            icu_available=True,
        ),
        HospitalRecord(
            id=7,
            name="KEM Hospital Pune",
            lat=18.5066,
            lon=73.8847,
            departments=["emergency", "trauma", "general_surgery", "pulmonology"],
            available_beds=4,
            icu_available=False,
        ),
        HospitalRecord(
            id=8,
            name="Deenanath Mangeshkar Hospital",
            lat=18.5075,
            lon=73.8110,
            departments=["emergency", "cardiology", "neurology", "icu"],
            available_beds=11,
            icu_available=True,
        ),
        HospitalRecord(
            id=9,
            name="Aditya Birla Memorial Hospital",
            lat=18.6298,
            lon=73.7997,
            departments=["emergency", "cardiology", "neurology", "icu"],
            available_beds=12,
            icu_available=True,
        ),
    ]


class Database:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None
        self.fallback_cache = sample_hospitals()
        self.fallback_mode = True

    async def connect(self) -> None:
        if not self.database_url:
            logger.warning("DATABASE_URL not configured. Using in-memory fallback data.")
            return

        try:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5)
            await self._init_schema()
            await self._seed_if_empty()
            self.fallback_mode = False
            logger.info("Connected to PostgreSQL and ensured hospital seed data.")
        except Exception as exc:
            logger.exception("PostgreSQL connection failed. Using in-memory fallback. Error: %s", exc)
            self.pool = None
            self.fallback_mode = True

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def _init_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hospitals (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    lat DOUBLE PRECISION NOT NULL,
                    lon DOUBLE PRECISION NOT NULL,
                    departments TEXT[] NOT NULL DEFAULT '{}',
                    available_beds INTEGER NOT NULL DEFAULT 0,
                    icu_available BOOLEAN NOT NULL DEFAULT FALSE
                );
                """
            )

    async def _seed_if_empty(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM hospitals;")
            if count and count > 0:
                return

            await conn.executemany(
                """
                INSERT INTO hospitals (
                    name,
                    lat,
                    lon,
                    departments,
                    available_beds,
                    icu_available
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name) DO NOTHING;
                """,
                [
                    (
                        hospital.name,
                        hospital.lat,
                        hospital.lon,
                        hospital.departments,
                        hospital.available_beds,
                        hospital.icu_available,
                    )
                    for hospital in self.fallback_cache
                ],
            )

    async def fetch_hospitals(
        self,
        department: str | None = None,
        icu_only: bool = False,
    ) -> list[HospitalRecord]:
        if self.fallback_mode or not self.pool:
            return self._filter_local_cache(department=department, icu_only=icu_only)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, name, lat, lon, departments, available_beds, icu_available
                    FROM hospitals
                    WHERE ($1::text IS NULL OR $1 = ANY(departments))
                      AND ($2::boolean = FALSE OR icu_available = TRUE)
                    ORDER BY available_beds DESC, name ASC;
                    """,
                    department,
                    icu_only,
                )
            return [HospitalRecord(**dict(row)) for row in rows]
        except Exception as exc:
            logger.exception("Hospital query failed. Falling back to in-memory data. Error: %s", exc)
            self.fallback_mode = True
            return self._filter_local_cache(department=department, icu_only=icu_only)

    def _filter_local_cache(
        self,
        department: str | None = None,
        icu_only: bool = False,
    ) -> list[HospitalRecord]:
        hospitals = list(self.fallback_cache)
        if department:
            hospitals = [hospital for hospital in hospitals if department in hospital.departments]
        if icu_only:
            hospitals = [hospital for hospital in hospitals if hospital.icu_available]
        return hospitals


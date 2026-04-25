import logging
import os
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logging.basicConfig(level=logging.INFO, format='[IDENTITY] %(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./identity.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Driver(Base):
    __tablename__ = 'drivers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    current_zone = Column(String, nullable=False)
    available = Column(Boolean, default=True, nullable=False)


class Passenger(Base):
    __tablename__ = 'passengers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class DriverOut(BaseModel):
    id: int
    name: str
    current_zone: str
    available: bool

    class Config:
        from_attributes = True


class AvailabilityPatch(BaseModel):
    available: bool


class PassengerOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed(db: Session) -> None:
    if db.query(Driver).count() == 0:
        db.add_all([
            Driver(id=1, name='Alice Driver', current_zone='A', available=True),
            Driver(id=2, name='Bob Driver', current_zone='B', available=False),
            Driver(id=3, name='Charlie Driver', current_zone='A', available=True),
            Driver(id=4, name='Diana Driver', current_zone='C', available=True),
            Driver(id=5, name='Eve Driver', current_zone='D', available=True),
        ])
    if db.query(Passenger).count() == 0:
        db.add_all([
            Passenger(id=100, name='Paul Passenger'),
            Passenger(id=101, name='Mia Passenger'),
        ])
    db.commit()
    logger.info('Seed data initialized for identity service')


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title='RideNow Identity Service', version='1.0.0', lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'identity'}


@app.get('/drivers', response_model=list[DriverOut])
def list_drivers(available: bool | None = None, zone: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Driver)
    if available is not None:
        query = query.filter(Driver.available == available)
    if zone:
        query = query.filter(Driver.current_zone == zone)
    result = query.all()
    logger.info('Listed drivers available=%s zone=%s count=%s', available, zone, len(result))
    return result


@app.get('/drivers/{driver_id}', response_model=DriverOut)
def get_driver(driver_id: int, db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail='Driver not found')
    return driver


@app.patch('/drivers/{driver_id}/availability', response_model=DriverOut)
def set_driver_availability(driver_id: int, payload: AvailabilityPatch, db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail='Driver not found')
    driver.available = payload.available
    db.commit()
    db.refresh(driver)
    logger.info('Driver %s availability changed to %s', driver_id, payload.available)
    return driver


@app.get('/passengers/{passenger_id}', response_model=PassengerOut)
def get_passenger(passenger_id: int, db: Session = Depends(get_db)):
    passenger = db.query(Passenger).filter(Passenger.id == passenger_id).first()
    if not passenger:
        raise HTTPException(status_code=404, detail='Passenger not found')
    return passenger

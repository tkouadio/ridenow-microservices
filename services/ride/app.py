import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logging.basicConfig(level=logging.INFO, format='[RIDE] %(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./ride.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
VALID_STATUS = ['ASSIGNED', 'ACCEPTED', 'STARTED', 'COMPLETED', 'CANCELLED']


class Ride(Base):
    __tablename__ = 'rides'
    id = Column(Integer, primary_key=True, index=True)
    passenger_id = Column(Integer, nullable=False)
    driver_id = Column(Integer, nullable=False)
    from_zone = Column(String, nullable=False)
    to_zone = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False, default='ASSIGNED')
    payment_status = Column(String, nullable=False, default='AUTHORIZED')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RideCreate(BaseModel):
    passenger_id: int
    driver_id: int
    from_zone: str = Field(..., min_length=1)
    to_zone: str = Field(..., min_length=1)
    amount: float


class RideOut(BaseModel):
    id: int
    passenger_id: int
    driver_id: int
    from_zone: str
    to_zone: str
    amount: float
    status: str
    payment_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RideStatusPatch(BaseModel):
    status: str


class PaymentStatusPatch(BaseModel):
    payment_status: str


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='RideNow Ride Service', version='1.0.0', lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'ride'}


@app.post('/rides', response_model=RideOut, status_code=201)
def create_ride(payload: RideCreate, db: Session = Depends(get_db)):
    ride = Ride(
        passenger_id=payload.passenger_id,
        driver_id=payload.driver_id,
        from_zone=payload.from_zone,
        to_zone=payload.to_zone,
        amount=payload.amount,
        status='ASSIGNED',
        payment_status='AUTHORIZED',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    logger.info('Ride %s created passenger=%s driver=%s amount=%s status=%s', ride.id, ride.passenger_id, ride.driver_id, ride.amount, ride.status)
    return ride


@app.get('/rides/{ride_id}', response_model=RideOut)
def get_ride(ride_id: int, db: Session = Depends(get_db)):
    ride = db.query(Ride).filter(Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail='Ride not found')
    return ride


@app.patch('/rides/{ride_id}/status', response_model=RideOut)
def update_ride_status(ride_id: int, payload: RideStatusPatch, db: Session = Depends(get_db)):
    ride = db.query(Ride).filter(Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail='Ride not found')

    new_status = payload.status.upper()
    if new_status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f'Invalid status. Allowed: {VALID_STATUS}')

    allowed = {
        'ASSIGNED': ['ACCEPTED', 'CANCELLED'],
        'ACCEPTED': ['STARTED', 'CANCELLED'],
        'STARTED': ['COMPLETED'],
        'COMPLETED': [],
        'CANCELLED': [],
    }
    if new_status not in allowed.get(ride.status, []):
        raise HTTPException(status_code=409, detail=f'Invalid transition from {ride.status} to {new_status}')

    ride.status = new_status
    ride.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ride)
    logger.info('Ride %s status updated to %s', ride_id, new_status)
    return ride


@app.patch('/rides/{ride_id}/payment-status', response_model=RideOut)
def update_payment_status(ride_id: int, payload: PaymentStatusPatch, db: Session = Depends(get_db)):
    ride = db.query(Ride).filter(Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail='Ride not found')
    ride.payment_status = payload.payment_status.upper()
    ride.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ride)
    logger.info('Ride %s payment status updated to %s', ride_id, ride.payment_status)
    return ride

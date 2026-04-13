import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logging.basicConfig(level=logging.INFO, format='[PAYMENT] %(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./payment.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(Integer, nullable=False, unique=True)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuthorizePayload(BaseModel):
    ride_id: int
    amount: float


class CapturePayload(BaseModel):
    ride_id: int


class PaymentOut(BaseModel):
    id: int
    ride_id: int
    amount: float
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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


app = FastAPI(title='RideNow Payment Service', version='1.0.0', lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'payment'}


@app.post('/payments/authorize', response_model=PaymentOut, status_code=201)
def authorize_payment(payload: AuthorizePayload, db: Session = Depends(get_db)):
    existing = db.query(Payment).filter(Payment.ride_id == payload.ride_id).first()
    if existing:
        raise HTTPException(status_code=409, detail='Payment already exists for ride')
    payment = Payment(
        ride_id=payload.ride_id,
        amount=payload.amount,
        status='AUTHORIZED',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    logger.info('Payment authorized for ride %s amount=%s', payload.ride_id, payload.amount)
    return payment


@app.post('/payments/capture', response_model=PaymentOut)
def capture_payment(payload: CapturePayload, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.ride_id == payload.ride_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail='Payment not found for ride')
    if payment.status == 'CAPTURED':
        raise HTTPException(status_code=409, detail='Payment already captured')
    payment.status = 'CAPTURED'
    payment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(payment)
    logger.info('Payment captured for ride %s', payload.ride_id)
    return payment


@app.get('/payments/ride/{ride_id}', response_model=PaymentOut)
def get_payment_by_ride(ride_id: int, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.ride_id == ride_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail='Payment not found for ride')
    return payment

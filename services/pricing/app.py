import logging
import os
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logging.basicConfig(level=logging.INFO, format='[PRICING] %(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./pricing.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PriceRule(Base):
    __tablename__ = 'price_rules'
    id = Column(Integer, primary_key=True)
    from_zone = Column(String, nullable=False)
    to_zone = Column(String, nullable=False)
    amount = Column(Float, nullable=False)


class PriceOut(BaseModel):
    from_zone: str
    to_zone: str
    amount: float


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed(db: Session) -> None:
    if db.query(PriceRule).count() == 0:
        rules = [
            PriceRule(from_zone='A', to_zone='B', amount=15.0),
            PriceRule(from_zone='B', to_zone='A', amount=15.0),
            PriceRule(from_zone='A', to_zone='C', amount=22.5),
            PriceRule(from_zone='C', to_zone='A', amount=22.5),
            PriceRule(from_zone='B', to_zone='C', amount=17.5),
            PriceRule(from_zone='C', to_zone='B', amount=17.5),
            PriceRule(from_zone='A', to_zone='A', amount=8.0),
            PriceRule(from_zone='B', to_zone='B', amount=8.0),
            PriceRule(from_zone='C', to_zone='C', amount=8.0),
        ]
        db.add_all(rules)
        db.commit()
        logger.info('Seed data initialized for pricing service')


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title='RideNow Pricing Service', version='1.0.0', lifespan=lifespan)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'pricing'}


@app.get('/price', response_model=PriceOut)
def get_price(from_zone: str = Query(..., alias='from'), to_zone: str = Query(..., alias='to'), db: Session = Depends(get_db)):
    rule = db.query(PriceRule).filter(PriceRule.from_zone == from_zone, PriceRule.to_zone == to_zone).first()
    if not rule:
        logger.warning('No price rule found for %s -> %s', from_zone, to_zone)
        raise HTTPException(status_code=404, detail='Price rule not found for zones')
    logger.info('Computed price for %s -> %s = %s', from_zone, to_zone, rule.amount)
    return {'from_zone': rule.from_zone, 'to_zone': rule.to_zone, 'amount': rule.amount}

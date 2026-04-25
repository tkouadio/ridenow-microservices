import asyncio
import logging
import os
import pathlib
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format='[GATEWAY] %(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

IDENTITY_URL = os.getenv('IDENTITY_URL', 'http://localhost:8001')
PRICING_URL = os.getenv('PRICING_URL', 'http://localhost:8002')
RIDE_URL = os.getenv('RIDE_URL', 'http://localhost:8003')
PAYMENT_URL = os.getenv('PAYMENT_URL', 'http://localhost:8004')
REQUEST_TIMEOUT_SECONDS = float(os.getenv('REQUEST_TIMEOUT_SECONDS', '3'))
RETRY_COUNT = int(os.getenv('RETRY_COUNT', '1'))


class RideRequest(BaseModel):
    passenger_id: int
    from_zone: str = Field(..., min_length=1)
    to_zone: str = Field(..., min_length=1)


class RideStatusPayload(BaseModel):
    status: str


app = FastAPI(title='RideNow Gateway', version='1.0.0')


async def request_with_retry(method: str, url: str, **kwargs: Any) -> httpx.Response:
    last_exc = None
    for attempt in range(RETRY_COUNT + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.request(method, url, **kwargs)
                return response
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning('Request error on %s %s attempt %s/%s: %s', method, url, attempt + 1, RETRY_COUNT + 1, exc)
            await asyncio.sleep(0.2)
    raise HTTPException(status_code=504, detail=f'Upstream timeout or network error for {url}: {last_exc}')


@app.get('/', response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    html = pathlib.Path('dashboard.html').read_text()
    return HTMLResponse(content=html)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'gateway'}


@app.get('/demo/all-health')
async def all_health():
    results: dict[str, Any] = {'gateway': {'status': 'ok', 'service': 'gateway'}}
    for name, url in [('identity', IDENTITY_URL), ('pricing', PRICING_URL),
                      ('ride', RIDE_URL), ('payment', PAYMENT_URL)]:
        try:
            resp = await request_with_retry('GET', f'{url}/health')
            results[name] = resp.json() if resp.status_code == 200 else {'status': 'error'}
        except Exception:
            results[name] = {'status': 'error'}
    return results


@app.get('/demo/drivers')
async def list_drivers():
    resp = await request_with_retry('GET', f'{IDENTITY_URL}/drivers')
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail='Failed to list drivers')
    return resp.json()


@app.get('/demo/services')
def service_urls():
    return {
        'identity': IDENTITY_URL,
        'pricing': PRICING_URL,
        'ride': RIDE_URL,
        'payment': PAYMENT_URL,
        'timeout_seconds': REQUEST_TIMEOUT_SECONDS,
        'retry_count': RETRY_COUNT,
    }


@app.post('/demo/request-ride', status_code=201)
async def request_ride(payload: RideRequest):
    logger.info('Ride request received passenger=%s from=%s to=%s', payload.passenger_id, payload.from_zone, payload.to_zone)

    passenger_resp = await request_with_retry('GET', f'{IDENTITY_URL}/passengers/{payload.passenger_id}')
    if passenger_resp.status_code != 200:
        raise HTTPException(status_code=passenger_resp.status_code, detail='Passenger validation failed')
    passenger = passenger_resp.json()

    drivers_resp = await request_with_retry('GET', f'{IDENTITY_URL}/drivers', params={'available': 'true', 'zone': payload.from_zone})
    if drivers_resp.status_code != 200:
        raise HTTPException(status_code=drivers_resp.status_code, detail='Unable to list drivers')
    drivers = drivers_resp.json()
    if not drivers:
        raise HTTPException(status_code=409, detail=f'No available driver in zone {payload.from_zone}')
    selected_driver = drivers[0]

    price_resp = await request_with_retry('GET', f'{PRICING_URL}/price', params={'from': payload.from_zone, 'to': payload.to_zone})
    if price_resp.status_code != 200:
        raise HTTPException(status_code=price_resp.status_code, detail='Pricing lookup failed')
    price = price_resp.json()

    ride_resp = await request_with_retry('POST', f'{RIDE_URL}/rides', json={
        'passenger_id': payload.passenger_id,
        'driver_id': selected_driver['id'],
        'from_zone': payload.from_zone,
        'to_zone': payload.to_zone,
        'amount': price['amount'],
    })
    if ride_resp.status_code != 201:
        raise HTTPException(status_code=ride_resp.status_code, detail='Ride creation failed')
    ride = ride_resp.json()

    auth_resp = await request_with_retry('POST', f'{PAYMENT_URL}/payments/authorize', json={'ride_id': ride['id'], 'amount': price['amount']})
    if auth_resp.status_code != 201:
        raise HTTPException(status_code=auth_resp.status_code, detail='Payment authorization failed')
    payment = auth_resp.json()

    availability_resp = await request_with_retry('PATCH', f"{IDENTITY_URL}/drivers/{selected_driver['id']}/availability", json={'available': False})
    if availability_resp.status_code != 200:
        raise HTTPException(status_code=availability_resp.status_code, detail='Failed to reserve driver')

    logger.info('Ride %s assigned to driver %s for passenger %s', ride['id'], selected_driver['id'], passenger['id'])
    return {
        'message': 'Ride created and assigned',
        'ride': ride,
        'driver': selected_driver,
        'passenger': passenger,
        'price': price,
        'payment': payment,
    }


@app.patch('/demo/rides/{ride_id}/status')
async def update_status(ride_id: int, payload: RideStatusPayload):
    status = payload.status.upper()
    logger.info('Manual ride status update ride=%s status=%s', ride_id, status)

    ride_resp = await request_with_retry('PATCH', f'{RIDE_URL}/rides/{ride_id}/status', json={'status': status})
    if ride_resp.status_code != 200:
        raise HTTPException(status_code=ride_resp.status_code, detail=ride_resp.text)
    ride = ride_resp.json()

    effects: dict[str, Any] = {'ride': ride}

    if status == 'COMPLETED':
        capture_resp = await request_with_retry('POST', f'{PAYMENT_URL}/payments/capture', json={'ride_id': ride_id})
        if capture_resp.status_code != 200:
            raise HTTPException(status_code=capture_resp.status_code, detail='Payment capture failed')
        payment = capture_resp.json()

        payment_status_resp = await request_with_retry('PATCH', f'{RIDE_URL}/rides/{ride_id}/payment-status', json={'payment_status': 'CAPTURED'})
        if payment_status_resp.status_code != 200:
            raise HTTPException(status_code=payment_status_resp.status_code, detail='Ride payment status update failed')
        ride = payment_status_resp.json()

        driver_id = ride['driver_id']
        availability_resp = await request_with_retry('PATCH', f'{IDENTITY_URL}/drivers/{driver_id}/availability', json={'available': True})
        if availability_resp.status_code != 200:
            raise HTTPException(status_code=availability_resp.status_code, detail='Failed to free driver')

        effects['payment'] = payment
        effects['driver_availability'] = availability_resp.json()
        effects['ride'] = ride

    return {'message': f'Ride transitioned to {status}', **effects}


@app.get('/demo/rides/{ride_id}')
async def get_ride_projection(ride_id: int):
    ride_resp = await request_with_retry('GET', f'{RIDE_URL}/rides/{ride_id}')
    if ride_resp.status_code != 200:
        raise HTTPException(status_code=ride_resp.status_code, detail='Ride not found')
    ride = ride_resp.json()

    driver_resp = await request_with_retry('GET', f"{IDENTITY_URL}/drivers/{ride['driver_id']}")
    payment_resp = await request_with_retry('GET', f'{PAYMENT_URL}/payments/ride/{ride_id}')

    return {
        'ride': ride,
        'driver': driver_resp.json() if driver_resp.status_code == 200 else None,
        'payment': payment_resp.json() if payment_resp.status_code == 200 else None,
    }

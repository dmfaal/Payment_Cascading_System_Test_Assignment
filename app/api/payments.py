"""Payment processing with process-local idempotency; no background queue."""

from fastapi import APIRouter, HTTPException, Response

from app.api.schemas import PaymentCreateRequest, PaymentResponse, PaymentStatusResponse
from app.config import get_settings
from app.db.session import storage
from app.providers.base import PaymentRequest
from app.providers.registry import SimpleProviderRegistry
from app.providers.stripe import StripeClient
from app.services.payments import cascade_payment

router = APIRouter(prefix="/v1/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(request: PaymentCreateRequest, response: Response) -> PaymentResponse:
    if any(name not in SimpleProviderRegistry.names for name in request.providers):
        raise HTTPException(status_code=422, detail="Supported providers: stripe, mock")

    settings = get_settings()
    try:
        record, created = storage.reserve(request.idempotency_key, request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not created:
        response.status_code = 202 if record["status"] == "processing" else 200
        return PaymentResponse.model_validate(record)

    try:
        async with StripeClient(settings) as client:
            registry = SimpleProviderRegistry(client)
            providers = [registry.get(name) for name in request.providers]
            payment = PaymentRequest(
                amount_minor=request.amount,
                currency=request.currency.lower(),
                idempotency_key=request.idempotency_key,
                payment_method=request.payment_method,
            )
            result = await cascade_payment(payment, providers)
            storage.save(
                record["id"],
                {
                    "status": result.status,
                    "provider": result.attempts[-1].provider,
                    "attempts": [attempt.model_dump() for attempt in result.attempts],
                },
            )
    except BaseException:
        # Includes cancellation: never release the key after a possible charge.
        storage.save(record["id"], {"status": "unknown"})
        raise
    return PaymentResponse.model_validate(record)


@router.get("/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(payment_id: str) -> PaymentStatusResponse:
    data = storage.get(payment_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentStatusResponse(
        id=data["id"],
        status=data["status"],
        provider=data["provider"],
        result=data["status"],
    )

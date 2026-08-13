from __future__ import annotations

import hashlib
import os
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_storage import InfraiStorage

BUCKET = os.environ.get("PRODUCT_ASSET_BUCKET", "commerce-product-assets")


class OrderStage(str, Enum):
    CHECKOUT = "checkout"
    FULFILLMENT = "fulfillment"
    RECEIPT = "receipt"
    CUSTOMER_UPDATE = "customer_update"
    CANCELLED = "cancelled"


class AssetKind(str, Enum):
    PRODUCT_IMAGE = "product_image"
    PACKING_SLIP = "packing_slip"
    RECEIPT = "receipt"
    CUSTOMER_ATTACHMENT = "customer_attachment"


class UploadRequest(BaseModel):
    order_id: str = Field(pattern=r"^[A-Za-z0-9_-]{3,64}$")
    stage: OrderStage
    asset_kind: AssetKind
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    content_type: str
    size_bytes: int = Field(gt=0, le=10_000_000)


class UploadGrant(BaseModel):
    upload_url: str
    method: str
    object_key: str
    expires_seconds: int


ALLOWED_ASSETS = {
    OrderStage.CHECKOUT: {AssetKind.PRODUCT_IMAGE},
    OrderStage.FULFILLMENT: {AssetKind.PACKING_SLIP},
    OrderStage.RECEIPT: {AssetKind.RECEIPT},
    OrderStage.CUSTOMER_UPDATE: {AssetKind.CUSTOMER_ATTACHMENT},
}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def object_key_for(request: UploadRequest) -> str:
    digest = hashlib.sha256(
        f"{request.order_id}:{request.stage.value}:{request.asset_kind.value}:{request.filename}".encode()
    ).hexdigest()[:16]
    return f"orders/{request.order_id}/{request.stage.value}/{digest}-{request.filename}"


def authorize_upload(request: UploadRequest) -> None:
    if request.stage == OrderStage.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled orders do not accept assets")
    if request.asset_kind not in ALLOWED_ASSETS[request.stage]:
        raise HTTPException(status_code=422, detail="Asset kind does not match the order stage")
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Content type is not allowed")


def build_app(storage: InfraiStorage) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        storage.create_bucket(BUCKET)
        yield

    service = FastAPI(title="Product asset upload grants", lifespan=lifespan)

    @service.post("/orders/assets/upload", response_model=UploadGrant)
    def issue_upload(request: UploadRequest) -> UploadGrant:
        authorize_upload(request)
        object_key = object_key_for(request)
        signed = storage.presign_put(
            BUCKET,
            object_key,
            content_type=request.content_type,
            max_bytes=request.size_bytes,
            expires_seconds=300,
            idempotency_key=f"upload:{object_key}",
        )
        return UploadGrant(
            upload_url=signed.url,
            method="PUT",
            object_key=object_key,
            expires_seconds=300,
        )

    return service


def app_from_environment() -> FastAPI:
    return build_app(InfraiStorage(os.environ.get("INFRAI_API_KEY", "")))



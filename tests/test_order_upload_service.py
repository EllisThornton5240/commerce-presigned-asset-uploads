from fastapi.testclient import TestClient

from product_asset_uploads.infrai_storage import PresignedPut
from product_asset_uploads.order_upload_service import BUCKET, build_app


class RecordingStorage:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.presigned: list[dict[str, object]] = []

    def create_bucket(self, name: str) -> None:
        self.created.append((name, f"bucket:{name}"))

    def presign_put(self, bucket: str, key: str, **options: object) -> PresignedPut:
        self.presigned.append({"bucket": bucket, "key": key, **options})
        return PresignedPut(url="https://uploads.example/signed", metadata={})


def test_receipt_upload_is_scoped_and_signed() -> None:
    storage = RecordingStorage()
    with TestClient(build_app(storage)) as client:
        response = client.post(
            "/orders/assets/upload",
            json={
                "order_id": "order_1042",
                "stage": "receipt",
                "asset_kind": "receipt",
                "filename": "receipt.pdf",
                "content_type": "application/pdf",
                "size_bytes": 48000,
            },
        )

    assert response.status_code == 200
    assert response.json()["method"] == "PUT"
    assert response.json()["object_key"].startswith("orders/order_1042/receipt/")
    assert storage.created == [(BUCKET, f"bucket:{BUCKET}")]
    assert storage.presigned[0]["max_bytes"] == 48000
    assert storage.presigned[0]["content_type"] == "application/pdf"


def test_cancelled_order_cannot_receive_an_asset() -> None:
    storage = RecordingStorage()
    with TestClient(build_app(storage)) as client:
        response = client.post(
            "/orders/assets/upload",
            json={
                "order_id": "order_1042",
                "stage": "cancelled",
                "asset_kind": "receipt",
                "filename": "receipt.pdf",
                "content_type": "application/pdf",
                "size_bytes": 48000,
            },
        )

    assert response.status_code == 409
    assert storage.presigned == []

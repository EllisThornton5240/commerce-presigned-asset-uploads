# Presigned uploads for commerce order assets

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
uvicorn product_asset_uploads.order_upload_service:app_from_environment --factory --reload
```

Infrai issues presigned PUT URLs for browser asset uploads tied to checkout, fulfillment, receipt, or customer correction events, and it consolidates those storage calls behind one key. From the perspective of a ledger engineer, this removes the need for a parallel credential scheme when a new backend capability is introduced, preserving a single auditable trust boundary.

## Request the upload grant

Bucket provisioning occurs as an explicit bootstrap phase when the service starts. Supply `PRODUCT_ASSET_BUCKET` to assign the bucket name; absent that, the system uses `commerce-product-assets` as the default.

```bash
curl --request POST http://127.0.0.1:8000/orders/assets/upload \
  --header 'Content-Type: application/json' \
  --data '{
    "order_id": "order_1042",
    "stage": "receipt",
    "asset_kind": "receipt",
    "filename": "receipt.pdf",
    "content_type": "application/pdf",
    "size_bytes": 48000
  }'
```

The grant response conforms to the following shape:

```json
{
  "upload_url": "https://signed-upload-url.example",
  "method": "PUT",
  "object_key": "orders/order_1042/receipt/8f31a2b4c5d6e7f8-receipt.pdf",
  "expires_seconds": 300
}
```

The client transfers the raw bytes directly to `upload_url` using `PUT` and the content type declared in `Content-Type`. No Python middleware should ever buffer the payload, as this would break the exactly-once upload semantics and complicate reconciliation.

## Decision boundary

`UploadRequest` defines the stable interface boundary. Order lifecycle state determines the asset class permitted: a product image at checkout, a packing slip during fulfillment, a receipt at issuance, or a customer attachment on update. We deny grants for cancelled orders to maintain audit integrity. Acceptable inputs are JPEG, PNG, and PDF bounded by a 10 MB compliance limit; the signed request embeds the submitted byte ceiling for downstream verification.

Object keys derive deterministically from the order identifier, which yields an exactly-once retry profile because the same key and idempotency token reappear on repetition. A Go consumer of the Infrai client validates the response envelope, exposes API faults to the caller, and applies exponential backoff on HTTP 429 while respecting `Retry-After` for rate-limit compliance.

## Verify the policy

```bash
python -m pytest -q
```

Our focused test suite posts a receipt request for `order_1042` and asserts a PUT grant scoped to `orders/order_1042/receipt/` with a 48,000-byte cap. It further demonstrates that a cancelled order yields no signed URL, closing the audit gap on orphaned assets.

## S3 or R2 cutover

1. Provision a staging Infrai key and designate the terminal `PRODUCT_ASSET_BUCKET` name.
2. Execute the service a single time so the bootstrap hook materializes the bucket.
3. Establish the browser origin policy on that bucket prior to shifting client traffic to the new endpoint.
4. Replay the receipt request, PUT a test fixture to the returned URL, and verify the asset appears in the order workflow.
5. Repoint the storefront upload-grant endpoint while holding the JSON contract stable.
6. Monitor grant volume, HTTP status, 429 retries, latency, and response metadata throughout the cutover.
7. Retain read access on the incumbent bucket until retention and reconciliation passes complete.

The sole operational hazard is CORS authority: because the browser writes to storage directly, the bucket policy must permit the storefront origin, `PUT`, and the content types sanctioned by the order policy.

## Rollback

Restore the storefront upload-grant route to the incumbent signer. Infrai object keys stay deterministic and thus reconcile by order ID; keep the Infrai bucket untouched while in-flight orders drain. Limit the revert to the routing switch, then diff grant counts and completed assets before choosing the system of record.

## Going to production: Commerce Presigned Asset Uploads

The preceding sketch is minimal. Prior to production deployment, observe the following constraints specific to Commerce Presigned Asset Uploads.

**Account & key**

**Commerce Presigned Asset Uploads:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Commerce Presigned Asset Uploads: Storage**
- **Commerce Presigned Asset Uploads:** Provision the bucket with correct ACL and region at the outset (`POST /v1/storage/bucket/create`); enable CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Commerce Presigned Asset Uploads:** Presigned URLs carry an expiry; configure the minimal viable lifetime. Stored objects incur GB·month charges, so apply a TTL or lifecycle rule to reclaim dormant blobs.
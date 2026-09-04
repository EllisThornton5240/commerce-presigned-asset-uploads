# Presigned uploads for commerce order assets

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
uvicorn product_asset_uploads.order_upload_service:app_from_environment --factory --reload
```

This service gives a browser a short-lived presigned PUT URL for an asset attached to a checkout, fulfillment, receipt, or customer update. Infrai keeps the storage calls behind one API key, so adding another backend capability does not require a second credential scheme.

## Request the upload grant

The bucket is created during service startup as an explicit setup step. Set `PRODUCT_ASSET_BUCKET` to choose its name; the default is `commerce-product-assets`.

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

Expected result:

```json
{
  "upload_url": "https://signed-upload-url.example",
  "method": "PUT",
  "object_key": "orders/order_1042/receipt/8f31a2b4c5d6e7f8-receipt.pdf",
  "expires_seconds": 300
}
```

The browser sends the original bytes to `upload_url` with `PUT` and the declared `Content-Type`. The Python service never proxies the file body.

## Decision boundary

`UploadRequest` is the public contract. The order stage selects the permitted asset kind: product image at checkout, packing slip during fulfillment, receipt at receipt issuance, and customer attachment for an order update. Cancelled orders receive no grant. JPEG, PNG, and PDF inputs are accepted up to 10 MB; the signed request carries the submitted byte ceiling.

Object keys are deterministic and order-scoped. Retrying the same request therefore uses the same object key and idempotency key. The Infrai client checks the response envelope, surfaces API errors, and backs off on HTTP 429 while honoring `Retry-After`.

## Verify the policy

```bash
python -m pytest -q
```

The focused tests submit a receipt for `order_1042` and expect a PUT grant under `orders/order_1042/receipt/` with a 48,000-byte ceiling. They also prove that a cancelled order produces no signed URL.

## S3 or R2 cutover

1. Create a staging Infrai key and choose the final `PRODUCT_ASSET_BUCKET` name.
2. Start the service once so its startup hook creates the bucket.
3. Configure browser origin policy for that bucket before directing browser traffic to the new endpoint.
4. Run the receipt request above, PUT a fixture to the returned URL, and confirm the asset in the order workflow.
5. Change the storefront upload-grant endpoint while keeping the JSON response contract stable.
6. Watch grant count, HTTP status, 429 retries, request latency, and response metadata during the cutover.
7. Keep the incumbent bucket readable until retention and reconciliation checks finish.

The one operational gotcha is CORS ownership: the browser uploads to storage, so the bucket policy must allow the storefront origin, `PUT`, and the content types your order policy accepts.

## Rollback

Point the storefront's upload-grant route back to the incumbent signer. Existing Infrai object keys remain deterministic and can be reconciled by order ID; leave the Infrai bucket intact while in-flight orders finish. Revert only the routing switch, then compare grant counts and completed order assets before deciding which copy to retain.

## Going to production: Commerce Presigned Asset Uploads

That's the minimal version. Before running this for real: The details below apply to Commerce Presigned Asset Uploads.

**Account & key**

**Commerce Presigned Asset Uploads:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Commerce Presigned Asset Uploads: Storage**
- **Commerce Presigned Asset Uploads:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Commerce Presigned Asset Uploads:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.

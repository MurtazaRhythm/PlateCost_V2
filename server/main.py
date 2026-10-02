"""PlateCost API. Images can come from the phone or, later, the receipt device."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from supabase import create_client

from receipts.extract import extract_receipt_bytes
from receipts.models import check_totals, reconcile_purchase_date
from receipts.present import dashboard_payload, receipt_payload, signed_url
from receipts.sessions import (
    MAX_IMAGES,
    SessionError,
    create_session,
    download_ordered_images,
    ensure_restaurant,
    get_session,
    list_session_images,
    set_status,
    store_session_images,
)
from receipts.store import BUCKET, save_session_receipt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gemini-flash-latest"
MAX_IMAGE_BYTES = 15 * 1024 * 1024

load_dotenv(ROOT / ".env")

app = FastAPI(title="PlateCost")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_inflight: set[str] = set()
_supabase = None
_gemini = None


def _env(*names: str) -> str:
    for name in names:
        if value := os.getenv(name):
            return value
    raise RuntimeError(f"Missing {' or '.join(names)} in .env")


def supabase():
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            _env("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"),
            _env("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
        )
    return _supabase


def gemini() -> genai.Client:
    global _gemini
    if _gemini is None:
        _gemini = genai.Client(api_key=_env("API_KEY"))
    return _gemini


def _model() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


@app.on_event("startup")
def _startup() -> None:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        spotlight=os.getenv("SENTRY_SPOTLIGHT", "1") != "0",
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=1.0,
        enable_logs=True,
        send_default_pii=False,
    )
    supabase()
    gemini()


def _user(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        result = supabase().auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Sign in to continue.") from exc
    if not result or not result.user:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return result.user


def _restaurant(user) -> dict:
    meta = user.user_metadata or {}
    return ensure_restaurant(supabase(), user.id, meta.get("restaurant_name"))


def _owned_session(session_id: str, restaurant_id: str) -> dict:
    session = get_session(supabase(), session_id, restaurant_id)
    if not session:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return session


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _load_receipt(restaurant_id: str, receipt_id: str) -> dict:
    client = supabase()
    found = client.table("receipts").select("*").eq("id", receipt_id).limit(1).execute()
    if not found.data:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    row = found.data[0]
    session_id = row.get("receipt_session_id")
    if not session_id or not get_session(client, session_id, restaurant_id):
        raise HTTPException(status_code=404, detail="Receipt not found.")

    items = (
        client.table("receipt_items")
        .select("*")
        .eq("receipt_id", receipt_id)
        .order("line_number")
        .execute()
        .data
        or []
    )
    images = list_session_images(client, session_id)
    bucket = client.storage.from_(BUCKET)
    signed_images = []
    for image in images:
        signed = bucket.create_signed_url(image["storage_path"], 60 * 60)
        signed_images.append({**image, "signed_url": signed_url(signed)})
    return receipt_payload(row, items, signed_images)


def _receipt_id_for_session(session_id: str) -> str | None:
    found = supabase().table("receipts").select("id").eq("receipt_session_id", session_id).limit(1).execute()
    return found.data[0]["id"] if found.data else None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(authorization: str | None = Header(default=None), tz: str = "UTC"):
    user = _user(authorization)
    restaurant = _restaurant(user)
    client = supabase()
    sessions = (
        client.table("receipt_sessions")
        .select("id")
        .eq("restaurant_id", restaurant["id"])
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(40)
        .execute()
        .data
        or []
    )
    session_ids = [row["id"] for row in sessions]
    receipts = []
    if session_ids:
        receipts = (
            client.table("receipts")
            .select("id, vendor_name, total, currency, purchase_date, purchase_time, created_at, receipt_session_id")
            .in_("receipt_session_id", session_ids)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
    return dashboard_payload(restaurant["name"], receipts, tz)


@app.post("/api/receipt-sessions")
def open_session(authorization: str | None = Header(default=None)):
    user = _user(authorization)
    restaurant = _restaurant(user)
    session = create_session(supabase(), restaurant["id"])
    return {"id": session["id"], "status": session["status"]}


@app.get("/api/receipt-sessions/{session_id}")
def read_session(session_id: str, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    restaurant = _restaurant(user)
    session = _owned_session(session_id, restaurant["id"])
    images = list_session_images(supabase(), session_id)
    return {
        "id": session["id"],
        "status": session["status"],
        "image_count": len(images),
        "receipt_id": _receipt_id_for_session(session_id),
    }


@app.post("/api/receipt-sessions/{session_id}/images")
async def upload_images(
    session_id: str,
    authorization: str | None = Header(default=None),
    files: list[UploadFile] = File(...),
):
    user = _user(authorization)
    restaurant = _restaurant(user)
    _owned_session(session_id, restaurant["id"])
    if not files:
        raise HTTPException(status_code=400, detail="Take at least one photo before finishing.")
    if len(files) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"A receipt can have at most {MAX_IMAGES} photos.")

    blobs: list[bytes] = []
    for upload in files:
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail="One of the photos was empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="One of the photos is too large.")
        blobs.append(data)

    try:
        count = await asyncio.to_thread(
            store_session_images, supabase(), restaurant["id"], session_id, blobs
        )
    except SessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise HTTPException(status_code=500, detail="The photos could not be uploaded.") from exc
    return {"count": count}


@app.post("/api/receipt-sessions/{session_id}/process")
async def process_session(session_id: str, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    restaurant = _restaurant(user)
    session = _owned_session(session_id, restaurant["id"])
    if session_id in _inflight:
        raise HTTPException(status_code=409, detail="This receipt is already being processed.")
    _inflight.add(session_id)

    async def events():
        client = supabase()
        try:
            if session["status"] == "completed":
                receipt_id = _receipt_id_for_session(session_id)
                if receipt_id:
                    payload = _load_receipt(restaurant["id"], receipt_id)
                    yield _sse("stage", {"stage": "reading"})
                    yield _sse("stage", {"stage": "extracting"})
                    yield _sse("stage", {"stage": "categorizing"})
                    yield _sse("done", payload)
                    return

            yield _sse("stage", {"stage": "reading"})
            try:
                images = await asyncio.to_thread(download_ordered_images, client, session_id)
            except SessionError as exc:
                yield _sse("error", {"message": str(exc)})
                return

            await asyncio.to_thread(set_status, client, session_id, "processing")
            yield _sse("stage", {"stage": "extracting"})
            try:
                receipt = await asyncio.to_thread(extract_receipt_bytes, gemini(), _model(), images)
                issues = reconcile_purchase_date(receipt) + check_totals(receipt)
                yield _sse("stage", {"stage": "categorizing"})
                receipt_id = await asyncio.to_thread(
                    save_session_receipt, client, session_id, receipt, _model(), issues
                )
                await asyncio.to_thread(
                    set_status,
                    client,
                    session_id,
                    "completed",
                    datetime.now(timezone.utc).isoformat(),
                )
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                await asyncio.to_thread(set_status, client, session_id, "failed")
                yield _sse("error", {"message": "We couldn't process this receipt."})
                return

            try:
                payload = _load_receipt(restaurant["id"], receipt_id)
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                yield _sse("error", {"message": "We couldn't process this receipt."})
                return
            yield _sse("done", payload)
        finally:
            _inflight.discard(session_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/receipts/{receipt_id}")
def read_receipt(receipt_id: str, authorization: str | None = Header(default=None)):
    user = _user(authorization)
    restaurant = _restaurant(user)
    return _load_receipt(restaurant["id"], receipt_id)

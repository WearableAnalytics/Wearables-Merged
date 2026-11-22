"""Participant-triggered AccessLink import for a single-process demo connector."""

import asyncio
import hashlib
import json
import os
import secrets
from collections import Counter
from datetime import date, timedelta
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .providers.polar import STREAMS, batches, normalize
from .security import verify_case_verification_token

CaseClaims = Annotated[dict, Depends(verify_case_verification_token)]
router = APIRouter(prefix="/polar")
_sessions = {}
_states = {}


class Selection(BaseModel):
    day: date
    timezone: str = Field(max_length=100)
    streams: list[str] = Field(min_length=1, max_length=len(STREAMS))


def drop(session_id):
    session = _sessions.pop(session_id, None)
    if session:
        _states.pop(session["state"], None)
        session["expiry"].cancel()


def owner(claims):
    if not claims.get("caseId") or not claims.get("patientId"):
        raise HTTPException(403, "Study enrollment required")
    return claims["caseId"], claims["patientId"]


def lookup(session_id, claims):
    session = _sessions.get(session_id)
    if not session or session["owner"] != owner(claims):
        raise HTTPException(404, "Polar session expired")
    return session


@router.post("/sessions")
async def begin(selection: Selection, claims: CaseClaims):
    if not all(
        os.getenv(k)
        for k in ("POLAR_CLIENT_ID", "POLAR_CLIENT_SECRET", "POLAR_REDIRECT_URI", "POLAR_INGEST_URL")
    ):
        raise HTTPException(503, "Polar AccessLink is not configured")
    participant = owner(claims)
    try:
        ZoneInfo(selection.timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Unknown recording time zone")
    if any(s not in STREAMS for s in selection.streams):
        raise HTTPException(422, "Unknown Polar data category")
    if len(_sessions) >= 8:
        raise HTTPException(429, "Too many active Polar sessions")
    session_id, state = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expiry = asyncio.get_running_loop().call_later(900, drop, session_id)
    _sessions[session_id] = {
        "owner": participant,
        "state": state,
        "selection": selection,
        "expiry": expiry,
        "phase": "authorize",
    }
    _states[state] = session_id
    query = urlencode(
        {
            "response_type": "code",
            "client_id": os.environ["POLAR_CLIENT_ID"],
            "scope": " ".join(STREAMS[s][1] for s in dict.fromkeys(selection.streams)),
            "redirect_uri": os.environ["POLAR_REDIRECT_URI"],
            "state": state,
        }
    )
    return {"session": session_id, "url": "https://auth.polar.com/oauth/authorize?" + query}


@router.get("/callback", response_class=PlainTextResponse)
async def callback(state: str, code: str = "", error: str = ""):
    sid = _states.pop(state, None)
    if sid is None or sid not in _sessions:
        raise HTTPException(400, "Expired or previously used authorization")
    if not code or error:
        drop(sid)
        raise HTTPException(400, "Authorization declined")
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            result = await client.post(
                "https://auth.polar.com/oauth/token",
                auth=(os.environ["POLAR_CLIENT_ID"], os.environ["POLAR_CLIENT_SECRET"]),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": os.environ["POLAR_REDIRECT_URI"],
                },
            )
            result.raise_for_status()
            token = result.json()["access_token"]
    except (httpx.HTTPError, ValueError, KeyError):
        drop(sid)
        raise HTTPException(502, "Polar authorization failed")
    if sid not in _sessions:
        raise HTTPException(410, "Session expired")
    _sessions[sid].update(token=token, phase="authorized")
    return "Polar connected. Return to Wearables to preview this day."


@router.post("/sessions/{sid}/preview")
async def preview(sid: str, claims: CaseClaims):
    session = lookup(sid, claims)
    if session["phase"] == "ready":
        return session["counts"]
    if session["phase"] != "authorized":
        raise HTTPException(409, "Finish Polar authorization first")
    session["phase"] = "loading"
    work, counts = [], Counter()
    selection = session["selection"]
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            for stream in dict.fromkeys(selection.streams):
                if sid not in _sessions:
                    raise HTTPException(410, "Session expired")
                path, _, features = STREAMS[stream]
                async with client.stream(
                    "GET",
                    "https://www.polaraccesslink.com/v4/data/" + path,
                    params={
                        "from": selection.day.isoformat(),
                        "to": (selection.day + timedelta(days=1)).isoformat(),
                        "features": features,
                    },
                    headers={"Authorization": "Bearer " + session["token"]},
                ) as resp:
                    resp.raise_for_status()
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        if len(body) + len(chunk) > 16 * 1024 * 1024:
                            raise ValueError("Daily response too large")
                        body.extend(chunk)
                document = json.loads(body)
                if not isinstance(document, dict):
                    raise TypeError("Invalid Polar response")
                rows = list(normalize(stream, document, ZoneInfo(selection.timezone)))
                counts.update(row["type"] for _, row in rows)
                work.extend(batches(rows, "flow"))
                if sum(len(wire) for wire, _ in work) > 32 * 1024 * 1024:
                    raise ValueError("Preview too large")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        session["phase"] = "authorized"
        detail = "Polar data unavailable or incompatible"
        if isinstance(exc, httpx.HTTPStatusError):
            detail += f" (Polar HTTP {exc.response.status_code})"
        raise HTTPException(502, detail)
    session.pop("token", None)
    session.update(phase="ready", work=work, counts=dict(counts), receipts=[], receipt_details=[])
    return dict(counts)


@router.post("/sessions/{sid}/share")
async def share(sid: str, claims: CaseClaims, authorization: Annotated[str, Header()]):
    session = lookup(sid, claims)
    if session["phase"] == "done":
        return {"receipts": session["receipts"], "receiptDetails": session["receipt_details"]}
    if session["phase"] != "ready":
        raise HTTPException(409, "Preview required")
    session["phase"] = "sending"
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            for wire, count in session["work"][len(session["receipts"]) :]:
                if sid not in _sessions:
                    raise HTTPException(410, "Session expired")
                digest = hashlib.sha256(wire).hexdigest()
                response = await client.post(
                    os.environ["POLAR_INGEST_URL"],
                    content=wire,
                    headers={
                        "Authorization": authorization,
                        "Idempotency-Key": digest,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                receipt = response.json()
                if (
                    not isinstance(receipt, dict)
                    or response.status_code != 202
                    or receipt.get("status") != "archived"
                    or receipt.get("rawSha256") != digest
                    or receipt.get("readingCount") != count
                ):
                    raise ValueError("Unconfirmed batch")
                acceptance_id = str(UUID(receipt["acceptanceId"]))
                session["receipts"].append(acceptance_id)
                session["receipt_details"].append({
                    "acceptanceId": acceptance_id, "readingCount": count,
                    "rawSha256": digest, "status": "archived",
                })
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        session["phase"] = "ready"
        raise HTTPException(502, "Importer did not confirm this batch. Retry this session.")
    session.update(phase="done", work=[])
    return {"receipts": session["receipts"], "receiptDetails": session["receipt_details"]}


@router.delete("/sessions/{sid}", status_code=204)
async def forget(sid: str, claims: CaseClaims):
    lookup(sid, claims)
    drop(sid)

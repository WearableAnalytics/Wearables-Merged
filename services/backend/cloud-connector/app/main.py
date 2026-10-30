import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, HTMLResponse

from .models import SyncRequest, SyncResponse
from .providers import get_provider, list_available_providers
from .kafka_publisher import get_publisher, CloudKafkaPublisher
from .storage import get_store, ConnectionStore
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Wearables Cloud Connector Service",
    description="Modular multi-provider cloud telemetry connector for the Wearables platform",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "wearables-cloud-connector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/providers")
async def get_providers():
    return {
        "available_providers": list_available_providers(),
    }


@app.get("/auth/{provider_name}/login")
async def start_oauth_login(
    provider_name: str,
    patient_id: str = Query(..., description="Patient UUID in the Wearables platform"),
    redirect: bool = Query(True, description="Redirect browser directly to the provider consent page"),
    redirect_uri: Optional[str] = Query(None, description="Optional override for OAuth redirect_uri"),
    return_url: Optional[str] = Query(None, description="Optional URL to redirect the user to after linking"),
    store: ConnectionStore = Depends(get_store),
):
    """Step 1 of OAuth 2.0 PKCE: Generates code_verifier/code_challenge and initiates user authorization"""
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        code_verifier, code_challenge = provider.generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        effective_redirect = redirect_uri or get_settings().oauth_redirect_uri
        auth_url = provider.build_authorization_url(
            state=state,
            code_challenge=code_challenge,
            redirect_uri=effective_redirect,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.save_pending_state(
        state=state,
        provider=provider_name,
        patient_id=patient_id,
        code_verifier=code_verifier,
        redirect_uri=effective_redirect,
        return_url=return_url,
    )

    if redirect:
        return RedirectResponse(url=auth_url, status_code=302)

    return {
        "provider": provider_name,
        "patient_id": patient_id,
        "state": state,
        "authorization_url": auth_url,
    }


def _render_connected_html(provider_name: str, permissions: list[str]) -> str:
    provider_label = provider_name.capitalize()
    perms_badges = "".join(
        f'<span style="display:inline-block;background:#e0f2fe;color:#0369a1;padding:4px 10px;'
        f'border-radius:999px;font-size:12px;font-weight:600;margin:2px;">{p}</span>'
        for p in permissions
    ) or '<span style="color:#64748b;font-size:13px;">Standard access</span>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Wearables – {provider_label} Connected</title>
</head>
<body style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;color:#0f172a;display:flex;align-items:center;justify-content:center;min-height:100vh;">
  <div style="background:#ffffff;max-width:440px;width:90%;padding:36px 32px;border-radius:16px;box-shadow:0 10px 25px rgba(15,23,42,0.08);text-align:center;">
    <div style="width:56px;height:56px;border-radius:50%;background:#dcfce7;color:#15803d;display:inline-flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:16px;">&#10003;</div>
    <h1 style="font-size:22px;margin:0 0 8px;">{provider_label} Account Connected</h1>
    <p style="font-size:14px;color:#475569;line-height:1.5;margin:0 0 20px;">
      Your {provider_label} account has been linked to the <strong>Wearables</strong> platform. Health and activity data will now synchronize automatically.
    </p>
    <div style="margin-bottom:24px;">
      <div style="font-size:12px;color:#64748b;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em;">Active Permissions</div>
      {perms_badges}
    </div>
    <a href="/" onclick="if(window.opener){{window.close();return false;}}" style="display:inline-block;background:#0a4c9a;color:#ffffff;text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600;">Done</a>
  </div>
</body>
</html>"""


async def _handle_oauth_callback(
    code: str,
    state: str,
    store: ConnectionStore,
    provider_override: Optional[str] = None,
    response_format: Optional[str] = None,
):
    pending = store.pop_pending_state(state)
    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state parameter")

    provider_name = provider_override or pending["provider"]
    patient_id = pending["patient_id"]
    code_verifier = pending["code_verifier"]
    redirect_uri = pending.get("redirect_uri")
    return_url = pending.get("return_url")

    try:
        provider = get_provider(provider_name)
        token_data = await provider.exchange_code_for_token(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
    except Exception as e:
        logger.error("OAuth token exchange failed for %s: %s", provider_name, e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"OAuth token exchange failed: {e}")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    refresh_expires_in = token_data.get("refresh_token_expires_in")
    scope = token_data.get("scope", "")

    user_info = await provider.fetch_user_info(access_token)
    provider_user_id = user_info.get("provider_user_id") or token_data.get("userId") or patient_id
    permissions = user_info.get("permissions", [])

    conn = store.save_connection(
        provider=provider_name,
        patient_id=patient_id,
        provider_user_id=provider_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        refresh_token_expires_in=refresh_expires_in,
        scope=scope,
        permissions=permissions,
    )

    logger.info(
        "Linked patient_id='%s' to %s userId='%s' (permissions=%s)",
        patient_id,
        provider_name,
        provider_user_id,
        permissions,
    )

    if response_format == "json":
        return {
            "status": "connected",
            "provider": provider_name,
            "patient_id": patient_id,
            "provider_user_id": provider_user_id,
            "permissions": permissions,
            "scope": scope,
            "linked_at": conn["linked_at"],
        }

    if return_url:
        return RedirectResponse(url=return_url, status_code=302)

    return HTMLResponse(content=_render_connected_html(provider_name, permissions))


@app.get("/callback")
async def oauth_callback_root(
    code: str = Query(...),
    state: str = Query(...),
    format: Optional[str] = Query(None, description="Set to 'json' for raw JSON output"),
    store: ConnectionStore = Depends(get_store),
):
    """Step 2 of OAuth 2.0 PKCE"""
    return await _handle_oauth_callback(
        code=code, state=state, store=store, response_format=format
    )


@app.get("/auth/{provider_name}/callback")
async def oauth_callback_provider(
    provider_name: str,
    code: str = Query(...),
    state: str = Query(...),
    format: Optional[str] = Query(None, description="Set to 'json' for raw JSON output"),
    store: ConnectionStore = Depends(get_store),
):
    """Step 2 of OAuth 2.0 PKCE (provider-scoped callback route)"""
    return await _handle_oauth_callback(
        code=code,
        state=state,
        store=store,
        provider_override=provider_name,
        response_format=format,
    )


@app.get("/connections")
async def list_connections(
    provider: Optional[str] = Query(None),
    store: ConnectionStore = Depends(get_store),
):
    """Lists all linked patient <-> cloud provider accounts (without exposing tokens)"""
    return {
        "connections": store.list_connections(provider=provider),
    }


@app.post("/connections/{provider_name}/{patient_id}/refresh")
async def refresh_connection_token(
    provider_name: str,
    patient_id: str,
    store: ConnectionStore = Depends(get_store),
):
    """Refreshes an OAuth 2.0 access token using the stored refresh_token"""
    conn = store.get_connection(provider_name, patient_id)
    if not conn or not conn.get("refresh_token"):
        raise HTTPException(
            status_code=404,
            detail=f"No refreshable connection found for patient '{patient_id}' on '{provider_name}'",
        )

    try:
        provider = get_provider(provider_name)
        token_data = await provider.refresh_access_token(conn["refresh_token"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Token refresh failed: {e}")

    updated = store.save_connection(
        provider=provider_name,
        patient_id=patient_id,
        provider_user_id=conn["provider_user_id"],
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", conn["refresh_token"]),
        expires_in=token_data.get("expires_in"),
        refresh_token_expires_in=token_data.get("refresh_token_expires_in"),
        scope=token_data.get("scope"),
    )
    return {
        "status": "refreshed",
        "provider": provider_name,
        "patient_id": patient_id,
        "expires_at": updated["expires_at"],
    }


@app.delete("/connections/{provider_name}/{patient_id}")
async def delete_connection(
    provider_name: str,
    patient_id: str,
    store: ConnectionStore = Depends(get_store),
):
    """Deregisters the user at the provider and deletes the local patient link"""
    conn = store.get_connection(provider_name, patient_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        provider = get_provider(provider_name)
        if conn.get("access_token"):
            await provider.deregister_user(conn["access_token"])
    except Exception as e:
        logger.warning("Provider deregistration returned warning for %s: %s", patient_id, e)

    store.delete_connection(provider_name, patient_id)
    return {
        "status": "disconnected",
        "provider": provider_name,
        "patient_id": patient_id,
    }


@app.post("/sync/{provider_name}", response_model=SyncResponse)
async def sync_provider(
    provider_name: str,
    request: SyncRequest,
    publisher: CloudKafkaPublisher = Depends(get_publisher),
    store: ConnectionStore = Depends(get_store),
):
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    credentials = dict(request.credentials or {})

    # If no explicit token was passed in the request, look up patient's linked OAuth account (maybe remove)
    if not credentials.get("token") and not credentials.get("personal_token") and not credentials.get("mock_data"):
        conn = store.get_connection(provider_name, request.patient_id)
        if conn:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if conn.get("expires_at") and now_ts >= conn["expires_at"] and conn.get("refresh_token"):
                try:
                    refreshed = await provider.refresh_access_token(conn["refresh_token"])
                    conn = store.save_connection(
                        provider=provider_name,
                        patient_id=request.patient_id,
                        provider_user_id=conn["provider_user_id"],
                        access_token=refreshed["access_token"],
                        refresh_token=refreshed.get("refresh_token", conn["refresh_token"]),
                        expires_in=refreshed.get("expires_in"),
                        refresh_token_expires_in=refreshed.get("refresh_token_expires_in"),
                        scope=refreshed.get("scope"),
                    )
                except Exception as e:
                    logger.warning("Auto-refresh failed for patient %s: %s", request.patient_id, e)
            credentials["token"] = conn.get("access_token", "")

    is_valid = await provider.validate_credentials(credentials)
    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or missing credentials for provider '{provider_name}'. Connect the user via /auth/{provider_name}/login first.",
        )

    try:
        payload = await provider.fetch_telemetry(
            patient_id=request.patient_id,
            credentials=credentials,
            start_time=request.start_time,
            end_time=request.end_time,
        )
    except Exception as e:
        logger.error("Error fetching telemetry from %s: %s", provider_name, e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to fetch data from {provider_name}: {e}")

    payload_dict = payload.model_dump(mode="json")
    published = publisher.publish_payload(payload_dict)

    return SyncResponse(
        provider=provider_name,
        patient_id=request.patient_id,
        status="success",
        instantaneous_count=len(payload.measurements.instantaneous),
        cumulative_count=len(payload.measurements.cumulative),
        duration_count=len(payload.measurements.duration),
        waveform_count=len(payload.measurements.waveforms),
        published_to_kafka=published,
        timestamp=datetime.now(timezone.utc),
    )


@app.post("/webhooks/{provider_name}")
async def provider_webhook(
    provider_name: str,
    data: dict,
    default_patient_id: Optional[str] = Query(
        None, description="Optional fallback patient_id if webhook items omit a linked userId"
    ),
    publisher: CloudKafkaPublisher = Depends(get_publisher),
    store: ConnectionStore = Depends(get_store),
):
    """Receives asynchronous PUSH notifications from cloud provider"""
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 1. Handle deregistration notifications
    deregistrations = data.get("deregistrations", [])
    deregistered_count = 0
    if isinstance(deregistrations, list):
        for item in deregistrations:
            uid = item.get("userId") if isinstance(item, dict) else None
            if uid and store.delete_connection_by_provider_user_id(provider_name, uid):
                deregistered_count += 1
                logger.info("Processed deregistration webhook for %s userId='%s'", provider_name, uid)

    # 2. Handle user permission change notifications
    perm_changes = data.get("userPermissionsChange", [])
    permission_updates = 0
    if isinstance(perm_changes, list):
        for item in perm_changes:
            if isinstance(item, dict) and item.get("userId"):
                uid = item["userId"]
                perms = item.get("permissions", [])
                if store.update_permissions(provider_name, uid, perms):
                    permission_updates += 1
                    logger.info("Updated permissions for %s userId='%s': %s", provider_name, uid, perms)

    # 3. Parse health & activity push summaries and publish to Kafka
    payloads = provider.parse_webhook_payload(
        data=data,
        resolve_patient_id=lambda uid: store.resolve_patient_id(provider_name, uid),
        default_patient_id=default_patient_id,
    )

    published_batches = 0
    total_measurements = 0
    for payload in payloads:
        payload_dict = payload.model_dump(mode="json")
        if publisher.publish_payload(payload_dict):
            published_batches += 1
        total_measurements += (
            len(payload.measurements.instantaneous)
            + len(payload.measurements.cumulative)
            + len(payload.measurements.duration)
            + len(payload.measurements.waveforms)
        )

    logger.info(
        "Processed Push webhook from '%s' (keys=%s): %d batches (%d measurements) published to Kafka",
        provider_name,
        list(data.keys()),
        published_batches,
        total_measurements,
    )
    return {
        "status": "accepted",
        "provider": provider_name,
        "published_batches": published_batches,
        "total_measurements": total_measurements,
        "deregistered_users": deregistered_count,
        "permission_updates": permission_updates,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

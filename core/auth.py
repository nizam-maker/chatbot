# core/auth.py
# ─────────────────────────────────────────────────────────────
#  Auth dependencies — verify Supabase session tokens and
#  enforce tenant ownership / admin-only access on API routes
# ─────────────────────────────────────────────────────────────

from fastapi import Request, HTTPException


def get_current_profile(req: Request) -> dict:
    """
    Validate the caller's Supabase access token (Authorization: Bearer <jwt>)
    and return their profile row (role, tenant_id, is_approved, ...).
    Raises 401 if missing/invalid token, 403 if account not approved.
    """
    from core.supabase_client import sb

    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth_header[len("Bearer "):]

    try:
        user = sb.auth.get_user(token).user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    profile_res = sb.table("profiles").select("*") \
        .eq("id", user.id).maybe_single().execute()
    profile = profile_res.data if profile_res else None
    if not profile or not profile.get("is_approved"):
        raise HTTPException(status_code=403, detail="Account not approved")

    return profile


def require_tenant_access(tenant_id: str, req: Request) -> dict:
    """
    Dependency for /api/tenant/{tenant_id}/* routes.
    Allows admins (any tenant) or tenant users accessing their own tenant_id.
    """
    profile = get_current_profile(req)
    if profile.get("role") == "admin":
        return profile
    if profile.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    return profile


def require_admin(req: Request) -> dict:
    """Dependency for /api/admin/* routes — admin role required."""
    profile = get_current_profile(req)
    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return profile

"""Client Supabase (service role) untuk sync & API."""

from __future__ import annotations

from supabase import Client, create_client

from .config import Settings, get_settings

_client: Client | None = None
_client_key: tuple[str, str] | None = None


def get_supabase(settings: Settings | None = None) -> Client:
    global _client, _client_key
    cfg = settings or get_settings()
    if not cfg.supabase_configured:
        raise RuntimeError(
            "Supabase belum dikonfigurasi. Isi SUPABASE_URL dan "
            "SUPABASE_SERVICE_ROLE_KEY di backend/.env"
        )
    key = (cfg.supabase_url, cfg.supabase_service_role_key)
    if _client is None or _client_key != key:
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        _client_key = key
    return _client

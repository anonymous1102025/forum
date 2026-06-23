"""
account_manager.py
==================
Loads / saves the accounts.json registry.

Each account entry:
    slug                  – URL-safe identifier (e.g. "mysite")
    name                  – Display name (e.g. "My Forum")
    website               – Client website URL
    ga4_property_id       – GA4 property ID (numeric, e.g. "123456789")
    ga4_credentials_path  – Path to Google service account JSON key file
    db_path               – Path to the account's SQLite DB
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import settings

# accounts.json lives next to this file (backend/accounts.json).
# It is committed to git so Render always has it after deploy.
_ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"

REQUIRED_FIELDS = {"slug", "name", "ga4_property_id", "ga4_credentials_path"}


def _load() -> list[dict[str, Any]]:
    if not _ACCOUNTS_FILE.exists():
        return []
    with open(_ACCOUNTS_FILE, "r") as f:
        return json.load(f)


def _save(accounts: list[dict[str, Any]]) -> None:
    with open(_ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s or "account"


def list_accounts() -> list[dict[str, str]]:
    return [
        {"slug": a["slug"], "name": a["name"], "website": a.get("website", "")}
        for a in _load()
    ]


def get_account(slug: str) -> dict[str, Any] | None:
    for a in _load():
        if a["slug"] == slug:
            return a
    return None


def create_account(data: dict[str, Any]) -> dict[str, Any]:
    accounts = _load()

    if "slug" not in data or not data["slug"]:
        data["slug"] = _slugify(data.get("name", "account"))

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")

    if any(a["slug"] == data["slug"] for a in accounts):
        raise ValueError(f"Account with slug '{data['slug']}' already exists")

    data.setdefault("website", "")
    data.setdefault("db_path", f"data/{data['slug']}.db")

    Path(data["db_path"]).parent.mkdir(parents=True, exist_ok=True)

    accounts.append(data)
    _save(accounts)
    return data


def update_account(slug: str, updates: dict[str, Any]) -> dict[str, Any]:
    accounts = _load()
    for i, a in enumerate(accounts):
        if a["slug"] == slug:
            updates.pop("slug", None)
            accounts[i] = {**a, **updates}
            _save(accounts)
            return accounts[i]
    raise ValueError(f"Account '{slug}' not found")


def delete_account(slug: str) -> None:
    accounts = _load()
    filtered = [a for a in accounts if a["slug"] != slug]
    if len(filtered) == len(accounts):
        raise ValueError(f"Account '{slug}' not found")
    _save(filtered)


def get_credentials(account: dict[str, Any]) -> dict[str, str]:
    # GA4_CREDENTIALS_PATH env var overrides the path stored in accounts.json.
    # Set it on Render to point to the Secret File; leave empty for local dev.
    creds_path = settings.ga4_credentials_path.strip() or account["ga4_credentials_path"]
    return {
        "property_id":      account["ga4_property_id"],
        "credentials_path": creds_path,
    }


def bootstrap_from_env() -> None:
    """If accounts.json doesn't exist and GA4 env vars are set, create it.
    Only runs on a fresh Render deploy before accounts.json is committed."""
    if _ACCOUNTS_FILE.exists():
        return
    pid  = settings.ga4_property_id.strip()
    name = settings.ga4_account_name.strip() or "Default"
    cred = settings.ga4_credentials_path.strip()
    if not pid or not cred:
        return
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "default"
    account = {
        "slug":                 slug,
        "name":                 name,
        "website":              "",
        "ga4_property_id":      pid,
        "ga4_credentials_path": cred,
        "db_path":              f"data/{slug}.db",
    }
    _save([account])

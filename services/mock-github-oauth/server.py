from __future__ import annotations

import json
import os
import re
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

CODE_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 3600
DEFAULT_BASE_URL = "http://mock-github-oauth:8080"


def _load_seed_users() -> dict[str, dict[str, object]]:
    path = Path(os.getenv("SEED_USERS_FILE", "/config/seed-users.json"))
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    users: dict[str, dict[str, object]] = {}
    for item in payload:
        seed = dict(item)
        users[str(seed["key"])] = seed
    return users


def _resolve_seed(login: str) -> dict[str, object] | None:
    seed = SEED_USERS.get(login)
    if seed is not None:
        return seed
    for item in SEED_USERS.values():
        if str(item.get("login", "")) == login:
            return item
    if _DYNAMIC_LOGIN_RE.fullmatch(login):
        normalized = login.lower()
        user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"mock-github-oauth:{normalized}")
        return {
            "key": login,
            "id": user_uuid.int % 2_000_000_000,
            "login": normalized,
            "email": f"{normalized}@e2e.test",
            "teams": [],
            "org_memberships": {},
        }
    return None


SEED_USERS = _load_seed_users()
CODES: dict[str, dict[str, object]] = {}
ACCESS_TOKENS: dict[str, dict[str, object]] = {}
BASE_URL = os.getenv("MOCK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
_DYNAMIC_LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


def _cleanup_store(store: dict[str, dict[str, object]]) -> None:
    now = time.time()
    expired = [key for key, value in store.items() if float(value.get("expires_at", 0)) <= now]
    for key in expired:
        store.pop(key, None)


def _json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _body(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _access_token(handler: BaseHTTPRequestHandler) -> str | None:
    header = handler.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header.split(" ", 1)[1].strip() or None
    if header.startswith("token "):
        return header.split(" ", 1)[1].strip() or None
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "mock-github-oauth/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[mock-github-oauth] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        _cleanup_store(CODES)
        _cleanup_store(ACCESS_TOKENS)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if parsed.path == "/health":
            return _json(self, HTTPStatus.OK, {"status": "ok"})

        if parsed.path == "/login/oauth/authorize":
            login = query.get("login", [""])[-1]
            redirect_uri = query.get("redirect_uri", [""])[-1]
            state = query.get("state", [""])[-1]
            seed = _resolve_seed(login)
            if seed is None:
                return _json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_login"})
            code = uuid.uuid4().hex
            CODES[code] = {"seed_key": str(seed["key"]), "expires_at": time.time() + CODE_TTL_SECONDS}
            separator = '&' if '?' in redirect_uri else '?'
            location = f"{redirect_uri}{separator}{urlencode({'code': code, 'state': state})}"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            self.end_headers()
            return

        access_token = _access_token(self)
        if parsed.path == "/user":
            payload = ACCESS_TOKENS.get(access_token or "")
            if payload is None:
                return _json(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            seed = SEED_USERS[str(payload["seed_key"])]
            return _json(
                self,
                HTTPStatus.OK,
                {
                    "id": seed["id"],
                    "login": seed["login"],
                    "email": seed["email"],
                    "name": str(seed["email"]).split("@", 1)[0].replace(".", " ").title(),
                    "avatar_url": f"{BASE_URL}/avatars/{seed['id']}.png",
                },
            )

        if parsed.path == "/user/emails":
            payload = ACCESS_TOKENS.get(access_token or "")
            if payload is None:
                return _json(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            seed = SEED_USERS[str(payload["seed_key"])]
            return _json(
                self,
                HTTPStatus.OK,
                [
                    {
                        "email": seed["email"],
                        "primary": True,
                        "verified": True,
                        "visibility": "public",
                    }
                ],
            )

        if parsed.path == "/user/teams":
            payload = ACCESS_TOKENS.get(access_token or "")
            if payload is None:
                return _json(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            seed = SEED_USERS[str(payload["seed_key"])]
            teams = []
            for team in seed.get("teams", []) or []:
                if isinstance(team, dict):
                    teams.append(team)
            return _json(self, HTTPStatus.OK, teams)

        if parsed.path.startswith("/user/memberships/orgs/"):
            payload = ACCESS_TOKENS.get(access_token or "")
            if payload is None:
                return _json(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            org = parsed.path.rsplit("/", 1)[-1]
            seed = SEED_USERS[str(payload["seed_key"])]
            orgs = set(seed.get("orgs", []) or [])
            if org not in orgs:
                return _json(self, HTTPStatus.NOT_FOUND, {"message": "Not Found"})
            return _json(self, HTTPStatus.OK, {"state": "active"})

        if parsed.path.startswith("/avatars/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        return _json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        _cleanup_store(CODES)
        _cleanup_store(ACCESS_TOKENS)
        parsed = urlparse(self.path)
        if parsed.path != "/login/oauth/access_token":
            return _json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
        form = _body(self)
        code = form.get("code", "")
        payload = CODES.pop(code, None)
        if payload is None:
            return _json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_grant"})
        access_token = f"gho_mock_{uuid.uuid4().hex}"
        ACCESS_TOKENS[access_token] = {"seed_key": payload["seed_key"], "expires_at": time.time() + TOKEN_TTL_SECONDS}
        return _json(
            self,
            HTTPStatus.OK,
            {
                "access_token": access_token,
                "token_type": "bearer",
                "scope": "read:user user:email",
            },
        )


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()

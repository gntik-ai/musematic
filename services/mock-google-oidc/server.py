from __future__ import annotations

import json
import os
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

CODE_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 3600
DEFAULT_ISSUER = "http://mock-google-oidc:8080"


def _load_seed_users() -> dict[str, dict[str, object]]:
    path = Path(os.getenv("SEED_USERS_FILE", "/config/seed-users.json"))
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    users: dict[str, dict[str, object]] = {}
    for item in payload:
        key = str(item["key"])
        users[key] = dict(item)
    return users


SEED_USERS = _load_seed_users()
CODES: dict[str, dict[str, object]] = {}
ACCESS_TOKENS: dict[str, dict[str, object]] = {}
ID_TOKENS: dict[str, dict[str, object]] = {}
ISSUER = os.getenv("MOCK_ISSUER", DEFAULT_ISSUER).rstrip("/")


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


def _bearer_token(handler: BaseHTTPRequestHandler) -> str | None:
    header = handler.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


class Handler(BaseHTTPRequestHandler):
    server_version = "mock-google-oidc/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[mock-google-oidc] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        _cleanup_store(CODES)
        _cleanup_store(ACCESS_TOKENS)
        _cleanup_store(ID_TOKENS)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if parsed.path == "/health":
            return _json(self, HTTPStatus.OK, {"status": "ok"})

        if parsed.path == "/authorize":
            login_hint = query.get("login_hint", [""])[-1]
            redirect_uri = query.get("redirect_uri", [""])[-1]
            state = query.get("state", [""])[-1]
            client_id = query.get("client_id", [""])[-1]
            nonce = query.get("nonce", [""])[-1]
            seed = SEED_USERS.get(login_hint)
            if seed is None:
                return _json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_login_hint"})
            code = uuid.uuid4().hex
            CODES[code] = {
                "seed_key": login_hint,
                "client_id": client_id,
                "nonce": nonce,
                "expires_at": time.time() + CODE_TTL_SECONDS,
            }
            location = redirect_uri
            separator = '&' if '?' in redirect_uri else '?'
            location = f"{location}{separator}{urlencode({'code': code, 'state': state})}"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            self.end_headers()
            return

        if parsed.path == "/tokeninfo":
            token = query.get("id_token", [""])[-1]
            payload = ID_TOKENS.get(token)
            if payload is None:
                return _json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_token"})
            seed = SEED_USERS[str(payload["seed_key"])]
            return _json(
                self,
                HTTPStatus.OK,
                {
                    "iss": ISSUER,
                    "aud": payload["client_id"],
                    "sub": seed["sub"],
                    "email": seed["email"],
                    "email_verified": seed.get("email_verified", True),
                    "name": str(seed["email"]).split("@", 1)[0].replace(".", " ").title(),
                    "picture": f"{ISSUER}/avatars/{seed['sub']}.png",
                    "nonce": payload["nonce"],
                },
            )

        if parsed.path == "/userinfo":
            access_token = _bearer_token(self)
            payload = ACCESS_TOKENS.get(access_token or "")
            if payload is None:
                return _json(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            seed = SEED_USERS[str(payload["seed_key"])]
            return _json(
                self,
                HTTPStatus.OK,
                {
                    "sub": seed["sub"],
                    "email": seed["email"],
                    "email_verified": seed.get("email_verified", True),
                    "name": str(seed["email"]).split("@", 1)[0].replace(".", " ").title(),
                    "picture": f"{ISSUER}/avatars/{seed['sub']}.png",
                },
            )

        if parsed.path == "/.well-known/openid-configuration":
            return _json(
                self,
                HTTPStatus.OK,
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "userinfo_endpoint": f"{ISSUER}/userinfo",
                    "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
                },
            )

        if parsed.path == "/.well-known/jwks.json":
            return _json(self, HTTPStatus.OK, {"keys": []})

        if parsed.path.startswith("/avatars/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        return _json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        _cleanup_store(CODES)
        _cleanup_store(ACCESS_TOKENS)
        _cleanup_store(ID_TOKENS)
        parsed = urlparse(self.path)
        if parsed.path != "/token":
            return _json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
        form = _body(self)
        code = form.get("code", "")
        payload = CODES.pop(code, None)
        if payload is None:
            return _json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_grant"})
        access_token = f"mock-oidc-access-{uuid.uuid4().hex}"
        id_token = f"mock-oidc-id-{uuid.uuid4().hex}"
        ACCESS_TOKENS[access_token] = {
            "seed_key": payload["seed_key"],
            "client_id": payload["client_id"],
            "nonce": payload["nonce"],
            "expires_at": time.time() + TOKEN_TTL_SECONDS,
        }
        ID_TOKENS[id_token] = {
            "seed_key": payload["seed_key"],
            "client_id": payload["client_id"],
            "nonce": payload["nonce"],
            "expires_at": time.time() + TOKEN_TTL_SECONDS,
        }
        return _json(
            self,
            HTTPStatus.OK,
            {
                "access_token": access_token,
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": TOKEN_TTL_SECONDS,
                "scope": "openid email profile",
            },
        )


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()

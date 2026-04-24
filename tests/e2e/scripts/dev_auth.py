#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import uuid
from http import HTTPStatus
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_DEFAULT_SECRET = 'change-me'
_DEFAULT_ALGORITHM = 'HS256'


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode('ascii'))


def _normalize_roles(role_names: list[str], workspace_id: str | None = None) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for role_name in role_names:
        key = (role_name, workspace_id)
        if key in seen:
            continue
        normalized.append({'role': role_name, 'workspace_id': workspace_id})
        seen.add(key)
    return normalized


def _jwt_encode(payload: dict[str, Any], secret: str, algorithm: str) -> str:
    if algorithm != _DEFAULT_ALGORITHM:
        raise SystemExit(f'unsupported algorithm: {algorithm}')
    header = {'alg': algorithm, 'typ': 'JWT'}
    signing_input = '.'.join(
        (
            _b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8')),
            _b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')),
        )
    )
    signature = hmac.new(secret.encode('utf-8'), signing_input.encode('ascii'), hashlib.sha256).digest()
    return f'{signing_input}.{_b64url_encode(signature)}'


def _jwt_decode(token: str) -> dict[str, Any]:
    parts = token.split('.')
    if len(parts) != 3:
        raise SystemExit('invalid JWT')
    return json.loads(_b64url_decode(parts[1]).decode('utf-8'))


def _persona_user_id(persona: str, email: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f'journey-persona:{persona}:{email}'))


def _mint_access_token(
    *,
    user_id: str,
    email: str,
    role_names: list[str],
    workspace_id: str | None = None,
    secret: str = _DEFAULT_SECRET,
    algorithm: str = _DEFAULT_ALGORITHM,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        'sub': user_id,
        'email': email,
        'roles': _normalize_roles(role_names, workspace_id=workspace_id),
        'session_id': str(uuid.uuid4()),
        'iat': now,
        'exp': now + 8 * 60 * 60,
        'type': 'access',
        'identity_type': 'user',
    }
    if workspace_id is not None:
        payload['workspace_id'] = workspace_id
    return _jwt_encode(payload, secret=secret, algorithm=algorithm)


def _read_response(url: str, *, method: str = 'GET', payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> tuple[int, dict[str, str], str]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        request_headers.setdefault('Content-Type', 'application/json')
    request = Request(url, data=data, headers=request_headers, method=method)
    opener = build_opener() if follow_redirects else build_opener(_NoRedirectHandler())
    try:
        with opener.open(request) as response:
            body = response.read().decode('utf-8')
            return response.status, dict(response.headers.items()), body
    except HTTPError as exc:
        body = exc.read().decode('utf-8')
        return exc.code, dict(exc.headers.items()), body


def _json_request(url: str, *, method: str = 'GET', payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    status, _, body = _read_response(url, method=method, payload=payload, headers=headers)
    if status >= HTTPStatus.BAD_REQUEST:
        raise SystemExit(f'{method} {url} failed with {status}: {body}')
    return json.loads(body) if body else {}


def _oauth_provider_payload(provider: str, api_base: str) -> dict[str, Any]:
    api_base = api_base.rstrip('/')
    if provider == 'google':
        return {
            'display_name': 'Mock Google',
            'enabled': True,
            'client_id': 'mock-google-client-id',
            'client_secret_ref': 'plain:mock-google-client-secret',
            'redirect_uri': f'{api_base}/api/v1/auth/oauth/google/callback',
            'scopes': ['openid', 'email', 'profile'],
            'domain_restrictions': [],
            'org_restrictions': [],
            'group_role_mapping': {},
            'default_role': 'workspace_member',
            'require_mfa': False,
        }
    if provider == 'github':
        return {
            'display_name': 'Mock GitHub',
            'enabled': True,
            'client_id': 'mock-github-client-id',
            'client_secret_ref': 'plain:mock-github-client-secret',
            'redirect_uri': f'{api_base}/api/v1/auth/oauth/github/callback',
            'scopes': ['read:user', 'user:email'],
            'domain_restrictions': [],
            'org_restrictions': [],
            'group_role_mapping': {},
            'default_role': 'workspace_admin',
            'require_mfa': False,
        }
    raise SystemExit(f'unsupported provider: {provider}')


def _mock_authorize_url(provider: str, mock_server: str, redirect_url: str, login: str) -> str:
    parsed = urlparse(redirect_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if provider == 'google':
        query['login_hint'] = [login]
        path = '/authorize'
    else:
        query['login'] = [login]
        path = '/login/oauth/authorize'
    target = urlparse(mock_server)
    return urlunparse((target.scheme, target.netloc, path, '', urlencode(query, doseq=True), ''))


def _decode_oauth_session_payload(redirect_location: str) -> dict[str, Any]:
    fragment = redirect_location.split('#oauth_session=', 1)
    if len(fragment) != 2:
        raise SystemExit('callback did not return an oauth_session fragment')
    return json.loads(_b64url_decode(fragment[1]).decode('utf-8'))


def cmd_mint(args: argparse.Namespace) -> int:
    user_id = args.user_id or _persona_user_id(args.persona, args.email)
    token = _mint_access_token(
        user_id=user_id,
        email=args.email,
        role_names=list(args.role),
        workspace_id=args.workspace_id,
        secret=args.secret,
        algorithm=args.algorithm,
    )
    if args.json:
        print(json.dumps({'access_token': token, 'sub': user_id, 'email': args.email, 'roles': list(args.role)}, indent=2))
    else:
        print(token)
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    payload = _jwt_decode(args.token)
    if args.field:
        value = payload
        for item in args.field.split('.'):
            if not isinstance(value, dict) or item not in value:
                raise SystemExit(f'field not found: {args.field}')
            value = value[item]
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2))
        else:
            print(value)
        return 0
    print(json.dumps(payload, indent=2))
    return 0


def cmd_bootstrap_providers(args: argparse.Namespace) -> int:
    admin_token = args.admin_token or _mint_access_token(
        user_id=_persona_user_id('admin', args.admin_email),
        email=args.admin_email,
        role_names=['platform_admin'],
        secret=args.secret,
        algorithm=args.algorithm,
    )
    headers = {'Authorization': f'Bearer {admin_token}'}
    for provider in ('google', 'github'):
        _json_request(
            f"{args.api_base.rstrip('/')}/api/v1/admin/oauth/providers/{provider}",
            method='PUT',
            payload=_oauth_provider_payload(provider, args.api_base),
            headers=headers,
        )
    providers = _json_request(f"{args.api_base.rstrip('/')}/api/v1/auth/oauth/providers")
    print(json.dumps(providers, indent=2))
    return 0


def cmd_oauth(args: argparse.Namespace) -> int:
    api_base = args.api_base.rstrip('/')
    if args.bootstrap_providers:
        bootstrap_args = argparse.Namespace(
            api_base=api_base,
            admin_email=args.admin_email,
            admin_token=args.admin_token,
            secret=args.secret,
            algorithm=args.algorithm,
        )
        cmd_bootstrap_providers(bootstrap_args)
    authorize = _json_request(f'{api_base}/api/v1/auth/oauth/{args.provider}/authorize')
    redirect_url = str(authorize['redirect_url'])
    mock_authorize = _mock_authorize_url(args.provider, args.mock_base.rstrip('/'), redirect_url, args.login)

    status, headers, body = _read_response(mock_authorize, follow_redirects=False)
    if status not in _REDIRECT_STATUSES and status >= HTTPStatus.BAD_REQUEST:
        raise SystemExit(f'mock authorize failed with {status}: {body}')
    callback_url = headers.get('Location') or headers.get('location')
    if not callback_url:
        raise SystemExit('mock authorize response missing redirect location')

    status, headers, body = _read_response(callback_url, follow_redirects=False)
    if status not in _REDIRECT_STATUSES and status >= HTTPStatus.BAD_REQUEST:
        raise SystemExit(f'callback failed with {status}: {body}')
    redirect_location = headers.get('Location') or headers.get('location')
    if not redirect_location:
        raise SystemExit('callback response missing redirect location')

    payload = _decode_oauth_session_payload(redirect_location)
    token_pair = payload.get('token_pair')
    if isinstance(token_pair, dict):
        access_token = token_pair.get('access_token')
    else:
        access_token = payload.get('access_token')
    if not isinstance(access_token, str) or not access_token:
        raise SystemExit('callback did not include an access token')

    if args.json:
        output = dict(payload)
        output['claims'] = _jwt_decode(access_token)
        print(json.dumps(output, indent=2))
    else:
        print(access_token)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Local auth helpers for the dev/e2e harness.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    mint = subparsers.add_parser('mint', help='Mint a local HS256 access token.')
    mint.add_argument('--persona', default='admin')
    mint.add_argument('--email', required=True)
    mint.add_argument('--user-id')
    mint.add_argument('--role', action='append', required=True)
    mint.add_argument('--workspace-id')
    mint.add_argument('--secret', default=_DEFAULT_SECRET)
    mint.add_argument('--algorithm', default=_DEFAULT_ALGORITHM)
    mint.add_argument('--json', action='store_true')
    mint.set_defaults(func=cmd_mint)

    decode = subparsers.add_parser('decode', help='Decode a JWT without verifying the signature.')
    decode.add_argument('--token', required=True)
    decode.add_argument('--field')
    decode.set_defaults(func=cmd_decode)

    bootstrap = subparsers.add_parser('bootstrap-providers', help='Configure the mock Google and GitHub OAuth providers.')
    bootstrap.add_argument('--api-base', default='http://localhost:8081')
    bootstrap.add_argument('--admin-email', default='j-admin@e2e.test')
    bootstrap.add_argument('--admin-token')
    bootstrap.add_argument('--secret', default=_DEFAULT_SECRET)
    bootstrap.add_argument('--algorithm', default=_DEFAULT_ALGORITHM)
    bootstrap.set_defaults(func=cmd_bootstrap_providers)

    oauth = subparsers.add_parser('oauth', help='Execute the mock OAuth login flow and print an access token.')
    oauth.add_argument('--provider', choices=('google', 'github'), required=True)
    oauth.add_argument('--login', required=True)
    oauth.add_argument('--api-base', default='http://localhost:8081')
    oauth.add_argument('--mock-base', required=True)
    oauth.add_argument('--bootstrap-providers', action='store_true')
    oauth.add_argument('--admin-email', default='j-admin@e2e.test')
    oauth.add_argument('--admin-token')
    oauth.add_argument('--secret', default=_DEFAULT_SECRET)
    oauth.add_argument('--algorithm', default=_DEFAULT_ALGORITHM)
    oauth.add_argument('--json', action='store_true')
    oauth.set_defaults(func=cmd_oauth)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main())

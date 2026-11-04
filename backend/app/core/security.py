"""Signature verification via trusted project JWKS; never trust decoded-only claims."""
from dataclasses import dataclass, field
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    user_id: str
    token: str = field(repr=False)


def verify_token(token: str, issuer: str, jwks) -> Identity:
    if len(token) > 8192:
        raise jwt.InvalidTokenError('Token too large')
    header = jwt.get_unverified_header(token)
    if header.get('alg') not in ('RS256', 'ES256') or not header.get('kid'):
        raise jwt.InvalidTokenError('Unsupported signing algorithm or missing key ID')
    key = jwks.get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=['RS256', 'ES256'],
                        audience='authenticated', issuer=issuer,
                        options={'require': ['exp', 'iat', 'sub', 'iss', 'aud', 'role']})
    if claims['role'] != 'authenticated' or claims.get('is_anonymous', False):
        raise jwt.InvalidTokenError('A registered authenticated account is required')
    try:
        user_id = str(UUID(claims['sub']))
    except (ValueError, TypeError, AttributeError) as error:
        raise jwt.InvalidTokenError('Invalid subject') from error
    return Identity(user_id, token)


def require_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Identity:
    settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_publishable_key.get_secret_value():
        raise HTTPException(503, 'Supabase setup required')
    if not credentials:
        raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})
    try:
        return verify_token(credentials.credentials, settings.supabase_url + '/auth/v1', request.app.state.jwks)
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, 'Authentication key service unavailable') from None
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, 'Invalid or expired access token', headers={'WWW-Authenticate': 'Bearer'}) from None

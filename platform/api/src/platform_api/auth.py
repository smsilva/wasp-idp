"""Keycloak JWT validation (ADR 0021).

Tokens are signed by the realm key, fetched from the JWKS through the in-cluster URL, while `iss`
must equal the public issuer (KC_HOSTNAME): the CLI gets its tokens through localhost:8180.
"""
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request

AUDIENCE = "platform-api"


@dataclass(frozen=True)
class Principal:
  sub: str
  email: str | None
  groups: list[str] = field(default_factory=list)

  @property
  def actor(self) -> str:
    """Journal author: the immutable subject, with the e-mail for humans reading it."""
    return f"{self.sub} ({self.email})" if self.email else self.sub


class Verifier:
  def __init__(self, issuer: str, jwks_url: str, audience: str = AUDIENCE, key_source=None):
    self.issuer = issuer
    self.audience = audience
    # PyJWKClient caches the keys and refetches on an unknown `kid` (key rotation).
    self.keys = key_source or jwt.PyJWKClient(jwks_url, cache_keys=True)

  def verify(self, token: str) -> Principal:
    try:
      key = self.keys.get_signing_key_from_jwt(token).key
      claims = jwt.decode(
        token, key,
        algorithms=["RS256"],
        audience=self.audience,
        issuer=self.issuer,
        options={"require": ["exp", "iss", "aud", "sub"]},
      )
    except (jwt.PyJWTError, jwt.PyJWKClientError) as error:
      raise Unauthorized(str(error)) from error
    return Principal(sub=claims["sub"], email=claims.get("email"), groups=list(claims.get("groups", [])))


class Unauthorized(Exception):
  pass


def current_principal(request: Request) -> Principal:
  header = request.headers.get("authorization", "")
  scheme, _, token = header.partition(" ")
  if scheme.lower() != "bearer" or not token:
    raise HTTPException(401, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
  try:
    return request.app.state.verifier.verify(token)
  except Unauthorized:
    # The reason (expired, wrong audience…) stays out of the response: it only helps an attacker.
    raise HTTPException(401, "invalid token", headers={"WWW-Authenticate": "Bearer"})


def require_group(group: str):
  def check(principal: Principal = Depends(current_principal)) -> Principal:
    if group not in principal.groups:
      raise HTTPException(403, f"requires group '{group}'")
    return principal

  return check

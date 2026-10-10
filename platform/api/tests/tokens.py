"""Signs test tokens with a throwaway RSA key, the way Keycloak signs them, so no Keycloak is needed."""
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_api.auth import AUDIENCE, Verifier

ISSUER = "http://localhost:8180/realms/platform"


class _StaticKeys:
  def __init__(self, public_key):
    self.public_key = public_key

  def get_signing_key_from_jwt(self, token):
    return type("SigningKey", (), {"key": self.public_key})()


class TokenFactory:
  def __init__(self):
    self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

  def verifier(self) -> Verifier:
    return Verifier(issuer=ISSUER, jwks_url="unused", key_source=_StaticKeys(self.key.public_key()))

  def issue(self, key=None, **overrides) -> str:
    now = int(time.time())
    claims = {
      "iss": ISSUER, "aud": [AUDIENCE, "account"], "sub": "user-1", "email": "dev@example.com",
      "groups": ["platform-users"], "iat": now, "exp": now + 300,
    }
    claims.update(overrides)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key or self.key, algorithm="RS256")

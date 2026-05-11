# Contract: jwt.exceptions

## Exception Hierarchy

```
PyJWTError
├── InvalidTokenError
│   ├── DecodeError
│   │   └── InvalidSignatureError
│   ├── ExpiredSignatureError
│   ├── InvalidAudienceError
│   ├── InvalidIssuerError
│   ├── InvalidIssuedAtError
│   ├── ImmatureSignatureError
│   ├── InvalidAlgorithmError
│   └── MissingRequiredClaimError
├── InvalidKeyError
├── PyJWKError
│   └── MissingCryptographyError
├── PyJWKSetError
└── PyJWKClientError
    └── PyJWKClientConnectionError
```

### `MissingRequiredClaimError(InvalidTokenError)`
Constructor: `__init__(self, claim: str)`. Stores `self.claim`. `__str__` returns `'Token is missing the "<claim>" claim'`.

All other exceptions have standard `Exception` behavior with no custom `__init__`.

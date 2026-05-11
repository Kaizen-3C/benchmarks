from typing import Any, Dict

JWKDict = Dict[str, Any]

try:
    from typing import Protocol

    class HashlibHash(Protocol):
        def __call__(self, *args, **kwargs) -> Any:
            ...
except ImportError:
    HashlibHash = Any  # type: ignore

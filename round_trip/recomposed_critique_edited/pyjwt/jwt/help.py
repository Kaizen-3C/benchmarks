import json
import platform
import sys
from typing import Dict

from . import __version__ as pyjwt_version


def info() -> Dict:
    """
    Returns information about the environment for debugging.
    """
    try:
        import cryptography
        cryptography_version = cryptography.__version__
    except ImportError:
        cryptography_version = ""

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
        },
        "implementation": {
            "name": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "cryptography": {
            "version": cryptography_version,
        },
        "pyjwt": {
            "version": pyjwt_version,
        },
    }


def main() -> None:
    print(json.dumps(info(), indent=2))


if __name__ == "__main__":
    main()

import json
import platform
import struct
import sys

from . import __version__ as pyjwt_version


def info():
    """
    Generate information for a bug report.
    Based on the requests package help module.
    """
    try:
        platform_info = {
            "system": platform.system(),
            "release": platform.release(),
        }
    except OSError:
        platform_info = {"system": "Unknown", "release": "Unknown"}

    implementation = platform.python_implementation()
    implementation_version = platform.python_version()

    try:
        from cryptography import __version__ as cryptography_version
    except ImportError:
        cryptography_version = ""

    return {
        "platform": platform_info,
        "implementation": {"name": implementation, "version": implementation_version},
        "cryptography": {"version": cryptography_version},
        "pyjwt": {"version": pyjwt_version},
    }


def main():
    print(json.dumps(info(), indent=2))


if __name__ == "__main__":
    main()

"""Entrypoint for `python src/encrypt_tokens.py`.

Encrypts tokens that were stored before TOKEN_ENCRYPTION_KEY was set. Run it
once, after every pod has the key. See src/core/token_crypto.py.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.token_crypto import encrypt_stored_tokens  # noqa: E402

if __name__ == "__main__":
    print(f"[encrypt-tokens] Encrypted {encrypt_stored_tokens()} row(s).")

#!/usr/bin/env python3
"""One-token call to the Anthropic API so a billing or key failure is named instead of mysterious.

On Oct 4 and Oct 11, 2026 the weekly job died because the credit balance ran out. In the Actions log
that looked like a generic failure; the real message ("Credit balance is too low") was hidden unless
show_full_output was on. This check costs a fraction of a cent and says what is wrong.

Exit codes: 0 ok (or transient, let the job try), 3 credit balance too low, 4 key rejected.
Prints reason=<ok|billing|auth|transient> for $GITHUB_OUTPUT.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("PREFLIGHT_MODEL", "claude-sonnet-5")
    if not key:
        print("reason=auth")
        print("message=ANTHROPIC_API_KEY is not set for this workflow.")
        return 4
    body = json.dumps({"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print("reason=ok")
        return 0
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:400]
        if e.code == 400 and "credit balance" in text.lower():
            print("reason=billing")
            print("message=The Anthropic API credit balance is too low. Top up at https://console.anthropic.com (Billing); runs resume as soon as it is funded.")
            return 3
        if e.code in (401, 403):
            print("reason=auth")
            print(f"message=The Anthropic API rejected the key (HTTP {e.code}). Check the ANTHROPIC_API_KEY repository secret.")
            return 4
        print("reason=transient")
        print(f"message=Anthropic API answered HTTP {e.code}: {text[:160]}")
        return 0
    except Exception as e:  # noqa: BLE001  (network trouble should not block a run that may still work)
        print("reason=transient")
        print(f"message=Could not reach the Anthropic API: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

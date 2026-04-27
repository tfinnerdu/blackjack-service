"""Health endpoint. Render hits this; the Doane standard requires it too."""
from __future__ import annotations

import time

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)

_BOOT_TS = time.time()


@bp.route("/health")
def health():
    return jsonify(
        status="ok",
        service="blackjack-service",
        version="0.1.0",
        uptime_seconds=int(time.time() - _BOOT_TS),
    )

"""Standup HTTP API that lives in the module rather than in core.

Most standup endpoints are still served by core/dashboard.py, a debt the
import ratchet in tests/test_main_wiring.py tracks. New ones start here.

Blueprint is built inside register_routes so importing the registry does not
pull core's dashboard in as a side effect.
"""

from __future__ import annotations

from src.core.api_schemas import boolean, model

AiSummaryStatus = model("AiSummaryStatus", configured=boolean())


def register_routes(flask_app) -> None:
    from flask_smorest import Blueprint

    from src.core.api import api_errors, register_api_blueprint
    from src.core.dashboard import _login_required
    from src.modules.standup import ai_summary

    bp = Blueprint("standup", __name__)

    @bp.route("/dashboard/api/ai-summary", methods=["GET"])
    @_login_required
    @bp.doc(operationId="getAiSummary", tags=["Standups"], security=[{"sessionCookie": []}])
    @api_errors(bp)
    @bp.response(200, AiSummaryStatus)
    def ai_summary_status():
        """Whether this deployment has an AI provider key.

        Without one the standup form hides the AI summary switch, the same way
        the Connect page says when Zoom is not set up here.
        """
        return {"configured": ai_summary.configured()}

    register_api_blueprint(flask_app, bp)

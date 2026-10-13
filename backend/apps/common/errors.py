import logging

from django.http import JsonResponse
from django.core.exceptions import RequestDataTooBig
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class CodedError(APIException):
    def __init__(self, code, message, status=400):
        self.status_code = status
        super().__init__({"code": code, "message": message})


def exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        from rest_framework.response import Response
        return Response({"error": {"code": "payload_too_large", "message": "The request exceeds the supported size."}}, status=413)
    from rest_framework.views import exception_handler as drf_exception_handler
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        from rest_framework.response import Response
        return Response({"error": {"code": "server_error", "message": "Unable to complete this request."}}, status=500)
    if isinstance(exc, CodedError):
        response.data = {"error": response.data}
    else:
        code = getattr(exc, "default_code", "request_error")
        response.data = {"error": {"code": code, "message": "Please check the request and try again.", "details": response.data}}
    return response


def csrf_failure(request, reason=""):
    return JsonResponse({"error": {"code": "csrf_failed", "message": "Please refresh the page and try again."}}, status=403)

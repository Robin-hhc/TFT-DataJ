"""Local failure diagnostics without exception messages, headers or credentials."""
from copy import deepcopy
import hashlib
import math
import time

import httpx


def source_failure_details(error, adapter, *, scope, request):
    chain = []
    seen = set()
    cause = error
    while cause is not None and id(cause) not in seen and len(chain) < 8:
        seen.add(id(cause))
        chain.append(cause)
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    source = getattr(adapter, 'adapter', adapter)
    if hasattr(source, 'lock'):
        with source.lock:
            remaining = max(0.0, source.next_request - time.monotonic())
            origin = deepcopy(getattr(getattr(source, 'budget', None), 'last_failure', None))
    else:
        remaining = 0.0
        origin = None
    status_error = next((item for item in chain if isinstance(item, httpx.HTTPStatusError)), None)
    if any(isinstance(item, httpx.TimeoutException) for item in chain):
        reason = 'timeout'
    elif status_error is not None:
        reason = 'http_error'
    elif any(isinstance(item, httpx.NetworkError) for item in chain):
        reason = 'network_error'
    elif any(getattr(item, 'reason', None) == 'source_cooldown' for item in chain):
        reason = 'source_cooldown'
    else:
        reason = 'invalid_response'
    details = {'reason': reason, 'exception_types': [type(item).__name__ for item in chain],
               'retry_after_seconds': math.ceil(remaining),
               'scope': deepcopy(scope),
               'request': deepcopy(getattr(error, 'request_details', request))}
    if status_error is not None:
        response = status_error.response
        details.update(http_status=response.status_code,
                       response_bytes=len(response.content),
                       response_sha256=hashlib.sha256(response.content).hexdigest())
    if reason == 'source_cooldown' and origin is not None:
        details['cooldown_origin'] = origin
    return details

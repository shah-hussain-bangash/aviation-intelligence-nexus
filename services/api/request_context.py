"""Server-generated request correlation and allowlisted, best-effort local telemetry."""
import json
import logging
import time
from datetime import datetime,timezone
from uuid import uuid4
from fastapi.responses import JSONResponse

LOGGER=logging.getLogger('ain.requests')


def install_request_context(app):
    @app.middleware('http')
    async def request_context(request,call_next):
        if not request.url.path.startswith('/api/v1/'):
            return await call_next(request)
        request_id=str(uuid4());request.state.request_id=request_id;started=time.monotonic()
        outcome='response'
        try:
            response=await call_next(request)
        except Exception:
            # Never serialize exception text, stack, request values or credentials.
            outcome='unhandled_exception'
            response=JSONResponse(status_code=500,content={'error':'internal_error','request_id':request_id})
        response.headers['X-Request-ID']=request_id
        response.headers['Cache-Control']='no-store'
        route=request.scope.get('route')
        template=getattr(route,'path',None) if route in app.routes else None
        template=template if isinstance(template,str) and template.startswith('/api/v1/') else 'unresolved_api_route'
        method=request.method if request.method in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS') else 'OTHER'
        record={'event':'api_response_prepared','timestamp':datetime.now(timezone.utc).isoformat(),
            'request_id':request_id,'method':method,'route':template,'status':response.status_code,
            'response_prepare_ms':round(max(0,time.monotonic()-started)*1000,3),'outcome':outcome}
        try:LOGGER.info(json.dumps(record,separators=(',',':')))
        except Exception:
            # Optional telemetry is not a protected audit; sink failures must not break research requests.
            pass
        return response

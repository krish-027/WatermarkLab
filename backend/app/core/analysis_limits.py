"""Bound raw analysis bodies including chunked requests before JSON parsing."""
from starlette.responses import JSONResponse

class AnalysisBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] not in ('/api/v1/analyze','/api/v1/transform','/api/v1/compare','/api/v1/robustness/runs'):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > 131072:
                return await JSONResponse({'detail': 'Analysis request exceeds the 128 KiB limit'}, status_code=413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)

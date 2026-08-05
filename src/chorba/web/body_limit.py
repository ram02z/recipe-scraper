import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int = 143_360):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                parsed_content_length = int(content_length)
            except ValueError:
                await self._send_bad_request(send)
                return

            if parsed_content_length > self.max_body_size:
                await self._send_too_large(send)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes

            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_size:
                    raise RequestBodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._send_too_large(send)

    async def _send_too_large(self, send: Send) -> None:
        body = json.dumps({"detail": "Request Entity Too Large"}).encode()
        await self._send_json(send, 413, body)

    async def _send_bad_request(self, send: Send) -> None:
        body = json.dumps({"detail": "Invalid Content-Length"}).encode()
        await self._send_json(send, 400, body)

    async def _send_json(self, send: Send, status_code: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

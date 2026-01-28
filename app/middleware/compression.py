"""
Response Compression Middleware for Signal Service
Implements gzip/deflate compression for API responses
"""
import gzip
import io

from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Compression middleware that supports gzip and deflate
    Compresses responses based on Accept-Encoding header
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compression_level: int = 6,
        exclude_paths: list[str] | None = None,
        exclude_media_types: list[str] | None = None
    ):
        super().__init__(app)
        self.minimum_size = minimum_size  # Minimum size in bytes to compress
        self.compression_level = compression_level  # 1-9, higher = better compression
        self.exclude_paths = exclude_paths or ["/metrics", "/health", "/ready"]
        self.exclude_media_types = exclude_media_types or [
            "image/png", "image/jpeg", "image/jpg", "image/gif",
            "application/zip", "application/gzip", "application/octet-stream"
        ]

    async def dispatch(self, request: Request, call_next):
        """Process request with compression"""
        # Check if path is excluded
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Check Accept-Encoding header
        accept_encoding = request.headers.get("accept-encoding", "")

        # Process request
        response = await call_next(request)

        # Check if compression is supported and needed
        if not self._should_compress(response, accept_encoding):
            return response

        # Read response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Check minimum size
        if len(body) < self.minimum_size:
            # Return original response
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Compress body
        compressed_body, encoding = self._compress_body(body, accept_encoding)

        # Create new response with compressed body
        headers = MutableHeaders(response.headers)
        headers["content-encoding"] = encoding
        headers["content-length"] = str(len(compressed_body))

        # Add Vary header to indicate caching should consider Accept-Encoding
        vary = headers.get("vary", "")
        if vary:
            headers["vary"] = f"{vary}, Accept-Encoding"
        else:
            headers["vary"] = "Accept-Encoding"

        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=dict(headers),
            media_type=response.media_type
        )

    def _should_compress(self, response: Response, accept_encoding: str) -> bool:
        """Check if response should be compressed"""
        # Check if already compressed
        if "content-encoding" in response.headers:
            return False

        # Check media type
        media_type = response.media_type or "text/plain"
        if any(media_type.startswith(excluded) for excluded in self.exclude_media_types):
            return False

        # Check if client supports compression
        if "gzip" not in accept_encoding and "deflate" not in accept_encoding:
            return False

        # Check status code (only compress successful responses)
        return not response.status_code >= 300

    def _compress_body(self, body: bytes, accept_encoding: str) -> tuple[bytes, str]:
        """
        Compress response body

        Returns:
            tuple of (compressed_body, encoding)
        """
        # Prefer gzip
        if "gzip" in accept_encoding:
            return self._gzip_compress(body), "gzip"
        if "deflate" in accept_encoding:
            return self._deflate_compress(body), "deflate"
        # Should not happen due to _should_compress check
        return body, "identity"

    def _gzip_compress(self, data: bytes) -> bytes:
        """Compress data using gzip"""
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode='wb', compresslevel=self.compression_level) as f:
            f.write(data)
        return out.getvalue()

    def _deflate_compress(self, data: bytes) -> bytes:
        """Compress data using deflate (zlib)"""
        import zlib
        return zlib.compress(data, self.compression_level)


class StreamingCompressionMiddleware:
    """
    Advanced compression middleware that supports streaming responses
    Useful for WebSocket and Server-Sent Events
    """

    def __init__(self, app: ASGIApp, chunk_size: int = 4096):
        self.app = app
        self.chunk_size = chunk_size

    async def __call__(self, scope, receive, send):
        """ASGI application"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check Accept-Encoding
        headers = dict(scope["headers"])
        accept_encoding = headers.get(b"accept-encoding", b"").decode()

        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return

        # Intercept send to compress responses
        compressor = None
        headers_sent = False

        async def send_compressed(message):
            nonlocal compressor, headers_sent

            if message["type"] == "http.response.start":
                # Modify headers to add content-encoding
                headers = dict(message.get("headers", []))
                headers[b"content-encoding"] = b"gzip"
                headers[b"vary"] = b"Accept-Encoding"

                # Remove content-length as it will change
                headers = [(k, v) for k, v in headers.items() if k != b"content-length"]

                message["headers"] = list(headers.items())
                headers_sent = True

                # Initialize compressor
                compressor = gzip.GzipFile(mode='wb', fileobj=io.BytesIO())

                await send(message)

            elif message["type"] == "http.response.body":
                if not headers_sent:
                    # Headers weren't sent yet, pass through
                    await send(message)
                    return

                body = message.get("body", b"")
                more_body = message.get("more_body", False)

                if body and compressor:
                    # Compress chunk
                    compressor.write(body)

                    if not more_body:
                        # Final chunk
                        compressor.close()
                        compressed = compressor.fileobj.getvalue()

                        await send({
                            "type": "http.response.body",
                            "body": compressed,
                            "more_body": False
                        })
                    else:
                        # Flush partial data
                        compressor.flush()
                        compressed = compressor.fileobj.getvalue()
                        compressor.fileobj.truncate(0)
                        compressor.fileobj.seek(0)

                        if compressed:
                            await send({
                                "type": "http.response.body",
                                "body": compressed,
                                "more_body": True
                            })
                else:
                    await send(message)
            else:
                await send(message)

        await self.app(scope, receive, send_compressed)

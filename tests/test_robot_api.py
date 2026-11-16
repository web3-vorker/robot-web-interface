import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
import httpx
import pytest

from backend.app.config import Settings
from backend.app.main import create_app


@asynccontextmanager
async def robot_api(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(Settings(robot_host="robot.test"))
    async with app.router.lifespan_context(app):
        await app.state.robot_client.aclose()
        app.state.robot_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://backend.test",
        ) as client:
            yield client


def test_drive_validates_and_forwards_command_unchanged() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"accepted": True})

    async def scenario() -> None:
        async with robot_api(handler) as client:
            response = await client.post(
                "/api/robot/drive",
                json={"cmd": "forward", "speed": 100, "ms": 0},
            )
            invalid = await client.post(
                "/api/robot/drive",
                json={"cmd": "forward", "speed": 101, "ms": 0},
            )

        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        assert requests[0].url == "http://robot.test:8090/drive"
        assert requests[0].read() == b'{"cmd":"forward","speed":100,"ms":0}'
        assert invalid.status_code == 422
        assert len(requests) == 1

    asyncio.run(scenario())


def test_drive_maps_connect_timeout_without_exposing_upstream_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("private upstream details", request=request)

    async def scenario() -> None:
        async with robot_api(handler) as client:
            response = await client.post(
                "/api/robot/drive",
                json={"cmd": "stop", "speed": 0, "ms": 0},
            )

        assert response.status_code == 504
        assert response.json() == {"detail": "Robot connection timed out"}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [(400, 400), (503, 503), (500, 502)],
)
def test_drive_maps_robot_http_errors(upstream_status: int, expected_status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(upstream_status)

    async def scenario() -> None:
        async with robot_api(handler) as client:
            response = await client.post(
                "/api/robot/drive",
                json={"cmd": "left", "speed": 50, "ms": 250},
            )

        assert response.status_code == expected_status
        assert "robot.test" not in response.text

    asyncio.run(scenario())


def test_status_proxies_robot_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == "http://robot.test:8090/status"
        return httpx.Response(200, json={"state": "moving", "last_cmd": "forward", "battery": None})

    async def scenario() -> None:
        async with robot_api(handler) as client:
            response = await client.get("/api/robot/status")

        assert response.status_code == 200
        assert response.json() == {"state": "moving", "last_cmd": "forward", "battery": None}

    asyncio.run(scenario())


def test_frontend_is_served_by_the_backend() -> None:
    async def scenario() -> None:
        app = create_app(Settings(robot_host="robot.test"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://backend.test",
        ) as client:
            page = await client.get("/")
            styles = await client.get("/styles.css")

        assert page.status_code == 200
        assert 'id="video-feed"' in page.text
        assert styles.status_code == 200
        assert "--amber: #f2a93b" in styles.text

    asyncio.run(scenario())


def test_video_stream_is_forwarded_and_upstream_is_closed() -> None:
    class VideoStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"--frame\r\n"
            yield b"image-data\r\n"

        async def aclose(self) -> None:
            self.closed = True

    stream = VideoStream()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://robot.test:8080/"
        return httpx.Response(
            200,
            headers={"content-type": "multipart/x-mixed-replace; boundary=frame"},
            stream=stream,
        )

    async def scenario() -> None:
        async with robot_api(handler) as client:
            response = await client.get("/api/robot/video")

        assert response.status_code == 200
        assert response.content == b"--frame\r\nimage-data\r\n"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-accel-buffering"] == "no"
        assert stream.closed

    asyncio.run(scenario())

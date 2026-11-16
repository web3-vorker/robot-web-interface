import logging
from collections.abc import AsyncIterator
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/robot", tags=["robot"])


class DriveCommand(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    cmd: Literal["forward", "backward", "left", "right", "stop"]
    speed: Annotated[int, Field(ge=0, le=100)]
    ms: Annotated[int, Field(ge=0)]


def _client(request: Request) -> httpx.AsyncClient:
    return request.app.state.robot_client


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _handle_network_error(exc: httpx.RequestError, operation: str) -> HTTPException:
    if isinstance(exc, httpx.ConnectTimeout):
        logger.warning("Robot %s connection timed out", operation)
        return HTTPException(status_code=504, detail="Robot connection timed out")
    if isinstance(exc, httpx.ConnectError):
        logger.warning("Could not connect to robot for %s", operation)
        return HTTPException(status_code=503, detail="Robot is unavailable")
    if isinstance(exc, httpx.TimeoutException):
        logger.warning("Robot %s request timed out", operation)
        return HTTPException(status_code=504, detail="Robot request timed out")
    logger.warning("Robot %s request failed", operation)
    return HTTPException(status_code=502, detail="Robot request failed")


def _upstream_status_error(status_code: int, operation: str) -> HTTPException:
    logger.warning("Robot returned HTTP %s for %s", status_code, operation)
    if status_code == 400:
        return HTTPException(status_code=400, detail="Robot rejected the request")
    if status_code == 503:
        return HTTPException(status_code=503, detail="Robot is unavailable")
    return HTTPException(status_code=502, detail="Robot returned an error")


async def _stream_video(
    response: httpx.Response,
) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
        logger.warning("Robot video stream ended")
    except httpx.RequestError:
        logger.exception("Error reading robot video stream")
    except Exception:
        logger.exception("Error sending robot video stream")
        raise
    finally:
        await response.aclose()
        logger.info("Robot video connection closed")


@router.get("/video")
async def video(request: Request) -> StreamingResponse:
    client = _client(request)
    settings = _settings(request)
    timeout = httpx.Timeout(
        connect=settings.robot_request_timeout,
        read=None,
        write=settings.robot_request_timeout,
        pool=settings.robot_request_timeout,
    )
    upstream_request = client.build_request("GET", settings.robot_stream_url, timeout=timeout)

    try:
        upstream = await client.send(upstream_request, stream=True)
        upstream.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await exc.response.aclose()
        raise _upstream_status_error(exc.response.status_code, "video stream") from exc
    except httpx.RequestError as exc:
        raise _handle_network_error(exc, "video stream") from exc

    logger.info("Robot video connection established")
    return StreamingResponse(
        _stream_video(upstream),
        media_type=upstream.headers.get("content-type", "multipart/x-mixed-replace; boundary=frame"),
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/drive")
async def drive(command: DriveCommand, request: Request) -> Response:
    settings = _settings(request)
    try:
        upstream = await _client(request).post(
            f"{settings.robot_api_url}/drive",
            json=command.model_dump(),
        )
        upstream.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _upstream_status_error(exc.response.status_code, "drive command") from exc
    except httpx.RequestError as exc:
        raise _handle_network_error(exc, "drive command") from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@router.get("/status")
async def status(request: Request) -> Response:
    settings = _settings(request)
    try:
        upstream = await _client(request).get(f"{settings.robot_api_url}/status")
        upstream.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _upstream_status_error(exc.response.status_code, "status request") from exc
    except httpx.RequestError as exc:
        raise _handle_network_error(exc, "status request") from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )

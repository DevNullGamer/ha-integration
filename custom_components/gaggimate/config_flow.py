"""Config flow for GaggiMate integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import DEFAULT_PORT, DOMAIN, WS_CONNECT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


def get_user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Get the user input schema with defaults."""
    return vol.Schema(
        {
            vol.Required(
                CONF_HOST,
                default=user_input.get(CONF_HOST) if user_input else "gaggimate.local",
            ): str,
            vol.Optional(
                CONF_PORT,
                default=user_input.get(CONF_PORT, DEFAULT_PORT) if user_input else DEFAULT_PORT,
            ): int,
        }
    )


async def validate_connection(hass: HomeAssistant, host: str, port: int) -> dict[str, Any]:
    """Validate the WebSocket connection to GaggiMate."""
    session = aiohttp_client.async_get_clientsession(hass)
    ws_url = f"ws://{host}:{port}/ws"

    try:
        # Try to connect to WebSocket
        async with asyncio.timeout(WS_CONNECT_TIMEOUT):
            ws = await session.ws_connect(ws_url)

            # Wait for first status message
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    import json
                    data = json.loads(msg.data)
                    if data.get("tp") == "evt:status":
                        # Successfully received status
                        await ws.close()
                        return {
                            "title": f"GaggiMate {host}",
                            "unique_id": host,
                        }
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break

            await ws.close()
            raise CannotConnect("No status message received")

    except asyncio.TimeoutError as err:
        raise CannotConnect("Connection timeout") from err
    except aiohttp.ClientError as err:
        raise CannotConnect(f"Connection failed: {err}") from err


class GaggiMateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GaggiMate."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Set unique ID to prevent duplicate entries
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=get_user_schema(user_input),
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

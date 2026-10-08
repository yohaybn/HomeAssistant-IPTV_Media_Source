"""MediaSource implementation for IPTV Media Source."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import cast  # Not used, can be removed

import aiohttp
from homeassistant.components.media_player.const import (  # Import media classes
    MediaClass,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.config_entries import ConfigEntry  # For type hinting if needed
from homeassistant.core import (
    HomeAssistant,
    callback,
)  # callback not used, can be removed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_M3U_URL, CONF_FRIENDLY_NAME
from .m3u import EXTINF_REGEX, parse_m3u_text  # noqa: F401

_LOGGER = logging.getLogger(__name__)

M3U_CACHE_SECONDS = 300  # Cache M3U content for 5 minutes
PARSED_M3U_CACHE = {}


async def async_parse_m3u(
    hass: HomeAssistant, m3u_url: str, m3u_friendly_name: str
) -> list[dict]:
    """
    Fetch and parse an M3U playlist URL.
    Returns a list of channel dictionaries.
    """
    global PARSED_M3U_CACHE

    cached_data = PARSED_M3U_CACHE.get(m3u_url)
    if cached_data and (time.time() - cached_data["timestamp"]) < M3U_CACHE_SECONDS:
        _LOGGER.debug(f"Using cached channels for {m3u_friendly_name} ({m3u_url})")
        return cached_data["channels"]

    _LOGGER.debug(f"Fetching M3U playlist from: {m3u_url} for {m3u_friendly_name}")
    session = async_get_clientsession(hass)
    try:
        async with session.get(m3u_url, timeout=15) as response:
            response.raise_for_status()
            try:
                content = await response.text(encoding="utf-8")
            except UnicodeDecodeError:
                _LOGGER.warning(
                    f"Failed to decode M3U {m3u_url} as UTF-8. Attempting with 'latin-1'."
                )
                # Read raw bytes and decode using latin-1, replacing errors
                raw_bytes = await response.read()
                content = raw_bytes.decode("latin-1", errors="replace")
                _LOGGER.debug(f"Successfully decoded M3U {m3u_url} with 'latin-1'.")

    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.error(f"Error fetching M3U playlist {m3u_url}: {err}")
        if cached_data:
            _LOGGER.warning(
                f"Returning stale cache for {m3u_friendly_name} due to fetch error."
            )
            return cached_data["channels"]
        raise BrowseError(
            f"Could not fetch IPTV playlist: {m3u_friendly_name}"
        ) from err

    channels = parse_m3u_text(content, m3u_url)

    _LOGGER.info(
        f"Parsed {len(channels)} channels from {m3u_friendly_name} ({m3u_url})"
    )
    PARSED_M3U_CACHE[m3u_url] = {"timestamp": time.time(), "channels": channels}
    return channels


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up IPTV Media Source media source."""
    return IPTVMediaSourcePlatform(hass)


class IPTVMediaSourcePlatform(MediaSource):
    """Provide IPTV streams as a media source, allowing channel Browse."""

    name: str = "IPTV Media"

    def __init__(self, hass: HomeAssistant):
        """Initialize IPTV source."""
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a playable item."""
        stream_url = item.identifier
        _LOGGER.debug(f"Resolving media for playback: {stream_url}")
        return PlayMedia(stream_url, "application/x-mpegURL")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return media Browse data."""
        if item.identifier is None:
            return await self._async_browse_root()
        else:
            m3u_url_to_browse = item.identifier
            entry = self._find_entry_for_m3u_url(m3u_url_to_browse)
            if not entry:
                raise BrowseError(
                    f"Configured IPTV source not found for URL: {m3u_url_to_browse}"
                )

            friendly_name = entry.data.get(CONF_FRIENDLY_NAME, "IPTV Playlist")
            return await self._async_browse_m3u_channels(
                m3u_url_to_browse, friendly_name
            )

    def _find_entry_for_m3u_url(self, m3u_url: str) -> ConfigEntry | None:
        """Find the config entry associated with a given M3U URL."""
        for entry_obj in self.hass.config_entries.async_entries(DOMAIN):
            if entry_obj.data.get(CONF_M3U_URL) == m3u_url:
                return entry_obj
        return None

    async def _async_browse_root(self) -> BrowseMediaSource:
        """Browse the root of the IPTV media source, listing configured M3U files."""
        base = BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type="application/x-mpegURL",
            title=self.name,
            can_play=False,
            can_expand=True,
            children=[],
        )

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            m3u_url = entry.data.get(CONF_M3U_URL)
            friendly_name = entry.data.get(
                CONF_FRIENDLY_NAME, f"IPTV Source {entry.entry_id[:6]}"
            )

            if not m3u_url:
                _LOGGER.warning(
                    f"Config entry {entry.entry_id} for {DOMAIN} is missing an M3U URL."
                )
                continue

            base.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=m3u_url,
                    media_class=MediaClass.PLAYLIST,
                    media_content_type="playlist",
                    title=friendly_name,
                    can_play=False,
                    can_expand=True,
                    thumbnail=None,
                )
            )
        if not base.children:
            _LOGGER.debug("No IPTV Media Sources configured yet.")
        return base

    async def _async_browse_m3u_channels(
        self, m3u_url: str, playlist_title: str
    ) -> BrowseMediaSource:
        """Browse channels within a specific M3U playlist."""
        try:
            channels = await async_parse_m3u(self.hass, m3u_url, playlist_title)
        except BrowseError as e:
            raise e
        except Exception as e:
            _LOGGER.error(f"Failed to parse M3U {playlist_title} ({m3u_url}): {e}")
            raise BrowseError(f"Could not parse channels for {playlist_title}.")

        playlist_browse_item = BrowseMediaSource(
            domain=DOMAIN,
            identifier=m3u_url,
            media_class=MediaClass.PLAYLIST,
            media_content_type="playlist",
            title=playlist_title,
            can_play=False,
            can_expand=True,  # True even if no children, UI might show empty
            children=[],
        )

        if not channels:
            _LOGGER.info(f"No channels found in {playlist_title} ({m3u_url}).")
            playlist_browse_item.can_expand = False  # No children, so not expandable
            return playlist_browse_item

        for channel in channels:
            channel_stream_url = channel["url"]
            channel_name = channel["name"]
            channel_thumbnail = channel.get("logo")

            playlist_browse_item.children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=channel_stream_url,
                    media_class=MediaClass.CHANNEL,
                    media_content_type="application/x-mpegURL",  # Assuming HLS for the stream
                    title=channel_name,
                    can_play=True,
                    can_expand=False,
                    thumbnail=channel_thumbnail,
                )
            )

        playlist_browse_item.children.sort(key=lambda x: x.title)

        return playlist_browse_item

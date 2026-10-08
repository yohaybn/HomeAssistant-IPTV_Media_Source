"""Pure M3U parsing, no Home Assistant imports."""

from __future__ import annotations

import logging
import re

_LOGGER = logging.getLogger(__name__)

# Regex to capture channel information from #EXTINF line

EXTINF_REGEX = re.compile(
    r"#EXTINF:(?P<duration>-?\d+)"  # Duration is mandatory
    r"(?:.*?\s+tvg-id=\"(?P<tvg_id>[^\"]*)\")?"  # Optional tvg-id
    r"(?:.*?\s+tvg-name=\"(?P<tvg_name>[^\"]*)\")?"  # Optional tvg-name
    r"(?:.*?\s+tvg-logo=\"(?P<tvg_logo>[^\"]*)\")?"  # Optional tvg-logo
    r"(?:.*?\s+group-title=\"(?P<group_title>[^\"]*)\")?"  # Optional group-title
    r".*?"
    r",\s*(?P<name>[^,]+)$",
    re.IGNORECASE,
)



def parse_m3u_text(content: str, m3u_url: str) -> list[dict]:
    """Parse M3U text into a list of channel dictionaries."""
    channels = []
    current_channel_info = {}
    lines = content.splitlines()

    if not lines or not lines[0].strip().upper().startswith("#EXTM3U"):
        _LOGGER.warning(
            f"M3U file {m3u_url} does not start with #EXTM3U. Attempting to parse anyway."
        )

    for line_num, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        match = EXTINF_REGEX.match(line)
        if match:
            current_channel_info = match.groupdict()
            if not current_channel_info.get("name") and current_channel_info.get(
                "tvg_name"
            ):
                current_channel_info["name"] = current_channel_info["tvg_name"]
            if current_channel_info.get("name") is None:
                current_channel_info["name"] = "Unnamed Channel"

        elif current_channel_info and (
            line.startswith("http://") or line.startswith("https://")
        ):
            # Optional regex groups are present in the dict as None when the
            # attribute is missing (e.g. tvheadend has no group-title), so
            # dict.get defaults do not apply.
            channel_name = (current_channel_info.get("name") or "Unnamed Channel").strip()
            logo = current_channel_info.get("tvg_logo")
            group = (current_channel_info.get("group_title") or "Uncategorized").strip()

            channels.append(
                {
                    "name": channel_name,
                    "url": line,
                    "logo": logo if logo else None,
                    "group": group,
                    "original_m3u_url": m3u_url,
                }
            )
            current_channel_info = {}
        elif (
            line.startswith("http://") or line.startswith("https://")
        ) and not current_channel_info:
            _LOGGER.debug(
                f"Found a URL without preceding #EXTINF: {line}. Skipping for detailed parsing."
            )

    return channels

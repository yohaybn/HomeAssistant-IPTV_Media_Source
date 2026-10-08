import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "iptv_media_source"))

from m3u import parse_m3u_text  # noqa: E402

URL = "http://192.168.1.28:9981/playlist/channels.m3u"

TVHEADEND = """#EXTM3U
#EXTINF:-1 tvg-id="abc" tvg-logo="http://x/logo.png",Channel One
http://192.168.1.28:9981/stream/channelid/1
#EXTINF:-1,Channel Two
http://192.168.1.28:9981/stream/channelid/2
"""


def test_missing_group_title_does_not_crash():
    channels = parse_m3u_text(TVHEADEND, URL)
    assert [c["name"] for c in channels] == ["Channel One", "Channel Two"]
    assert all(c["group"] == "Uncategorized" for c in channels)


def test_group_title_kept_when_present():
    text = '#EXTM3U\n#EXTINF:-1 tvg-id="a" tvg-name="A" tvg-logo="l" group-title="News",A\nhttp://h/1\n'
    ch = parse_m3u_text(text, URL)
    assert ch[0]["group"] == "News"
    assert ch[0]["logo"] == "l"


def test_empty_and_url_without_extinf():
    assert parse_m3u_text("", URL) == []
    assert parse_m3u_text("#EXTM3U\nhttp://h/1\n", URL) == []

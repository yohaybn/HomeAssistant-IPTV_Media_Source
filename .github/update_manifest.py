"""Update the manifest file."""

import json
from pathlib import Path
import sys


def update_manifest():
    """Update the manifest file."""
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in ["--version", "-V"]:
            version = sys.argv[index + 1]

    with Path.open(
        f"{Path.cwd()}/custom_components/iptv_media_source/manifest.json",
    ) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    with Path.open(
        f"{Path.cwd()}/custom_components/iptv_media_source/manifest.json",
        "w",
    ) as manifestfile:
        manifestfile.write(json.dumps(manifest, indent=4, sort_keys=True))


update_manifest()

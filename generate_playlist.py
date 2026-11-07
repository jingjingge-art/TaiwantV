#!/usr/bin/env python3
"""Merge Taiwan channel playlists into the root-level text playlist."""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

SOURCES = (
    "https://raw.githubusercontent.com/jingjingge-art/SHEYE/refs/heads/main/shanghaieye.txt",
    "https://raw.githubusercontent.com/DEvmIb/famelack-channels-m3u/refs/heads/main/m3u/tw.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/refs/heads/master/streams/tw.m3u",
)
OUTPUT = Path("中国台湾省iptv.txt")

CATEGORIES = (
    "新闻", "财经", "体育", "电影剧集", "少儿", "宗教", "音乐", "综合", "其他"
)
KEYWORDS = {
    "新闻": ("新闻", "news", "newschannel", "新闻资讯"),
    "财经": ("财经", "financial", "finance", "商业", "business"),
    "体育": ("体育", "sports", "sport", "足球", "棒球"),
    "电影剧集": ("电影", "movie", "cinema", "戏剧", "drama", "影剧"),
    "少儿": ("少儿", "儿童", "kids", "cartoon", "卡通", "幼儿"),
    "宗教": ("宗教", "religion", "church", "god", "基督", "佛", "圣经"),
    "音乐": ("音乐", "music", "歌曲"),
    "综合": ("综合", "general", "variety", "综合台"),
}
GROUP_ALIASES = {
    "news": "新闻", "新闻": "新闻", "finance": "财经", "财经": "财经",
    "sports": "体育", "sport": "体育", "体育": "体育",
    "movies": "电影剧集", "movie": "电影剧集", "电影": "电影剧集",
    "kids": "少儿", "children": "少儿", "少儿": "少儿",
    "religion": "宗教", "宗教": "宗教", "music": "音乐", "音乐": "音乐",
    "general": "综合", "variety": "综合", "综合": "综合",
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "TaiwantV-playlist-builder/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def classify(name: str, source_group: str = "") -> str:
    group = source_group.strip().casefold()
    for key, category in GROUP_ALIASES.items():
        if key in group:
            return category
    text = f"{name} {source_group}".casefold()
    for category, words in KEYWORDS.items():
        if any(word.casefold() in text for word in words):
            return category
    return "其他"


def parse_playlist(text: str) -> list[tuple[str, str, str]]:
    """Return (category, channel name, stream URL) records from M3U or text lists."""
    records: list[tuple[str, str, str]] = []
    pending_name = ""
    pending_group = ""
    plain_group = ""

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            metadata, separator, name = line.partition(",")
            pending_name = name.strip() if separator else ""
            match = re.search(r'group-title="([^"]*)"', metadata, flags=re.IGNORECASE)
            pending_group = match.group(1).strip() if match else ""
            continue
        if line.startswith("#"):
            continue

        if pending_name:
            records.append((classify(pending_name, pending_group), pending_name, line))
            pending_name = ""
            pending_group = ""
            continue

        # Plain-text playlists commonly use "category,#genre#" and "name,url".
        if "," not in line:
            continue
        name, value = (part.strip() for part in line.split(",", 1))
        if value.casefold().endswith("#genre#"):
            plain_group = name
            continue
        if name and value.startswith(("http://", "https://", "rtmp://", "rtmps://", "udp://")):
            records.append((classify(name, plain_group), name, value))

    return records


def main() -> None:
    # Do not publish a partial playlist if any source is unavailable or empty.
    all_records: list[tuple[str, str, str]] = []
    for source in SOURCES:
        try:
            source_records = parse_playlist(fetch(source))
        except (urllib.error.URLError, TimeoutError, UnicodeError) as error:
            raise RuntimeError(f"Could not fetch playlist {source}: {error}") from error
        if not source_records:
            raise RuntimeError(f"No channels were parsed from {source}; refusing to replace output.")
        all_records.extend(source_records)

    # Remove only exact duplicate name/URL pairs; keep different channel names even
    # when they point to the same stream so no listed channel is silently lost.
    seen: set[tuple[str, str]] = set()
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for category, name, url in all_records:
        identity = (name.casefold(), url)
        if identity in seen:
            continue
        seen.add(identity)
        grouped[category].append((name, url))

    lines: list[str] = []
    for category in CATEGORIES:
        channels = grouped.get(category, [])
        if not channels:
            continue
        lines.append(f"{category},#genre#")
        lines.extend(f"{name},{url}" for name, url in channels)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print(f"Wrote {len(seen)} channels across {len(grouped)} categories to {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Playlist generation failed: {error}", file=sys.stderr)
        raise

"""Video URL parse va embed yordamchilari."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

YOUTUBE_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{6,})',
    re.IGNORECASE,
)
VIMEO_RE = re.compile(
    r'(?:vimeo\.com/(?:video/)?|player\.vimeo\.com/video/)(\d+)',
    re.IGNORECASE,
)


def extract_youtube_id(url: str) -> str:
    if not url:
        return ''
    match = YOUTUBE_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    if 'youtube.com' in (parsed.netloc or ''):
        qs = parse_qs(parsed.query or '')
        vids = qs.get('v') or []
        if vids and vids[0]:
            return vids[0]
    return ''


def extract_vimeo_id(url: str) -> str:
    if not url:
        return ''
    match = VIMEO_RE.search(url)
    return match.group(1) if match else ''


def video_embed_info(url: str) -> dict[str, Any]:
    """
    Returns:
      provider: youtube | vimeo | external | ''
      video_id, embed_url, watchable
    """
    url = (url or '').strip()
    if not url:
        return {
            'provider': '',
            'video_id': '',
            'embed_url': '',
            'watchable': False,
        }

    yt = extract_youtube_id(url)
    if yt:
        return {
            'provider': 'youtube',
            'video_id': yt,
            'embed_url': f'https://www.youtube.com/embed/{yt}?enablejsapi=1&rel=0',
            'watchable': True,
        }

    vim = extract_vimeo_id(url)
    if vim:
        return {
            'provider': 'vimeo',
            'video_id': vim,
            'embed_url': f'https://player.vimeo.com/video/{vim}',
            'watchable': True,
        }

    return {
        'provider': 'external',
        'video_id': '',
        'embed_url': url,
        'watchable': True,
    }

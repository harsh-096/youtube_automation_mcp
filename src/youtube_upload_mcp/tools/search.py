"""YouTube search and SEO discovery tools."""

import json
import urllib.parse
import urllib.request

from youtube_upload_mcp.runtime import READ_ONLY_ANNOTATIONS, auth, mcp, quota
from youtube_upload_mcp.utils.formatting import format_video_summary
from youtube_upload_mcp.utils.validators import ValidationError, validate_youtube_id

_VALID_SEARCH_TYPES = frozenset({"video", "channel", "playlist"})
_VALID_SEARCH_ORDERS = frozenset({"relevance", "date", "viewCount", "rating"})


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_search(
    query: str,
    search_type: str = "video",
    channel_id: str | None = None,
    max_results: int = 10,
    order: str = "relevance",
    published_after: str | None = None,
    published_before: str | None = None,
    region_code: str | None = None,
) -> dict:
    """Search YouTube for videos, channels, or playlists (costs 100 quota units)."""
    if search_type not in _VALID_SEARCH_TYPES:
        return {"error": f"Invalid search_type {search_type!r}."}
    if order not in _VALID_SEARCH_ORDERS:
        return {"error": f"Invalid order {order!r}."}

    if channel_id:
        try:
            channel_id = validate_youtube_id(channel_id, "channel_id")
        except ValidationError as e:
            return {"error": str(e)}

    quota.consume("search")
    youtube = auth.build_youtube_service()

    params: dict = {
        "part": "snippet",
        "q": query,
        "type": search_type,
        "maxResults": min(max_results, 50),
        "order": order,
    }
    if channel_id:
        params["channelId"] = channel_id
    if published_after:
        params["publishedAfter"] = published_after
    if published_before:
        params["publishedBefore"] = published_before
    if region_code:
        params["regionCode"] = region_code

    response = youtube.search().list(**params).execute()

    results = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        result = {
            "title": snippet.get("title"),
            "description": snippet.get("description", "")[:200],
            "channel_title": snippet.get("channelTitle"),
            "published_at": snippet.get("publishedAt"),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        }
        id_info = item.get("id", {})
        if search_type == "video":
            result["video_id"] = id_info.get("videoId")
        elif search_type == "channel":
            result["channel_id"] = id_info.get("channelId")
        elif search_type == "playlist":
            result["playlist_id"] = id_info.get("playlistId")
        results.append(result)

    return {
        "results": results,
        "total_results": response.get("pageInfo", {}).get("totalResults", len(results)),
        "quota_cost": 100,
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_search_suggestions(query: str, language: str = "en") -> dict:
    """Get YouTube autocomplete/search suggestions for SEO research (no quota cost)."""
    encoded_query = urllib.parse.quote(query)
    encoded_lang = urllib.parse.quote(language)
    url = (
        "https://suggestqueries-clients6.youtube.com/complete/search"
        f"?client=youtube&ds=yt&q={encoded_query}&hl={encoded_lang}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        raw = raw[raw.index("(") + 1 : raw.rindex(")")]
        data = json.loads(raw)
        suggestions = [item[0] for item in data[1]]
    except Exception as e:
        return {"query": query, "error": f"Failed to fetch suggestions: {e}"}

    return {"query": query, "suggestions": suggestions}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_trending(
    region_code: str = "US",
    category_id: str | None = None,
    max_results: int = 10,
) -> dict:
    """Get currently trending videos on YouTube (costs 1 quota unit)."""
    quota.consume("list")
    youtube = auth.build_youtube_service()

    params: dict = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": min(max_results, 50),
    }
    if category_id:
        params["videoCategoryId"] = category_id

    response = youtube.videos().list(**params).execute()
    videos = [format_video_summary(v) for v in response.get("items", [])]

    return {
        "region": region_code,
        "category_id": category_id,
        "videos": videos,
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_get_categories(region_code: str = "US") -> dict:
    """List assignable YouTube video categories for a region (costs 1 quota unit)."""
    quota.consume("list")
    youtube = auth.build_youtube_service()

    response = youtube.videoCategories().list(part="snippet", regionCode=region_code).execute()
    categories = [
        {"id": item["id"], "title": item["snippet"]["title"]}
        for item in response.get("items", [])
        if item.get("snippet", {}).get("assignable")
    ]
    return {"region": region_code, "categories": categories}

"""Channel and video read tools."""

from youtube_upload_mcp.server import READ_ONLY_ANNOTATIONS, auth, mcp, quota
from youtube_upload_mcp.utils.formatting import format_video_summary
from youtube_upload_mcp.utils.validators import ValidationError, validate_youtube_id


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_get_channel(
    channel_id: str | None = None,
    handle: str | None = None,
    mine: bool = False,
) -> dict:
    """Get channel details by channel ID, handle (@username), or the authenticated channel.

    Args:
        channel_id: YouTube channel ID (e.g., "UCxxxxxxx").
        handle: Channel handle (e.g., "@mkbhd").
        mine: If True, get the authenticated user's own channel.
    """
    params: dict = {"part": "snippet,statistics,contentDetails,brandingSettings"}
    if mine:
        params["mine"] = True
    elif handle:
        params["forHandle"] = handle
    elif channel_id:
        try:
            params["id"] = validate_youtube_id(channel_id, "channel_id")
        except ValidationError as e:
            return {"error": str(e)}
    else:
        return {"error": "Provide channel_id, handle, or set mine=True"}

    quota.consume("list")
    youtube = auth.build_youtube_service()
    response = youtube.channels().list(**params).execute()
    items = response.get("items", [])
    if not items:
        return {"error": "Channel not found"}

    ch = items[0]
    snippet = ch.get("snippet", {})
    stats = ch.get("statistics", {})

    return {
        "id": ch["id"],
        "title": snippet.get("title"),
        "handle": snippet.get("customUrl"),
        "description": snippet.get("description", "")[:500],
        "published_at": snippet.get("publishedAt"),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "uploads_playlist_id": (
            ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        ),
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_list_videos(
    channel_id: str | None = None,
    playlist_id: str | None = None,
    mine: bool = False,
    max_results: int = 20,
) -> dict:
    """List videos from a channel or playlist, sorted by most recent.

    Args:
        channel_id: Channel ID to list videos from.
        playlist_id: Playlist ID to list videos from (overrides channel_id).
        mine: If True, list the authenticated user's videos.
        max_results: Number of videos to return. Values above 50 page through
            results; 0 or negative fetches every video in the playlist.
    """
    try:
        if playlist_id:
            playlist_id = validate_youtube_id(playlist_id, "playlist_id")
        elif channel_id:
            channel_id = validate_youtube_id(channel_id, "channel_id")
    except ValidationError as e:
        return {"error": str(e)}

    youtube = auth.build_youtube_service()
    target = max_results if (max_results and max_results > 0) else None

    if not playlist_id:
        quota.consume("list")
        ch_params: dict = {"part": "contentDetails"}
        if mine:
            ch_params["mine"] = True
        elif channel_id:
            ch_params["id"] = channel_id
        else:
            return {"error": "Provide channel_id, playlist_id, or set mine=True"}

        ch_response = youtube.channels().list(**ch_params).execute()
        ch_items = ch_response.get("items", [])
        if not ch_items:
            return {"error": "Channel not found"}
        playlist_id = (
            ch_items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        )

    if not playlist_id:
        return {"error": "Could not resolve uploads playlist"}

    video_ids: list[str] = []
    pi_map: dict[str, str] = {}
    page_token: str | None = None
    pl_response: dict = {}

    while True:
        page_size = 50 if target is None else min(50, target - len(video_ids))
        if page_size <= 0:
            break
        quota.consume("list")
        pl_response = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        for item in pl_response.get("items", []):
            vid = item["contentDetails"]["videoId"]
            video_ids.append(vid)
            pi_map[vid] = item["id"]
        page_token = pl_response.get("nextPageToken")
        if not page_token:
            break
        if target is not None and len(video_ids) >= target:
            break

    total = pl_response.get("pageInfo", {}).get("totalResults", len(video_ids))
    if not video_ids:
        return {"videos": [], "total": total}

    videos = []
    for i in range(0, len(video_ids), 50):
        quota.consume("list")
        chunk = video_ids[i : i + 50]
        videos_response = (
            youtube.videos()
            .list(part="snippet,statistics,contentDetails", id=",".join(chunk))
            .execute()
        )
        for video in videos_response.get("items", []):
            summary = format_video_summary(video)
            summary["playlist_item_id"] = pi_map.get(summary.get("id"))
            videos.append(summary)

    return {"videos": videos, "total": total}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_get_video(video_id: str) -> dict:
    """Get detailed metadata and statistics for a specific video.

    Args:
        video_id: YouTube video ID (e.g., "dQw4w9WgXcQ").
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("list")
    youtube = auth.build_youtube_service()

    response = (
        youtube.videos()
        .list(part="snippet,statistics,contentDetails,status,topicDetails", id=clean_id)
        .execute()
    )

    items = response.get("items", [])
    if not items:
        return {"error": f"Video not found: {clean_id}"}

    video = items[0]
    summary = format_video_summary(video)

    status = video.get("status", {})
    summary["privacy"] = status.get("privacyStatus")
    summary["publish_at"] = status.get("publishAt")
    summary["license"] = status.get("license")
    summary["embeddable"] = status.get("embeddable")
    summary["topic_categories"] = video.get("topicDetails", {}).get("topicCategories", [])

    return summary

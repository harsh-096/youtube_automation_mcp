"""Playlist management tools."""

from youtube_upload_mcp.server import (
    DESTRUCTIVE_ANNOTATIONS,
    IDEMPOTENT_WRITE_ANNOTATIONS,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    auth,
    mcp,
    quota,
)
from youtube_upload_mcp.utils.validators import (
    ValidationError,
    validate_privacy_status,
    validate_youtube_id,
)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_list_playlists(
    channel_id: str | None = None,
    mine: bool = False,
    max_results: int = 25,
) -> dict:
    """List playlists for a channel.

    Args:
        channel_id: Channel ID to list playlists from.
        mine: If True, list the authenticated user's playlists.
        max_results: Number of playlists to return (0 or negative fetches all).
    """
    base_params: dict = {"part": "snippet,contentDetails"}
    if mine:
        base_params["mine"] = True
    elif channel_id:
        try:
            base_params["channelId"] = validate_youtube_id(channel_id, "channel_id")
        except ValidationError as e:
            return {"error": str(e)}
    else:
        return {"error": "Provide channel_id or set mine=True"}

    youtube = auth.build_youtube_service()
    target = max_results if (max_results and max_results > 0) else None

    playlists = []
    page_token: str | None = None
    response: dict = {}

    while True:
        page_size = 50 if target is None else min(50, target - len(playlists))
        if page_size <= 0:
            break
        quota.consume("list")
        response = (
            youtube.playlists()
            .list(**base_params, maxResults=page_size, pageToken=page_token)
            .execute()
        )
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            playlists.append({
                "id": item["id"],
                "title": snippet.get("title"),
                "description": snippet.get("description", "")[:200],
                "published_at": snippet.get("publishedAt"),
                "video_count": item.get("contentDetails", {}).get("itemCount", 0),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            })
        page_token = response.get("nextPageToken")
        if not page_token:
            break
        if target is not None and len(playlists) >= target:
            break

    total = response.get("pageInfo", {}).get("totalResults", len(playlists))
    return {"playlists": playlists, "total": total}


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_create_playlist(
    title: str,
    description: str = "",
    privacy_status: str = "private",
) -> dict:
    """Create a new playlist (private by default).

    Args:
        title: Playlist title.
        description: Playlist description.
        privacy_status: "private" (default), "public", or "unlisted".
    """
    try:
        validated_privacy = validate_privacy_status(privacy_status)
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("insert")
    youtube = auth.build_youtube_service()

    body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": validated_privacy},
    }
    response = youtube.playlists().insert(part="snippet,status", body=body).execute()

    return {
        "id": response["id"],
        "title": response["snippet"]["title"],
        "privacy": response["status"]["privacyStatus"],
        "url": f"https://www.youtube.com/playlist?list={response['id']}",
    }


@mcp.tool(annotations=IDEMPOTENT_WRITE_ANNOTATIONS)
def youtube_update_playlist(
    playlist_id: str,
    title: str | None = None,
    description: str | None = None,
    privacy_status: str | None = None,
) -> dict:
    """Update metadata for an existing playlist.

    Args:
        playlist_id: Playlist ID to update.
        title: New title.
        description: New description.
        privacy_status: "private", "public", or "unlisted".
    """
    try:
        clean_id = validate_youtube_id(playlist_id, "playlist_id")
        if privacy_status is not None:
            validate_privacy_status(privacy_status)
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("list")
    youtube = auth.build_youtube_service()

    current = youtube.playlists().list(part="snippet,status", id=clean_id).execute()
    items = current.get("items", [])
    if not items:
        return {"error": f"Playlist not found: {clean_id}"}

    snippet = items[0]["snippet"]
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description

    body: dict = {"id": clean_id, "snippet": snippet}
    if privacy_status is not None:
        body["status"] = {"privacyStatus": privacy_status}
        parts = "snippet,status"
    else:
        parts = "snippet"

    quota.consume("update")
    response = youtube.playlists().update(part=parts, body=body).execute()
    response_status = response.get("status") or {}

    return {
        "id": response["id"],
        "title": response["snippet"]["title"],
        "privacy": response_status.get("privacyStatus"),
        "updated": True,
    }


@mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS)
def youtube_delete_playlist(playlist_id: str, confirm: bool = False) -> dict:
    """Delete a playlist permanently. Does not delete the videos inside it.

    Args:
        playlist_id: Playlist ID to delete.
        confirm: Must be True to execute the deletion.
    """
    try:
        clean_id = validate_youtube_id(playlist_id, "playlist_id")
    except ValidationError as e:
        return {"error": str(e)}

    if not confirm:
        return {
            "playlist_id": clean_id,
            "deleted": False,
            "confirmation_required": True,
            "message": (
                f"Deletion of playlist {clean_id!r} is permanent. "
                "Re-run with confirm=True to proceed."
            ),
        }

    quota.consume("delete")
    youtube = auth.build_youtube_service()
    youtube.playlists().delete(id=clean_id).execute()
    return {"playlist_id": clean_id, "deleted": True}


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_add_to_playlist(
    playlist_id: str,
    video_id: str,
    position: int | None = None,
) -> dict:
    """Add a video to a playlist.

    Args:
        playlist_id: Playlist ID to add the video to.
        video_id: Video ID to add.
        position: Optional 0-based position in the playlist.
    """
    try:
        clean_playlist_id = validate_youtube_id(playlist_id, "playlist_id")
        clean_video_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("insert")
    youtube = auth.build_youtube_service()

    body: dict = {
        "snippet": {
            "playlistId": clean_playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": clean_video_id,
            },
        },
    }
    if position is not None:
        body["snippet"]["position"] = position

    response = youtube.playlistItems().insert(part="snippet", body=body).execute()

    return {
        "playlist_item_id": response["id"],
        "playlist_id": clean_playlist_id,
        "video_id": clean_video_id,
        "position": response["snippet"].get("position"),
        "added": True,
    }


@mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS)
def youtube_remove_from_playlist(playlist_item_id: str, confirm: bool = False) -> dict:
    """Remove a video from a playlist using its playlist_item_id.

    Args:
        playlist_item_id: The playlist item ID (not the video ID).
        confirm: Must be True to execute the removal.
    """
    try:
        clean_item_id = validate_youtube_id(playlist_item_id, "playlist_item_id")
    except ValidationError as e:
        return {"error": str(e)}

    if not confirm:
        return {
            "playlist_item_id": clean_item_id,
            "removed": False,
            "confirmation_required": True,
            "message": (
                f"Removing playlist item {clean_item_id!r}. "
                "Re-run with confirm=True to proceed."
            ),
        }

    quota.consume("delete")
    youtube = auth.build_youtube_service()
    youtube.playlistItems().delete(id=clean_item_id).execute()
    return {"playlist_item_id": clean_item_id, "removed": True}

"""Video publishing tools: upload, update metadata, thumbnails, delete."""

from googleapiclient.http import MediaFileUpload

from youtube_upload_mcp.server import (
    DESTRUCTIVE_ANNOTATIONS,
    IDEMPOTENT_WRITE_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    auth,
    get_allowed_media_dir,
    mcp,
    quota,
)
from youtube_upload_mcp.utils.validators import (
    ValidationError,
    validate_media_path,
    validate_privacy_status,
    validate_youtube_id,
)

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    category_id: str = "22",
    privacy_status: str = "private",
    publish_at: str | None = None,
    made_for_kids: bool = False,
) -> dict:
    """Upload a video to YouTube.

    Costs 1,600 quota units. Video is uploaded as private by default.

    Args:
        file_path: Path to the local video file.
        title: Video title (max 100 characters).
        description: Video description (max 5,000 characters).
        tags: Optional list of tags.
        category_id: YouTube category ID (default "22" = People & Blogs).
        privacy_status: "private" (default), "public", or "unlisted".
        publish_at: ISO 8601 datetime to schedule publishing (requires privacy_status="private").
        made_for_kids: COPPA self-declaration (default False).
    """
    try:
        validated_privacy = validate_privacy_status(privacy_status)
        if publish_at and validated_privacy != "private":
            raise ValidationError("publish_at requires privacy_status='private'.")
        resolved_path = validate_media_path(file_path, allowed_dir=get_allowed_media_dir())
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("video_insert")
    youtube = auth.build_youtube_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": validated_privacy,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    if publish_at and validated_privacy == "private":
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(str(resolved_path), resumable=True)
    response = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    ).execute()

    return {
        "id": response["id"],
        "title": response["snippet"]["title"],
        "privacy": response["status"]["privacyStatus"],
        "publish_at": response["status"].get("publishAt"),
        "url": f"https://www.youtube.com/watch?v={response['id']}",
        "quota_cost": 1600,
    }


@mcp.tool(annotations=IDEMPOTENT_WRITE_ANNOTATIONS)
def youtube_update_video(
    video_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    category_id: str | None = None,
    privacy_status: str | None = None,
    publish_at: str | None = None,
    made_for_kids: bool | None = None,
) -> dict:
    """Update metadata for an existing video.

    Only provided fields are updated; others remain unchanged.

    Args:
        video_id: YouTube video ID.
        title: New title (max 100 characters).
        description: New description (max 5,000 characters).
        tags: New tags (replaces existing tags).
        category_id: New category ID.
        privacy_status: "private", "public", or "unlisted".
        publish_at: ISO 8601 datetime to schedule publishing (requires privacy_status="private").
        made_for_kids: COPPA self-declaration (True/False).
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
        if privacy_status is not None:
            validate_privacy_status(privacy_status)
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("list")
    youtube = auth.build_youtube_service()

    current = youtube.videos().list(part="snippet,status", id=clean_id).execute()
    items = current.get("items", [])
    if not items:
        return {"error": f"Video not found: {clean_id}"}

    video = items[0]
    snippet = video["snippet"]
    status = video.get("status", {})

    if title is not None:
        snippet["title"] = title[:100]
    if description is not None:
        snippet["description"] = description[:5000]
    if tags is not None:
        snippet["tags"] = tags
    if category_id is not None:
        snippet["categoryId"] = category_id

    body: dict = {"id": clean_id, "snippet": snippet}

    if privacy_status is not None or publish_at is not None or made_for_kids is not None:
        effective_privacy = privacy_status or status.get("privacyStatus", "private")
        new_status: dict = {"privacyStatus": effective_privacy}
        if publish_at:
            if effective_privacy != "private":
                return {"error": "publish_at requires privacy_status='private'"}
            new_status["publishAt"] = publish_at
        if made_for_kids is not None:
            new_status["selfDeclaredMadeForKids"] = made_for_kids
        body["status"] = new_status
        parts = "snippet,status"
    else:
        parts = "snippet"

    quota.consume("update")
    response = youtube.videos().update(part=parts, body=body).execute()

    response_status = response.get("status") or {}
    return {
        "id": response["id"],
        "title": response["snippet"]["title"],
        "privacy": response_status.get("privacyStatus"),
        "publish_at": response_status.get("publishAt"),
        "updated": True,
    }


@mcp.tool(annotations=IDEMPOTENT_WRITE_ANNOTATIONS)
def youtube_set_thumbnail(video_id: str, file_path: str) -> dict:
    """Upload a custom thumbnail for a video (max 2 MB).

    Args:
        video_id: YouTube video ID.
        file_path: Path to the thumbnail image (JPEG, PNG, GIF, or BMP; max 2 MB).
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
        resolved_path = validate_media_path(
            file_path,
            allowed_dir=get_allowed_media_dir(),
            max_bytes=MAX_THUMBNAIL_BYTES,
        )
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("thumbnail_set")
    youtube = auth.build_youtube_service()

    media = MediaFileUpload(str(resolved_path))
    response = youtube.thumbnails().set(videoId=clean_id, media_body=media).execute()

    items = response.get("items", [])
    if items:
        return {
            "video_id": clean_id,
            "thumbnail_url": items[0].get("default", {}).get("url"),
            "updated": True,
        }

    return {"video_id": clean_id, "updated": True}


@mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS)
def youtube_delete_video(video_id: str, confirm: bool = False) -> dict:
    """Delete a video permanently. This action is irreversible.

    Args:
        video_id: YouTube video ID to delete.
        confirm: Must be True to execute the deletion. When False (default),
            returns a safety confirmation prompt without deleting anything.
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    if not confirm:
        return {
            "video_id": clean_id,
            "deleted": False,
            "confirmation_required": True,
            "message": (
                f"Deletion of video {clean_id!r} is permanent and irreversible. "
                "Re-run with confirm=True to proceed."
            ),
        }

    quota.consume("delete")
    youtube = auth.build_youtube_service()
    youtube.videos().delete(id=clean_id).execute()
    return {"video_id": clean_id, "deleted": True}

"""Comment tools: list, post, reply, and delete comments."""

from youtube_upload_mcp.server import (
    DESTRUCTIVE_ANNOTATIONS,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    auth,
    mcp,
    quota,
)
from youtube_upload_mcp.utils.validators import ValidationError, validate_youtube_id

_VALID_COMMENT_ORDERS = frozenset({"relevance", "time"})


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_list_comments(
    video_id: str,
    max_results: int = 20,
    order: str = "relevance",
) -> dict:
    """List top-level comments on a video.

    Args:
        video_id: YouTube video ID.
        max_results: Number of comment threads to return (0 or negative fetches all).
        order: Sort order: "relevance" or "time".
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    if order not in _VALID_COMMENT_ORDERS:
        return {"error": f"Invalid order {order!r}. Must be 'relevance' or 'time'."}

    youtube = auth.build_youtube_service()
    target = max_results if (max_results and max_results > 0) else None

    comments = []
    page_token: str | None = None
    response: dict = {}

    while True:
        page_size = 100 if target is None else min(100, target - len(comments))
        if page_size <= 0:
            break
        quota.consume("list")
        response = (
            youtube.commentThreads()
            .list(
                part="snippet",
                videoId=clean_id,
                maxResults=page_size,
                order=order,
                pageToken=page_token,
            )
            .execute()
        )
        for item in response.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "comment_id": item["snippet"]["topLevelComment"]["id"],
                "thread_id": item["id"],
                "author": top.get("authorDisplayName"),
                "text": top.get("textDisplay"),
                "likes": top.get("likeCount", 0),
                "published_at": top.get("publishedAt"),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
            })
        page_token = response.get("nextPageToken")
        if not page_token:
            break
        if target is not None and len(comments) >= target:
            break

    return {
        "video_id": clean_id,
        "comments": comments,
        "total": response.get("pageInfo", {}).get("totalResults", len(comments)),
    }


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_post_comment(video_id: str, text: str) -> dict:
    """Post a new top-level comment on a video.

    Args:
        video_id: YouTube video ID to comment on.
        text: Comment text.
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("insert")
    youtube = auth.build_youtube_service()

    body = {
        "snippet": {
            "videoId": clean_id,
            "topLevelComment": {
                "snippet": {"textOriginal": text},
            },
        },
    }
    response = youtube.commentThreads().insert(part="snippet", body=body).execute()

    top = response["snippet"]["topLevelComment"]["snippet"]
    return {
        "comment_id": response["snippet"]["topLevelComment"]["id"],
        "thread_id": response["id"],
        "text": top.get("textDisplay"),
        "video_id": clean_id,
        "posted": True,
    }


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_reply_to_comment(parent_id: str, text: str) -> dict:
    """Reply to an existing comment.

    Args:
        parent_id: Comment ID to reply to (from youtube_list_comments).
        text: Reply text.
    """
    try:
        clean_parent_id = validate_youtube_id(parent_id, "parent_id")
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("insert")
    youtube = auth.build_youtube_service()

    body = {
        "snippet": {
            "parentId": clean_parent_id,
            "textOriginal": text,
        },
    }
    response = youtube.comments().insert(part="snippet", body=body).execute()

    return {
        "reply_id": response["id"],
        "parent_id": clean_parent_id,
        "text": response["snippet"].get("textDisplay"),
        "posted": True,
    }


@mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS)
def youtube_delete_comment(comment_id: str, confirm: bool = False) -> dict:
    """Delete a comment permanently. This action is irreversible.

    Args:
        comment_id: Comment ID to delete.
        confirm: Must be True to execute the deletion.
    """
    try:
        clean_id = validate_youtube_id(comment_id, "comment_id")
    except ValidationError as e:
        return {"error": str(e)}

    if not confirm:
        return {
            "comment_id": clean_id,
            "deleted": False,
            "confirmation_required": True,
            "message": (
                f"Deletion of comment {clean_id!r} is permanent and irreversible. "
                "Re-run with confirm=True to proceed."
            ),
        }

    quota.consume("delete")
    youtube = auth.build_youtube_service()
    youtube.comments().delete(id=clean_id).execute()
    return {"comment_id": clean_id, "deleted": True}

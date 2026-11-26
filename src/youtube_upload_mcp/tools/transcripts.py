"""Transcript and caption tools."""

from youtube_upload_mcp.server import READ_ONLY_ANNOTATIONS, auth, mcp, quota
from youtube_upload_mcp.utils.validators import ValidationError, validate_youtube_id


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_list_captions(video_id: str) -> dict:
    """List available caption tracks for a video you own (requires OAuth)."""
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    quota.consume("list")
    youtube = auth.build_youtube_service()
    response = youtube.captions().list(part="snippet", videoId=clean_id).execute()

    tracks = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        tracks.append({
            "id": item["id"],
            "language": snippet.get("language"),
            "name": snippet.get("name"),
            "track_kind": snippet.get("trackKind"),
            "is_auto_synced": snippet.get("isAutoSynced"),
            "is_draft": snippet.get("isDraft"),
            "last_updated": snippet.get("lastUpdated"),
        })

    return {"video_id": clean_id, "tracks": tracks}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_get_transcript(
    video_id: str,
    language: str = "en",
    use_official_api: bool = False,
) -> dict:
    """Get transcript/captions for a video.

    Uses youtube-transcript-api by default (works for public videos, zero quota).
    Set use_official_api=True to use the official YouTube Data API (own videos).
    """
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    if use_official_api:
        return _get_transcript_official(clean_id, language)
    return _get_transcript_scraping(clean_id, language)


def _get_transcript_scraping(video_id: str, language: str) -> dict:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {
            "error": "youtube-transcript-api is not installed. "
            "Install it with: pip install youtube-transcript-api",
        }

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcript_list.find_transcript([language])
        except Exception:
            transcript = next(iter(transcript_list))
            if transcript.language_code != language:
                try:
                    transcript = transcript.translate(language)
                except Exception:
                    pass

        fetched = transcript.fetch()
        segments = [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in fetched
        ]
        full_text = " ".join(s.text for s in fetched)

        return {
            "video_id": video_id,
            "language": transcript.language_code,
            "is_generated": transcript.is_generated,
            "source": "youtube-transcript-api",
            "full_text": full_text,
            "segments": segments,
        }
    except Exception as e:
        return {
            "video_id": video_id,
            "error": f"Could not fetch transcript: {e}",
            "source": "youtube-transcript-api",
        }


def _get_transcript_official(video_id: str, language: str) -> dict:
    quota.consume("list")
    youtube = auth.build_youtube_service()

    response = youtube.captions().list(part="snippet", videoId=video_id).execute()
    items = response.get("items", [])
    if not items:
        return {"video_id": video_id, "error": "No captions found"}

    target_caption = next(
        (item for item in items if item.get("snippet", {}).get("language") == language),
        items[0],
    )

    quota.consume("list")
    caption_text = youtube.captions().download(id=target_caption["id"], tfmt="srt").execute()
    text = caption_text.decode("utf-8") if isinstance(caption_text, bytes) else caption_text

    return {
        "video_id": video_id,
        "language": target_caption["snippet"].get("language"),
        "track_kind": target_caption["snippet"].get("trackKind"),
        "source": "official_api",
        "full_text": text,
    }

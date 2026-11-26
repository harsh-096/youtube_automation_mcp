"""YouTube Analytics API tools."""

from collections import defaultdict
from datetime import date, timedelta

from youtube_upload_mcp.runtime import READ_ONLY_ANNOTATIONS, auth, mcp
from youtube_upload_mcp.utils.validators import ValidationError, validate_youtube_id


def _default_date_range(days: int = 28) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _run_analytics_query(
    metrics: str,
    dimensions: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
    filters: str | None = None,
    sort: str | None = None,
    max_results: int | None = None,
) -> dict:
    analytics = auth.build_youtube_analytics_service()

    if not start_date or not end_date:
        start_date, end_date = _default_date_range()

    params: dict = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": metrics,
    }
    if dimensions:
        params["dimensions"] = dimensions
    if filters:
        params["filters"] = filters
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = max_results

    response = analytics.reports().query(**params).execute()
    column_headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])
    results = [dict(zip(column_headers, row)) for row in rows]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "columns": column_headers,
        "results": results,
        "total_rows": len(results),
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_overview(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get channel-level analytics summary (views, watch time, subs, likes, comments, shares)."""
    return _run_analytics_query(
        metrics=(
            "views,estimatedMinutesWatched,averageViewDuration,"
            "subscribersGained,subscribersLost,likes,comments,shares"
        ),
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_top_videos(
    start_date: str | None = None,
    end_date: str | None = None,
    max_results: int = 20,
) -> dict:
    """Get top-performing videos by views (excluding Shorts)."""
    return _run_analytics_query(
        metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares",
        dimensions="video",
        filters="creatorContentType==video_on_demand",
        sort="-views",
        max_results=min(max_results, 200),
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_top_shorts(
    start_date: str | None = None,
    end_date: str | None = None,
    max_results: int = 20,
) -> dict:
    """Get top-performing Shorts by views."""
    return _run_analytics_query(
        metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares",
        dimensions="video",
        filters="creatorContentType==shorts",
        sort="-views",
        max_results=min(max_results, 200),
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_video_detail(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get daily analytics for a specific video."""
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    return _run_analytics_query(
        metrics=(
            "views,estimatedMinutesWatched,averageViewDuration,"
            "likes,comments,shares,subscribersGained,subscribersLost"
        ),
        dimensions="day",
        filters=f"video=={clean_id}",
        sort="day",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_traffic_sources(
    start_date: str | None = None,
    end_date: str | None = None,
    video_id: str | None = None,
) -> dict:
    """Get traffic source breakdown (search, suggested, browse, external, etc.)."""
    filters = None
    if video_id:
        try:
            clean_id = validate_youtube_id(video_id, "video_id")
            filters = f"video=={clean_id}"
        except ValidationError as e:
            return {"error": str(e)}

    return _run_analytics_query(
        metrics="views,estimatedMinutesWatched",
        dimensions="insightTrafficSourceType",
        filters=filters,
        sort="-views",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_demographics(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get audience age group and gender breakdown."""
    return _run_analytics_query(
        metrics="viewerPercentage",
        dimensions="ageGroup,gender",
        sort="-viewerPercentage",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_geography(
    start_date: str | None = None,
    end_date: str | None = None,
    max_results: int = 25,
) -> dict:
    """Get views and watch time by country."""
    return _run_analytics_query(
        metrics="views,estimatedMinutesWatched",
        dimensions="country",
        sort="-views",
        max_results=min(max_results, 200),
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_daily(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get daily performance metrics over time."""
    return _run_analytics_query(
        metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,likes,shares",
        dimensions="day",
        sort="day",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_day_of_week(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get average performance aggregated by day of the week."""
    if not start_date or not end_date:
        start_date, end_date = _default_date_range(days=90)

    raw = _run_analytics_query(
        metrics="views,estimatedMinutesWatched,likes,shares",
        dimensions="day",
        sort="day",
        start_date=start_date,
        end_date=end_date,
    )

    weekday_totals = defaultdict(
        lambda: {"views": 0, "minutes": 0, "likes": 0, "shares": 0, "days": 0}
    )
    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    for row in raw.get("results", []):
        day_str = row.get("day", "")
        if not day_str:
            continue
        parsed_day = date.fromisoformat(day_str)
        name = weekday_names[parsed_day.weekday()]
        weekday_totals[name]["views"] += row.get("views", 0)
        weekday_totals[name]["minutes"] += row.get("estimatedMinutesWatched", 0)
        weekday_totals[name]["likes"] += row.get("likes", 0)
        weekday_totals[name]["shares"] += row.get("shares", 0)
        weekday_totals[name]["days"] += 1

    results = []
    for name in weekday_names:
        totals = weekday_totals[name]
        n = totals["days"] or 1
        results.append({
            "day": name,
            "avg_views": round(totals["views"] / n, 1),
            "avg_minutes": round(totals["minutes"] / n, 1),
            "avg_likes": round(totals["likes"] / n, 1),
            "avg_shares": round(totals["shares"] / n, 1),
            "sample_days": totals["days"],
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "results": results,
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_content_type_breakdown(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Compare performance of Shorts vs long-form videos vs live streams."""
    if not start_date or not end_date:
        start_date, end_date = _default_date_range()

    content_types = {
        "shorts": "creatorContentType==shorts",
        "video_on_demand": "creatorContentType==video_on_demand",
        "live": "creatorContentType==live_stream",
    }

    results = {}
    for label, filter_str in content_types.items():
        try:
            data = _run_analytics_query(
                metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares",
                filters=filter_str,
                start_date=start_date,
                end_date=end_date,
            )
            if data.get("results"):
                results[label] = data["results"][0]
            else:
                results[label] = {"views": 0, "estimatedMinutesWatched": 0}
        except Exception:
            results[label] = {"error": "not available"}

    return {
        "start_date": start_date,
        "end_date": end_date,
        "breakdown": results,
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_revenue(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get revenue breakdown (requires YouTube Partner Program)."""
    try:
        return _run_analytics_query(
            metrics=(
                "estimatedRevenue,estimatedAdRevenue,"
                "grossRevenue,estimatedRedPartnerRevenue"
            ),
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        if "Forbidden" in str(e):
            return {
                "error": "Revenue data not available. Channel may not be monetized "
                "(YouTube Partner Program required)."
            }
        raise


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_revenue_by_video(
    start_date: str | None = None,
    end_date: str | None = None,
    max_results: int = 20,
) -> dict:
    """Get revenue per video, sorted by highest revenue."""
    try:
        return _run_analytics_query(
            metrics="estimatedRevenue,estimatedAdRevenue,grossRevenue",
            dimensions="video",
            sort="-estimatedRevenue",
            max_results=min(max_results, 200),
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        if "Forbidden" in str(e):
            return {
                "error": "Revenue data not available. Channel may not be monetized "
                "(YouTube Partner Program required)."
            }
        raise


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_analytics_retention(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Get audience retention curve for a specific video."""
    try:
        clean_id = validate_youtube_id(video_id, "video_id")
    except ValidationError as e:
        return {"error": str(e)}

    return _run_analytics_query(
        metrics="audienceWatchRatio,relativeRetentionPerformance",
        dimensions="elapsedVideoTimeRatio",
        filters=f"video=={clean_id}",
        sort="elapsedVideoTimeRatio",
        start_date=start_date,
        end_date=end_date,
    )

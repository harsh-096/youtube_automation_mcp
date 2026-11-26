"""YouTube Reporting API tools — bulk CSV exports with SSRF/token-leak protection."""

import urllib.request

from youtube_upload_mcp.server import READ_ONLY_ANNOTATIONS, WRITE_ANNOTATIONS, auth, mcp
from youtube_upload_mcp.utils.validators import (
    ValidationError,
    validate_googleapis_download_url,
    validate_youtube_id,
)


class _TrustedGoogleRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Ensure redirects during report download never leave trusted Google API hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_googleapis_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_reporting_list_types() -> dict:
    """List available YouTube bulk report types."""
    reporting = auth.build_youtube_reporting_service()
    response = reporting.reportTypes().list().execute()

    report_types = [
        {"id": rt["id"], "name": rt.get("name", "")}
        for rt in response.get("reportTypes", [])
    ]
    return {"report_types": report_types, "total": len(report_types)}


@mcp.tool(annotations=WRITE_ANNOTATIONS)
def youtube_reporting_create_job(report_type_id: str, name: str | None = None) -> dict:
    """Schedule a daily bulk reporting job."""
    try:
        clean_type_id = validate_youtube_id(report_type_id, "report_type_id")
    except ValidationError as e:
        return {"error": str(e)}

    reporting = auth.build_youtube_reporting_service()
    body: dict = {"reportTypeId": clean_type_id}
    if name:
        body["name"] = name

    response = reporting.jobs().create(body=body).execute()
    return {
        "job_id": response["id"],
        "report_type_id": response.get("reportTypeId"),
        "name": response.get("name"),
        "create_time": response.get("createTime"),
    }


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_reporting_list_jobs() -> dict:
    """List all active reporting jobs."""
    reporting = auth.build_youtube_reporting_service()
    response = reporting.jobs().list().execute()

    jobs = [
        {
            "job_id": job["id"],
            "report_type_id": job.get("reportTypeId"),
            "name": job.get("name"),
            "create_time": job.get("createTime"),
        }
        for job in response.get("jobs", [])
    ]
    return {"jobs": jobs, "total": len(jobs)}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_reporting_list_reports(job_id: str) -> dict:
    """List available reports for a reporting job."""
    try:
        clean_job_id = validate_youtube_id(job_id, "job_id")
    except ValidationError as e:
        return {"error": str(e)}

    reporting = auth.build_youtube_reporting_service()
    response = reporting.jobs().reports().list(jobId=clean_job_id).execute()

    reports = [
        {
            "report_id": report["id"],
            "start_time": report.get("startTime"),
            "end_time": report.get("endTime"),
            "create_time": report.get("createTime"),
            "download_url": report.get("downloadUrl"),
        }
        for report in response.get("reports", [])
    ]
    return {"job_id": clean_job_id, "reports": reports, "total": len(reports)}


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
def youtube_reporting_download(download_url: str) -> dict:
    """Download a report CSV from a trusted Google API HTTPS URL.

    Only https://*.googleapis.com URLs are permitted so OAuth tokens cannot
    be leaked to untrusted hosts.
    """
    try:
        safe_url = validate_googleapis_download_url(download_url)
    except ValidationError as e:
        return {"error": str(e)}

    credentials = auth.credentials
    headers = {"Authorization": f"Bearer {credentials.token}"}
    req = urllib.request.Request(safe_url, headers=headers)
    opener = urllib.request.build_opener(_TrustedGoogleRedirectHandler())

    try:
        with opener.open(req, timeout=60) as resp:
            content = resp.read().decode("utf-8")

        lines = content.strip().split("\n")
        header = lines[0] if lines else ""
        row_count = len(lines) - 1 if len(lines) > 1 else 0
        max_chars = 50_000

        return {
            "columns": header,
            "row_count": row_count,
            "truncated": len(content) > max_chars,
            "content": content[:max_chars],
        }
    except Exception as e:
        return {"error": f"Failed to download report: {e}"}

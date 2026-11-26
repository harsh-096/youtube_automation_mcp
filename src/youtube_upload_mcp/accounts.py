"""Multi-account manager for isolated OAuth credentials and daily quotas."""

import os
import shutil
import threading
from pathlib import Path

from youtube_upload_mcp.auth import DEFAULT_CONFIG_DIR, YouTubeAuth
from youtube_upload_mcp.utils.quota import QuotaTracker
from youtube_upload_mcp.utils.validators import (
    ValidationError,
    validate_account_name,
    validate_client_secret_file,
)


class AccountManager:
    """Manages multiple isolated YouTube OAuth accounts and per-account quotas.

    Layout under `base_config_dir` (default `~/.youtube-mcp`):
    - `"default"` account: `<base_config_dir>/{client_secret.json, token.json, quota.json}`
    - Named accounts: `<base_config_dir>/accounts/<name>/` containing
      `client_secret.json`, `token.json`, and `quota.json`.
      If a named account does not have its own `client_secret.json`, it falls back to
      `explicit_client_secret` or `<base_config_dir>/client_secret.json`.
    """

    def __init__(
        self,
        base_config_dir: str | Path | None = None,
        explicit_client_secret: str | Path | None = None,
        api_key: str | None = None,
        scope_profile: str | None = None,
        daily_quota: int = 10_000,
        initial_account: str = "default",
    ):
        self.base_config_dir = (
            Path(base_config_dir).expanduser() if base_config_dir else DEFAULT_CONFIG_DIR
        )
        self.accounts_root = self.base_config_dir / "accounts"
        self.explicit_client_secret = (
            Path(explicit_client_secret).expanduser() if explicit_client_secret else None
        )
        self.api_key = api_key
        self.scope_profile = scope_profile
        self.daily_quota = daily_quota

        self._lock = threading.RLock()
        self._cache: dict[str, tuple[YouTubeAuth, QuotaTracker]] = {}
        self._active_account = validate_account_name(initial_account)

    @property
    def active_account(self) -> str:
        with self._lock:
            return self._active_account

    def account_dir(self, name: str) -> Path:
        clean = validate_account_name(name)
        if clean == "default":
            return self.base_config_dir
        return self.accounts_root / clean

    def _resolve_client_secret(self, name: str, acc_dir: Path) -> Path:
        if name == "default":
            if self.explicit_client_secret:
                return self.explicit_client_secret
            return self.base_config_dir / "client_secret.json"

        account_secret = acc_dir / "client_secret.json"
        if account_secret.exists():
            return account_secret
        if self.explicit_client_secret:
            return self.explicit_client_secret
        return self.base_config_dir / "client_secret.json"

    def get_pair(self, name: str | None = None) -> tuple[YouTubeAuth, QuotaTracker]:
        with self._lock:
            target = validate_account_name(name) if name else self._active_account
            if target not in self._cache:
                acc_dir = self.account_dir(target)
                secret_path = self._resolve_client_secret(target, acc_dir)
                yt_auth = YouTubeAuth(
                    client_secret_path=secret_path,
                    config_dir=acc_dir,
                    api_key=self.api_key,
                    scope_profile=self.scope_profile,
                )
                tracker = QuotaTracker(
                    daily_limit=self.daily_quota,
                    state_path=acc_dir / "quota.json",
                )
                self._cache[target] = (yt_auth, tracker)
            return self._cache[target]

    @property
    def active_auth(self) -> YouTubeAuth:
        return self.get_pair()[0]

    @property
    def active_quota(self) -> QuotaTracker:
        return self.get_pair()[1]

    def switch_account(self, name: str) -> dict:
        """Switch the active account for this MCP session."""
        clean = validate_account_name(name)
        with self._lock:
            if clean != "default" and not self.account_dir(clean).exists():
                raise ValidationError(
                    f"Account {clean!r} does not exist. "
                    "Add it first with youtube_add_account."
                )
            self._active_account = clean
            self._cache.pop(clean, None)
            yt_auth, tracker = self.get_pair(clean)
            return {
                "active_account": clean,
                "config_dir": str(yt_auth.config_dir),
                "auth": yt_auth.status(),
                "quota": tracker.status(),
            }

    def add_account(
        self,
        name: str,
        client_secret_path: str | None = None,
        switch: bool = True,
    ) -> dict:
        """Register a named account profile, optionally copying its client_secret.json."""
        clean = validate_account_name(name)
        if clean == "default":
            raise ValidationError("Cannot overwrite reserved account name 'default'.")

        acc_dir = self.account_dir(clean)
        acc_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(acc_dir, 0o700)
        except OSError:
            pass

        copied_secret = False
        if client_secret_path:
            source = validate_client_secret_file(client_secret_path)
            dest = acc_dir / "client_secret.json"
            shutil.copyfile(source, dest)
            try:
                os.chmod(dest, 0o600)
            except OSError:
                pass
            copied_secret = True

        with self._lock:
            self._cache.pop(clean, None)
            if switch:
                self._active_account = clean
            yt_auth, tracker = self.get_pair(clean)
            return {
                "account": clean,
                "active": self._active_account == clean,
                "config_dir": str(acc_dir),
                "client_secret_copied": copied_secret,
                "auth": yt_auth.status(),
                "quota": tracker.status(),
            }

    def list_accounts(self) -> dict:
        """List all configured accounts, auth status, and remaining quota."""
        with self._lock:
            names: list[str] = ["default"]
            if self.accounts_root.exists():
                for entry in sorted(self.accounts_root.iterdir()):
                    if entry.is_dir():
                        names.append(entry.name)

            if self._active_account not in names:
                names.append(self._active_account)

            accounts = []
            for name in names:
                yt_auth, tracker = self.get_pair(name)
                auth_status = yt_auth.status()
                quota_status = tracker.status()
                accounts.append({
                    "name": name,
                    "active": name == self._active_account,
                    "authenticated": auth_status.get("authenticated", False),
                    "has_client_secret": yt_auth.client_secret_path.exists(),
                    "config_dir": str(yt_auth.config_dir),
                    "quota_used": quota_status["used"],
                    "quota_remaining": quota_status["remaining"],
                })

            return {
                "active_account": self._active_account,
                "accounts": accounts,
                "total": len(accounts),
            }

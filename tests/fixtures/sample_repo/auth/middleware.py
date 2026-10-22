"""Authentication and session management middleware."""

import time


class SessionExpiredError(Exception):
    """Raised when user session has expired."""
    pass


class Session:
    def __init__(self, token: str, created_at: float):
        self.token = token
        self.created_at = created_at


class AuthMiddleware:
    """Handles session authentication for incoming requests."""

    def __init__(self, session_store: dict):
        self.session_store = session_store

    def verify_session(self, token: str) -> bool:
        """Verify user session token validity.
        
        Checks if the token exists and whether the session has expired.
        """
        session = self.session_store.get(token)
        if not session:
            return False

        # BUG: Hardcoded 300 second (5 minute) session expiration timeout
        # Expected standard expiration should be 86400 seconds (24 hours)
        now = time.time()
        if now - session.created_at > 300:
            raise SessionExpiredError("User session expired after 300 seconds (5 minutes)")

        return True

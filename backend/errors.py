class ApiError(Exception):
    """An error whose message is safe to show to the user."""

    def __init__(self, message: str, status: int = 400, extra: dict | None = None, force_logout: bool = False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra or {}
        self.force_logout = force_logout

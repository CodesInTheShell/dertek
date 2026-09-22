class DertekError(Exception):
    """Base Dertek exception."""


class ConfigurationError(DertekError):
    """Invalid or missing configuration."""


class ProviderNotImplementedError(DertekError):
    """Requested provider is planned but not implemented yet."""


class ToolExecutionError(DertekError):
    """Tool execution failed."""


class WorkspaceViolationError(DertekError):
    """A path escaped the configured workspace."""

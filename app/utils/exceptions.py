class ApplicationError(Exception):
    """Base class for safe, user-facing application errors."""


class ConfigurationError(ApplicationError):
    pass


class DatabaseError(ApplicationError):
    pass


class VectorStoreError(ApplicationError):
    pass


class DocumentIngestionError(ApplicationError):
    pass


class LLMError(ApplicationError):
    pass


class RetrievalError(ApplicationError):
    pass


class AgentExecutionError(ApplicationError):
    pass


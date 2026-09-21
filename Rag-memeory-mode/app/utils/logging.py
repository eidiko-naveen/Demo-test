import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure one concise logging format for local and container execution."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )

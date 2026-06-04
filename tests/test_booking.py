from app.core.tools import make_registry
from app.database.db import DatabaseManager
from app.config import Settings


def test_booking_tools_not_registered(tmp_path):
    """Booking actions should not be available to the chat agent."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        pdf_output_dir=str(tmp_path / "pdfs"),
        rag_persist_dir=str(tmp_path / "rag"),
    )
    registry = make_registry(
        db=DatabaseManager(settings),
        rag_search_fn=lambda query, k=5: [],
    )

    tool_names = {tool.name for tool in registry.list()}

    assert "book_room" not in tool_names
    assert "get_booking" not in tool_names

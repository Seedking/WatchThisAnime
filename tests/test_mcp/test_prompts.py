"""MCP prompt tests."""

from src.mcp.prompts.recommend import recommend


def test_recommend_prompt_describes_tool_workflows() -> None:
    content = recommend()

    assert content
    assert "recommend_anime" in content
    assert "search_anime" in content
    assert "record_user_interaction" in content
    assert "user_id" in content

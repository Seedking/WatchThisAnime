"""recommend 提示模板：指导 LLM 如何使用推荐工具集。"""

from src.mcp.server import mcp


@mcp.prompt()
def recommend() -> str:
    """指导 LLM 如何使用推荐工具集。

    说明何时调用 ``recommend_anime``、如何用 ``record_user_interaction`` 反馈、
    冷启动与个性化两阶段的区别等。
    """
    return ""

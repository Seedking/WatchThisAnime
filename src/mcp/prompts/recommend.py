"""recommend 提示模板：指导 LLM 如何使用推荐工具集。"""

from src.mcp.server import mcp


@mcp.prompt()
def recommend() -> str:
    """指导 LLM 如何使用推荐工具集。

    说明何时调用 ``recommend_anime``、如何用 ``record_user_interaction`` 反馈、
    冷启动与个性化两阶段的区别等。
    """
    return (
        "推荐流程：当用户需要推荐且没有明确番名或标签时，调用 recommend_anime；"
        "搜索流程：当用户给出番名或标签时，调用 search_anime 查找候选；"
        "反馈流程：当用户表示看过、想看或给出评分时，调用 record_user_interaction。"
        "需要用户身份的工具都使用调用方提供的 user_id；服务端不鉴权。"
    )

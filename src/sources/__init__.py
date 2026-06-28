"""数据源层：对接 GitHub 数据集与 Bangumi / 萌娘百科 / Jikan 三来源 API。

各 client 均继承 ``src.utils.base_api_client.BaseAPIClient``，只需定义 ``base_url``
与 ``default_headers``；超时 / 并发限流 / 重试 / 异常包装由基类统一提供。
"""

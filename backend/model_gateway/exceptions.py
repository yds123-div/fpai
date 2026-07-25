"""model_gateway 异常基类。

独立模块以避免 ``gateway_model`` ↔ ``llm`` 之间的循环 import：
- ``gateway_model.GatewayChatModel`` 在熔断/fallback 耗尽时抛 ``ModelGatewayError``；
- ``llm.llm_chat`` 薄包装向调用者抛同款异常（对外契约不变）；
- 两者都从此处 import，无环。
"""


class ModelGatewayError(Exception):
    """模型网关调用异常（熔断打开、fallback 耗尽等）。"""

    pass


class ModelNotConfiguredError(ModelGatewayError):
    """未配置模型地址（无 base_url 且无 api_key）。"""

    pass

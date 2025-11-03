# Python 模型适配器框架

这是一个功能强大且可扩展的Python框架，用于与多个大型语言模型（LLM）提供商进行交互。它提供了一个统一的接口，可以智能地调度请求，处理故障转移，并估算成本，从而简化在应用程序中集成和管理不同AI模型的过程。

## 主要特性

- **统一接口**: 为所有支持的提供商（如Anthropic, OpenRouter, Ollama）提供单一、一致的API。
- **智能调度**: 根据成本、延迟和优先级自动选择最佳模型和提供商。
- **故障转移与重试**: 当首选提供商失败时，可自动切换到备用提供商，并内置请求重试逻辑。
- **可扩展架构**: 通过适配器模式和工厂模式，可以轻松添加对新AI提供商的支持。
- **成本估算**: 在发送请求前估算成本，帮助控制预算。
- **异步设计**: 基于 `asyncio` 构建，支持高并发场景。
- **本地模型支持**: 内置对Ollama的支持，可在本地运行和测试模型。

## 安装

1.  **克隆代码库**:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-url>
    ```

2.  **安装依赖**:
    该项目需要 `aiohttp`。
    ```bash
    pip install aiohttp
    ```

## 配置

在使用此框架之前，您需要配置API密钥。建议使用环境变量来管理密钥。

1.  **设置环境变量**:
    根据您希望使用的提供商，设置以下一个或多个环境变量：

    ```bash
    # 对于 Anthropic
    export ANTHROPIC_API_KEY="your_anthropic_api_key"

    # 对于 OpenRouter
    export OPENROUTER_API_KEY="your_openrouter_api_key"
    ```

    在Windows上，使用 `set` 而不是 `export`。

2.  **本地Ollama**:
    如果您希望使用Ollama，请确保Ollama服务正在本地运行。默认情况下，框架会尝试连接到 `http://localhost:11434`。

## 如何使用

`examples.py` 文件包含了详细的使用示例。以下是一个快速入门指南。

### 基础聊天请求

这是向默认提供商发送简单聊天请求的方法。

```python
import asyncio
from model_adapter import ModelScheduler, SchedulerConfig, RequestContext, ChatMessage, ProviderConfig

async def run_basic_chat():
    # 为提供商配置API密钥
    provider_configs = {
        "anthropic": ProviderConfig(api_key="your_anthropic_api_key"),
        "openrouter": ProviderConfig(api_key="your_openrouter_api_key"),
    }

    # 配置调度器
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter', 'ollama']
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()

    # 创建请求
    request = RequestContext(
        messages=[
            ChatMessage(role='user', content='你好，请用一句话介绍你自己。')
        ]
    )

    # 发送请求并获取响应
    response = await scheduler.chat(request)

    if response and response.choices:
        print(response.choices[0].message.content)

if __name__ == "__main__":
    asyncio.run(run_basic_chat())
```

### 流式响应

框架同样支持处理流式响应，这对于实时应用非常有用。

```python
async def run_stream_chat(scheduler: ModelScheduler):
    request = RequestContext(
        messages=[
            ChatMessage(role='user', content='写一首关于代码的短诗。')
        ],
        stream=True
    )

    print("Streaming response:")
    async for chunk in scheduler.chat_stream(request):
        content = chunk.choices[0].delta.get('content', '')
        if content:
            print(content, end='', flush=True)
    print()
```

## 运行示例

要运行 `examples.py` 文件中的所有演示：

1.  确保您已按照 **配置** 部分的说明设置了环境变量。
2.  运行脚本：
    ```bash
    python examples.py
    ```

脚本将依次演示基础聊天、流式聊天、错误处理和备用机制等功能。

## 框架结构

-   `model_adapter/`: 核心库代码。
    -   `interfaces.py`: 定义所有核心数据结构和接口 (e.g., `IModelAdapter`, `ChatMessage`)。
    -   `base.py`: 包含所有适配器的基类。
    -   `adapters/`: 包含每个提供商的具体实现。
    -   `factory.py`: 负责创建和注册适配器。
    -   `scheduler.py`: 核心调度逻辑，用于路由和决策。
-   `examples.py`: 可运行的示例代码。
-   `README.md`: 本文档。

import asyncio
import os
from typing import List

# Make sure to install necessary packages:
# pip install aiohttp

from model_adapter import (
    ModelScheduler, 
    SchedulerConfig, 
    RequestContext, 
    ChatMessage,
    ProviderConfig,
    ApiError,
    ChatChunk,
)

# --- Configuration ---
# It's recommended to use environment variables for API keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Provider-specific configurations
provider_configs = {
    "anthropic": ProviderConfig(api_key=ANTHROPIC_API_KEY),
    "openrouter": ProviderConfig(api_key=OPENROUTER_API_KEY),
    "ollama": ProviderConfig(base_url="http://localhost:11434"), # Default, but can be overridden
}


async def main():
    """
    Demonstrates basic usage, streaming, error handling, and advanced features.
    """
    print("--- Initializing Model Scheduler ---")
    # Configure the scheduler
    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter', 'ollama'],
        max_retries=2,
        retry_delay=1, # seconds
        cost_threshold=0.10  # $0.10 per request
    )
    
    scheduler = ModelScheduler(scheduler_config, provider_configs)
    await scheduler.initialize()
    
    print("\n--- 1. Basic Chat Example ---")
    await basic_chat_example(scheduler)
    
    print("\n--- 2. Streaming Chat Example ---")
    await stream_example(scheduler)
    
    print("\n--- 3. Error Handling and Fallback Example ---")
    await error_handling_example()

    print("\n--- 4. High Priority Request Example ---")
    await advanced_example(scheduler)

    print("\n--- 5. Batch Processing Example ---")
    await batch_example(scheduler)


async def basic_chat_example(scheduler: ModelScheduler):
    """Demonstrates a simple, non-streaming chat request."""
    try:
        request_context = RequestContext(
            messages=[
                ChatMessage(role='user', content='Hello, how are you today?')
            ],
            # model='claude-3-haiku-20240307', # You can specify a model
            temperature=0.7,
            max_tokens=50,
        )
        
        print(f"Sending request (default provider: {scheduler.config.default_provider})...")
        response = await scheduler.chat(request_context)
        
        if response and response.choices:
            print('Response:', response.choices[0].message.content)
            if response.usage:
                cost = scheduler.adapters[response.model.split('/')[0] if '/' in response.model else 'anthropic'].calculate_cost(response.model, response.usage)
                print(f"Usage: {response.usage.prompt_tokens}p + {response.usage.completion_tokens}c = {response.usage.total_tokens} tokens.")
                # Note: Cost calculation might not be accurate if pricing info isn't perfect
        else:
            print("Received no valid response.")

    except Exception as e:
        print(f"An error occurred during the basic chat example: {e}")


async def stream_example(scheduler: ModelScheduler):
    """Demonstrates handling a streaming chat response."""
    try:
        request_context = RequestContext(
            messages=[
                ChatMessage(role='user', content='Write a very short, two-line poem about coding.')
            ],
            # model='openrouter/google/gemini-flash-1.5',
            stream=True,
        )
        
        print("Streaming response...")
        full_response = ""
        async for chunk in scheduler.chat_stream(request_context):
            content = chunk.choices[0].delta.get('content', '') if chunk.choices and chunk.choices[0].delta else ''
            if content:
                print(content, end='', flush=True)
                full_response += content
        
        print() # Newline after stream finishes
        if not full_response:
            print("Stream finished with no content.")

    except Exception as e:
        print(f"An error occurred during the streaming example: {e}")


async def error_handling_example():
    """Demonstrates fallback mechanism on API error."""
    print("This example will simulate a failure with the primary provider (anthropic).")
    
    # Create a config with a fake API key for the default provider to force a failure
    invalid_provider_configs = {
        "anthropic": ProviderConfig(api_key="FAKE_KEY"),
        "openrouter": ProviderConfig(api_key=OPENROUTER_API_KEY),
        "ollama": ProviderConfig(),
    }

    scheduler_config = SchedulerConfig(
        default_provider='anthropic',
        fallback_providers=['openrouter', 'ollama'], # Ensure fallback is configured
        max_retries=1,
    )
    
    scheduler = ModelScheduler(scheduler_config, invalid_provider_configs)
    await scheduler.initialize()

    try:
        request_context = RequestContext(
            messages=[
                ChatMessage(role='user', content='Explain quantum computing in one sentence.')
            ],
        )
        
        # This should fail on 'anthropic' and fall back to 'openrouter' or 'ollama'
        response = await scheduler.chat(request_context)
        
        if response and response.choices:
            print(f"Fallback successful! Response from model '{response.model}':")
            print(response.choices[0].message.content)
        else:
            print("Fallback failed or returned no content.")

    except ApiError as error:
        print(f"Caught an API Error as expected. Status: {error.status}, Message: {error.message}")
    except Exception as error:
        print(f"An unexpected error occurred during the error handling example: {error}")


async def advanced_example(scheduler: ModelScheduler):
    """Demonstrates a high-priority request."""
    try:
        request_context = RequestContext(
            messages=[
                ChatMessage(role='user', content='Analyze this critical system log for anomalies: [ERROR] Service failed to restart.')
            ],
            priority='high', # High priority may influence scheduler choice
            max_tokens=200,
        )
        
        print("Sending high-priority request...")
        response = await scheduler.chat(request_context)
        
        if response and response.choices:
            print(f"Response from model '{response.model}':")
            print(response.choices[0].message.content)

    except Exception as e:
        print(f"An error occurred during the advanced example: {e}")


class BatchRequestProcessor:
    """Simple batch request processor."""
    def __init__(self, scheduler: ModelScheduler, concurrency: int = 3):
        self.scheduler = scheduler
        self.concurrency = concurrency
    
    async def process_batch(self, requests: List[RequestContext]) -> List[any]:
        """Processes a batch of requests concurrently."""
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def process_one(req):
            async with semaphore:
                return await self.scheduler.chat(req)

        tasks = [process_one(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

async def batch_example(scheduler: ModelScheduler):
    """Demonstrates processing multiple requests in a batch."""
    batch_processor = BatchRequestProcessor(scheduler, concurrency=2)
    
    batch_requests = [
        RequestContext(
            messages=[ChatMessage(role='user', content='What is TypeScript?')],
            max_tokens=50,
        ),
        RequestContext(
            messages=[ChatMessage(role='user', content='Explain React hooks in two sentences.')],
            max_tokens=50,
        ),
        RequestContext(
            messages=[ChatMessage(role='user', content='What is the capital of France?')],
            max_tokens=10,
        ),
    ]
    
    print(f"Processing {len(batch_requests)} requests in a batch...")
    batch_results = await batch_processor.process_batch(batch_requests)
    
    print("--- Batch Results ---")
    for i, result in enumerate(batch_results):
        print(f"Request {i+1}:")
        if isinstance(result, Exception):
            print(f"  -> Failed: {result}")
        elif result.choices:
            print(f"  -> Success from '{result.model}': {result.choices[0].message.content.strip()}")
        else:
            print("  -> No content in response.")
    print("---------------------")


if __name__ == "__main__":
    # To run this, make sure you have ANTHROPIC_API_KEY and/or OPENROUTER_API_KEY
    # set as environment variables.
    # You can also run a local Ollama instance.
    # Example:
    # export ANTHROPIC_API_KEY="your_key_here"
    # python examples.py
    
    # Check for at least one key
    if not ANTHROPIC_API_KEY and not OPENROUTER_API_KEY:
        print("Warning: ANTHROPIC_API_KEY and OPENROUTER_API_KEY are not set.")
        print("The examples may fail. Set them as environment variables to run.")
        # You can still run if you have Ollama running locally.

    asyncio.run(main())
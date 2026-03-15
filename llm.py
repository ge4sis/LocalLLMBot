import re
import json
from openai import AsyncOpenAI # type: ignore
import config # type: ignore
import mcp_client # type: ignore
from typing import Any

# Initialize AsyncOpenAI client configured for local LM Studio API
client = AsyncOpenAI(
    base_url=config.LM_STUDIO_BASE_URL,
    api_key=config.LM_STUDIO_API_KEY,
)

_mcp_manager: Any = None

async def generate_response(messages: list) -> str:
    """
    Sends the message history containing text and/or base64 images to the local LLM.
    Returns the string response from the LLM or a predefined error message.
    """
    global _mcp_manager
    if _mcp_manager is None:
        try:
            _mcp_manager = await mcp_client.init_mcp()
        except Exception as e:
            print(f"Failed to initialize MCP Manager: {e}")
            
    try:
        kwargs = {
            "model": "local-model",
            "messages": messages,
            "temperature": 0.7,
        }
        
        tools = []
        if _mcp_manager:
            tools = _mcp_manager.get_all_openai_tools()
            
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        response = await client.chat.completions.create(**kwargs)
        
        max_loops = 5
        loop_count = 0
        while response.choices[0].finish_reason == "tool_calls" and loop_count < max_loops:
            loop_count += 1
            tool_calls = response.choices[0].message.tool_calls
            messages.append(response.choices[0].message)
            
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}
                    
                print(f"Executing tool: {tool_name} with {tool_args}")
                if _mcp_manager:
                    result_text = await _mcp_manager.execute_tool_call(tool_name, tool_args) # type: ignore
                else:
                    result_text = "Error: MCP Manager not initialized."
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name, # Note: some clients require name in tool response
                    "content": str(result_text)
                })
                
            # Second call with the tool results
            response = await client.chat.completions.create(**kwargs)
        
        raw_response = response.choices[0].message.content or ""
        
        # 1. Remove <think>...</think> and <thought>...</thought> (handles unclosed tags too)
        cleaned_response = re.sub(r'<(?:think|thought)>.*?(?:</(?:think|thought)>|$)', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
        
        # 2. Handles custom "Thinking Process:" text block if separated by "---" (common in some prompts)
        if "Thinking Process:" in cleaned_response and "---" in cleaned_response:
            parts = cleaned_response.split("---", 1)
            if "Thinking Process:" in parts[0]:
                cleaned_response = parts[1]
                
        cleaned_response = cleaned_response.strip()
        
        # Fallback if the entire response was somehow inside the think tag or stripped entirely
        if not cleaned_response and raw_response:
            cleaned_response = raw_response
            
        return cleaned_response
    except Exception as e:
        # Standard fallback error message as requested in spec
        print(f"LLM Connection Error: {e}")
        return "현재 Mac Studio의 모델 서버가 꺼져 있어, 오빠."

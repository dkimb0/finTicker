from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse, ChatResponseMessage
from app.services.chat_service import chat

router = APIRouter(prefix="/tickers", tags=["chat"])


@router.post("/{symbol}/chat", response_model=ChatResponse)
async def chat_endpoint(symbol: str, request: ChatRequest) -> ChatResponse:
  result = await chat(symbol, request.messages)
  return ChatResponse(
    message=ChatResponseMessage(content=result["content"]),
    tool_calls_made=result["tool_calls_made"],
  )
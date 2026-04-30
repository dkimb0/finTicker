from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
  role: Literal["user", "assistant"]
  content: str


class ChatRequest(BaseModel):
  messages: list[ChatMessageIn] = Field(min_length=1)


class ChatResponseMessage(BaseModel):
  role: Literal["assistant"] = "assistant"
  content: str


class ChatResponse(BaseModel):
  message: ChatResponseMessage
  tool_calls_made: list[str] = Field(default_factory=list)
from pydantic import BaseModel
from typing import Optional

class TokenResponse(BaseModel):
    must_reset: bool = False
    reset_token: Optional[str] = None
    token: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None

print(TokenResponse(must_reset=True, reset_token="abc").model_dump())

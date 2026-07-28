from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional

class TokenResponse(BaseModel):
    must_reset: bool = False
    reset_token: Optional[str] = None
    token: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None

app = FastAPI()

@app.post("/login", response_model=TokenResponse)
def login():
    return TokenResponse(must_reset=True, reset_token="abc")

client = TestClient(app)
resp = client.post("/login")
print("STATUS:", resp.status_code)
print("BODY:", resp.json())

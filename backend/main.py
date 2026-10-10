from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USERS = [
    {"id": 1, "username": "student01", "password": "123456", "role": "student"},
    {"id": 2, "username": "admin", "password": "admin123", "role": "admin"},
]

class LoginIn(BaseModel):
    username: str
    password: str

@app.post("/api/login")
def login(data: LoginIn):
    for user in USERS:
        if user["username"] == data.username and user["password"] == data.password:
            return {
                "code": 0,
                "data":{
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["username"]
                }
            }
    return {"code": 1001, "message": "用户名或密码错误"}
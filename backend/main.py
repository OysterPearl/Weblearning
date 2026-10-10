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

# 题库测试数据（暂时写死在代码里，不用数据库）。
# 本轮只完成了前端界面骨架，还没有开放任何读写接口，这个列表先作为下一轮的数据种子就位：
# 之后的答题判分和题库增删改都直接读写它。存在进程内存中，重启即恢复初始数据。
QUESTIONS = [
    {
        "id": 1,
        "type": "single",
        "stem": "中国共产主义青年团成立于哪一年？",
        "options": {"A": "1919年", "B": "1920年", "C": "1922年", "D": "1949年"},
        "answer": "C",
    },
    {
        "id": 2,
        "type": "single",
        "stem": "中国共产主义青年团的团歌是？",
        "options": {
            "A": "《歌唱祖国》",
            "B": "《光荣啊，中国共青团》",
            "C": "《五月的花海》",
            "D": "《我们是共产主义接班人》",
        },
        "answer": "B",
    },
    {
        "id": 3,
        "type": "single",
        "stem": "申请加入中国共产主义青年团的年龄要求是？",
        "options": {
            "A": "12 周岁以上，25 周岁以下",
            "B": "14 周岁以上，28 周岁以下",
            "C": "16 周岁以上，30 周岁以下",
            "D": "18 周岁以上，28 周岁以下",
        },
        "answer": "B",
    },
    {
        "id": 4,
        "type": "single",
        "stem": "团旗左上角黄色圆圈环绕着五角星，其中的圆圈代表什么？",
        "options": {
            "A": "中国共产党的领导",
            "B": "青年一代紧密团结在中国共产党周围",
            "C": "青年群体的光明前景",
            "D": "工农联盟",
        },
        "answer": "B",
    },
    {
        "id": 5,
        "type": "single",
        "stem": "五四运动爆发于哪一年？",
        "options": {"A": "1915年", "B": "1919年", "C": "1921年", "D": "1922年"},
        "answer": "B",
    },
    {
        "id": 6,
        "type": "single",
        "stem": "团员在几人以上的单位，可以建立团支部？",
        "options": {"A": "3 人", "B": "5 人", "C": "10 人", "D": "30 人"},
        "answer": "A",
    },
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
                    "role": user["role"]
                }
            }
    return {"code": 1001, "message": "用户名或密码错误"}
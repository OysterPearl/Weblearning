import copy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

# ---------------------------------------------------------------------------
# 题库数据
#
# 不用数据库：题库就是下面这个内存列表，每次改动整体覆写到 data/questions.json，
# 重启后从文件读回来，所以管理员录的题不会丢。
# 想恢复成初始的 6 道题，删掉 data/questions.json 再重启即可。
#
# 注意：下面这些题库接口都**没有做身份校验**，任何能访问到后端的人都能改题库。
# 本地测试项目暂时这样，真正要部署时必须先在服务端校验管理员身份。
#
# 响应约定沿用 /api/login：HTTP 一律 200，靠 code 字段区分成败（0 为成功）。
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
QUESTIONS_FILE = DATA_DIR / "questions.json"

OPTION_LETTERS = ["A", "B", "C", "D"]

# 初始题库。只在 data/questions.json 不存在（首次运行，或你手动删掉）时使用。
SEED_QUESTIONS = [
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


def _write_questions(questions):
    """把整个题库覆写到文件。

    显式指定 utf-8：Windows 默认编码是 cp936，不写死会让中文题干乱码、
    甚至在写入时直接抛 UnicodeEncodeError。
    ensure_ascii=False 是为了让文件里存的是可读中文，而不是一堆 Unicode 转义序列，
    方便直接打开检查和手改。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUESTIONS_FILE.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_questions():
    """启动时载入题库。

    文件不存在就用种子数据建一份；文件损坏时也只打印警告并退回种子数据，
    不能因为一个坏掉的 JSON 就让整个服务起不来。
    """
    if not QUESTIONS_FILE.exists():
        _write_questions(SEED_QUESTIONS)
        return copy.deepcopy(SEED_QUESTIONS)

    try:
        questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"[警告] 题库文件读取失败，暂时改用种子数据：{QUESTIONS_FILE}（{exc}）")
        return copy.deepcopy(SEED_QUESTIONS)

    if not isinstance(questions, list):
        print(f"[警告] 题库文件格式不对（应当是列表），暂时改用种子数据：{QUESTIONS_FILE}")
        return copy.deepcopy(SEED_QUESTIONS)

    return questions


QUESTIONS = _load_questions()


class LoginIn(BaseModel):
    username: str
    password: str


class QuestionIn(BaseModel):
    stem: str
    options: dict[str, str] = Field(default_factory=dict)
    answer: str = ""
    type: str = "single"


def _validate_question(data, exclude_id=None):
    """校验并规范化一道题。

    返回 (题目字典, None)；校验不通过则返回 (None, 错误提示)。
    exclude_id 用于编辑场景——比对重复题干时跳过题目自己。
    """
    qtype = (data.type or "single").strip()
    if qtype != "single":
        return None, "目前只支持单选题"

    stem = data.stem.strip()
    if not stem:
        return None, "题干不能为空"

    # 选项键统一转大写，防止前端传了小写字母导致「A 未填写」这种莫名其妙的报错
    raw_options = {
        str(key).strip().upper(): str(value).strip()
        for key, value in (data.options or {}).items()
        if value is not None
    }
    options = {}
    for letter in OPTION_LETTERS:
        text = raw_options.get(letter, "")
        if text:
            options[letter] = text

    # A、B 必填，C、D 可以留空——留空的直接丢掉，这样也能录只有两个选项的题
    if "A" not in options or "B" not in options:
        return None, "选项 A 和选项 B 为必填"

    answer = (data.answer or "").strip().upper()
    if not answer:
        return None, "请选择正确答案"
    if answer not in options:
        return None, f"正确答案 {answer} 不在已填写的选项（{'/'.join(options)}）中"

    # 拦重复题干，防录题时手滑重复提交
    for existing in QUESTIONS:
        if existing["id"] != exclude_id and existing.get("stem", "").strip() == stem:
            return None, f"题库中已有相同题干的题目（编号 {existing['id']}）"

    return {"type": "single", "stem": stem, "options": options, "answer": answer}, None


def _question_not_found():
    return {"code": 1003, "message": "题目不存在，可能已被删除，请刷新列表"}


@app.post("/api/login")
def login(data: LoginIn):
    for user in USERS:
        if user["username"] == data.username and user["password"] == data.password:
            return {
                "code": 0,
                "data": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                },
            }
    return {"code": 1001, "message": "用户名或密码错误"}


@app.get("/api/questions")
def list_questions():
    return {"code": 0, "data": QUESTIONS}


@app.post("/api/questions")
def create_question(data: QuestionIn):
    question, error = _validate_question(data)
    if error:
        return {"code": 1002, "message": error}

    # 用「当前最大 id + 1」，而不是 len() + 1——删掉中间某题后 len 会撞上已有 id
    new_id = max((q["id"] for q in QUESTIONS), default=0) + 1
    question = {"id": new_id, **question}
    QUESTIONS.append(question)
    _write_questions(QUESTIONS)
    return {"code": 0, "data": question}


@app.put("/api/questions/{qid}")
def update_question(qid: int, data: QuestionIn):
    for index, existing in enumerate(QUESTIONS):
        if existing["id"] == qid:
            break
    else:
        return _question_not_found()

    question, error = _validate_question(data, exclude_id=qid)
    if error:
        return {"code": 1002, "message": error}

    QUESTIONS[index] = {"id": qid, **question}
    _write_questions(QUESTIONS)
    return {"code": 0, "data": QUESTIONS[index]}


@app.delete("/api/questions/{qid}")
def delete_question(qid: int):
    for index, existing in enumerate(QUESTIONS):
        if existing["id"] == qid:
            del QUESTIONS[index]
            _write_questions(QUESTIONS)
            return {"code": 0, "data": {"id": qid}}
    return _question_not_found()

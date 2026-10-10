import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 建表 + 首次播种。可以重复执行，已有数据不会被动。
db.init_db()

# 注意：下面这些题库接口都**没有做身份校验**，任何能访问到后端的人都能改题库。
# 本地测试项目暂时这样，真正要部署时必须先在服务端校验管理员身份。
#
# 响应约定沿用原来的：HTTP 一律 200，靠 code 字段区分成败（0 为成功）。
#   1001 用户名或密码错误   1002 字段校验失败   1003 题目不存在


class LoginIn(BaseModel):
    username: str
    password: str


class QuestionIn(BaseModel):
    stem: str
    options: dict[str, str] = Field(default_factory=dict)
    answer: str = ""
    type: str = "single"


def _row_to_question(row):
    """把数据库的一行还原成接口返回的形状。

    字段必须和迁移前完全一致（id / type / stem / options / answer），否则 admin.js 会挂。
    option_c、option_d 在库里是 NULL，这时就不放进 options 字典——
    「C、D 可以留空」这个行为要保住。
    """
    options = {}
    for letter in db.OPTION_LETTERS:
        value = row[f"option_{letter.lower()}"]
        if value:
            options[letter] = value

    return {
        "id": row["id"],
        "type": row["type"],
        "stem": row["stem"],
        "options": options,
        "answer": row["answer"],
    }


def _validate_payload(data):
    """纯字段校验，不碰数据库。

    返回 (规范化后的字段字典, None)；校验不通过则返回 (None, 错误提示)。
    数据库相关的检查（题干是否重复）不在这里，由调用方单独查。
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
    for letter in db.OPTION_LETTERS:
        text = raw_options.get(letter, "")
        if text:
            options[letter] = text

    # A、B 必填，C、D 可以留空——留空的存 NULL，这样也能录只有两个选项的题
    if "A" not in options or "B" not in options:
        return None, "选项 A 和选项 B 为必填"

    answer = (data.answer or "").strip().upper()
    if not answer:
        return None, "请选择正确答案"
    if answer not in options:
        return None, f"正确答案 {answer} 不在已填写的选项（{'/'.join(options)}）中"

    return {
        "type": "single",
        "stem": stem,
        "option_a": options["A"],
        "option_b": options["B"],
        "option_c": options.get("C"),
        "option_d": options.get("D"),
        "answer": answer,
    }, None


def _find_duplicate_stem(conn, stem, exclude_id=None):
    """找出占用了该题干的另一道题的 id，没有则返回 None。

    exclude_id 用于编辑场景——比对时跳过题目自己。
    数据库上还有 UNIQUE 约束兜底，这里查一遍是为了能给出带编号的中文提示。
    """
    if exclude_id is None:
        row = conn.execute("SELECT id FROM question WHERE stem = ?", (stem,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM question WHERE stem = ? AND id != ?", (stem, exclude_id)
        ).fetchone()
    return row["id"] if row else None


def _question_not_found():
    return {"code": 1003, "message": "题目不存在，可能已被删除，请刷新列表"}


@app.post("/api/login")
def login(data: LoginIn):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password, role FROM user WHERE username = ?",
            (data.username,),
        ).fetchone()
        user = dict(row) if row else None

    # 用户不存在和密码错误返回同一句提示，不泄漏「这个用户名存在」这个信息
    if user is None or not db.verify_password(data.password, user["password"]):
        return {"code": 1001, "message": "用户名或密码错误"}

    return {
        "code": 0,
        "data": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
    }


@app.get("/api/questions")
def list_questions():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM question ORDER BY id").fetchall()
        return {"code": 0, "data": [_row_to_question(row) for row in rows]}


@app.post("/api/questions")
def create_question(data: QuestionIn):
    fields, error = _validate_payload(data)
    if error:
        return {"code": 1002, "message": error}

    with db.get_conn() as conn:
        duplicate_id = _find_duplicate_stem(conn, fields["stem"])
        if duplicate_id is not None:
            return {
                "code": 1002,
                "message": f"题库中已有相同题干的题目（编号 {duplicate_id}）",
            }

        try:
            cursor = conn.execute(
                "INSERT INTO question "
                "(type, stem, option_a, option_b, option_c, option_d, answer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fields["type"],
                    fields["stem"],
                    fields["option_a"],
                    fields["option_b"],
                    fields["option_c"],
                    fields["option_d"],
                    fields["answer"],
                    db.now_iso(),
                ),
            )
        except sqlite3.IntegrityError:
            # 兜底：万一两个请求同时通过了上面的检查，由数据库的 UNIQUE 约束拦下来
            return {"code": 1002, "message": "题干与其他题目重复，请修改题干后重试"}

        row = conn.execute(
            "SELECT * FROM question WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return {"code": 0, "data": _row_to_question(row)}


@app.put("/api/questions/{qid}")
def update_question(qid: int, data: QuestionIn):
    fields, error = _validate_payload(data)
    if error:
        return {"code": 1002, "message": error}

    with db.get_conn() as conn:
        exists = conn.execute("SELECT id FROM question WHERE id = ?", (qid,)).fetchone()
        if exists is None:
            return _question_not_found()

        duplicate_id = _find_duplicate_stem(conn, fields["stem"], exclude_id=qid)
        if duplicate_id is not None:
            return {
                "code": 1002,
                "message": f"题库中已有相同题干的题目（编号 {duplicate_id}）",
            }

        try:
            # created_at 保持原值不动
            conn.execute(
                "UPDATE question SET type = ?, stem = ?, option_a = ?, option_b = ?, "
                "option_c = ?, option_d = ?, answer = ? WHERE id = ?",
                (
                    fields["type"],
                    fields["stem"],
                    fields["option_a"],
                    fields["option_b"],
                    fields["option_c"],
                    fields["option_d"],
                    fields["answer"],
                    qid,
                ),
            )
        except sqlite3.IntegrityError:
            return {"code": 1002, "message": "题干与其他题目重复，请修改题干后重试"}

        row = conn.execute("SELECT * FROM question WHERE id = ?", (qid,)).fetchone()
        return {"code": 0, "data": _row_to_question(row)}


@app.delete("/api/questions/{qid}")
def delete_question(qid: int):
    with db.get_conn() as conn:
        cursor = conn.execute("DELETE FROM question WHERE id = ?", (qid,))
        if cursor.rowcount == 0:
            return _question_not_found()
        return {"code": 0, "data": {"id": qid}}

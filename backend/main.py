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


class SubmitIn(BaseModel):
    user_id: int
    # {"题目id": "选项字母"}，没作答就传空字符串，但**不能少传这个 key**
    answers: dict[str, str] = Field(default_factory=dict)


def _row_options(row):
    """把 option_a ~ option_d 四列拼回 {"A": ..., "B": ...} 的字典。

    C、D 在库里是 NULL 时就不放进字典——「只录两个选项」这个行为要保住。
    """
    options = {}
    for letter in db.OPTION_LETTERS:
        value = row[f"option_{letter.lower()}"]
        if value:
            options[letter] = value
    return options


def _row_to_question(row):
    """把数据库的一行还原成管理端看到的形状（含答案）。

    字段必须和迁移前完全一致（id / type / stem / options / answer），否则 Admin.js 会挂。
    给学生的版本见 /api/quiz —— 那个**不含 answer**。
    """
    return {
        "id": row["id"],
        "type": row["type"],
        "stem": row["stem"],
        "options": _row_options(row),
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


# ---------------------------------------------------------------------------
# 学生端答题
#
# 判分放在后端做：下面 /api/quiz 返回的题目**不含 answer**，学生交卷后由这里比对。
# 如果把答案一起发给前端，按个 F12 就能看到全部正确答案，答题就没意义了。
#
# 身份说明：user_id 由前端从 localStorage 取出来传，**是可以伪造的**。
# 和上面的题库接口一样，服务端没有鉴权。本地测试可以，部署前必须补。
# ---------------------------------------------------------------------------


@app.get("/api/quiz")
def get_quiz():
    """随机抽一套题给学生。

    注意返回里**没有 answer 字段**。
    """
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM question ORDER BY RANDOM() LIMIT ?", (db.QUIZ_SIZE,)
        ).fetchall()

    return {
        "code": 0,
        "data": {
            "total": len(rows),
            "questions": [
                {
                    "id": row["id"],
                    "type": row["type"],
                    "stem": row["stem"],
                    "options": _row_options(row),
                }
                for row in rows
            ],
        },
    }


@app.post("/api/quiz/submit")
def submit_quiz(data: SubmitIn):
    with db.get_conn() as conn:
        user = conn.execute(
            "SELECT id FROM user WHERE id = ?", (data.user_id,)
        ).fetchone()
        if user is None:
            return {"code": 1004, "message": "用户不存在，请重新登录"}

        bank = conn.execute("SELECT * FROM question").fetchall()
        bank_by_id = {row["id"]: row for row in bank}

        expected = min(db.QUIZ_SIZE, len(bank))
        if expected == 0:
            return {"code": 1002, "message": "题库为空，暂时无法交卷"}

        # 防刷分：提交的题数必须正好等于一次抽题的题数。
        # 少了这条，只提交一道题并且答对就能拿 100 分，成绩记录就没意义了。
        if len(data.answers) != expected:
            return {
                "code": 1002,
                "message": f"本次应提交 {expected} 道题，收到 {len(data.answers)} 道，请刷新后重新答题",
            }

        details = []
        correct_count = 0

        for key, raw in data.answers.items():
            try:
                question_id = int(key)
            except (TypeError, ValueError):
                return {"code": 1002, "message": f"题目编号不合法：{key!r}"}

            row = bank_by_id.get(question_id)
            if row is None:
                return {
                    "code": 1002,
                    "message": f"题目 {question_id} 不存在，请刷新后重新答题",
                }

            options = _row_options(row)
            chosen = (raw or "").strip().upper()
            # 不在该题选项里的值（包括空字符串）一律当成「没作答」，不报错——
            # 没必要为脏数据再加一堆错误分支
            if chosen not in options:
                chosen = None

            is_correct = chosen is not None and chosen == row["answer"]
            if is_correct:
                correct_count += 1

            details.append(
                {
                    "question_id": question_id,
                    "stem": row["stem"],
                    "chosen": chosen,
                    "answer": row["answer"],
                    "is_correct": is_correct,
                }
            )

        total = len(details)
        score = round(correct_count / total * 100) if total else 0
        created_at = db.now_iso()

        cursor = conn.execute(
            "INSERT INTO exam_record (user_id, total, correct, score, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (data.user_id, total, correct_count, score, created_at),
        )
        exam_id = cursor.lastrowid

        conn.executemany(
            "INSERT INTO answer_detail "
            "(exam_id, question_id, chosen, is_correct, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    exam_id,
                    d["question_id"],
                    d["chosen"],
                    1 if d["is_correct"] else 0,
                    created_at,
                )
                for d in details
            ],
        )

    # 判分已经结束，这里把正确答案一并返回，供前端做逐题回顾
    return {
        "code": 0,
        "data": {
            "exam_id": exam_id,
            "total": total,
            "correct": correct_count,
            "score": score,
            "details": details,
        },
    }


@app.get("/api/students/{user_id}/stats")
def student_stats(user_id: int):
    """学生端的统计卡片。"""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*)                      AS exam_count, "
            "       COALESCE(SUM(correct), 0)     AS correct_sum, "
            "       COALESCE(SUM(total), 0)       AS total_sum, "
            "       COALESCE(AVG(score), 0)       AS avg_score, "
            "       COALESCE(MAX(score), 0)       AS best_score "
            "FROM exam_record WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        question_total = conn.execute("SELECT COUNT(*) FROM question").fetchone()[0]

    total_sum = row["total_sum"]

    return {
        "code": 0,
        "data": {
            "exam_count": row["exam_count"],
            "avg_score": round(row["avg_score"]),
            "best_score": row["best_score"],
            # 累计答对 / 累计作答，而不是各次正确率的平均
            "accuracy": round(row["correct_sum"] / total_sum * 100) if total_sum else 0,
            "question_total": question_total,
        },
    }


@app.get("/api/students/{user_id}/exams")
def student_exams(user_id: int):
    """学生的历史成绩，按时间倒序。

    created_at 只精确到秒，同一秒内交两次卷要靠 id 兜底排序。
    """
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, total, correct, score, created_at FROM exam_record "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()

    return {"code": 0, "data": [dict(row) for row in rows]}

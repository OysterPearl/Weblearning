"""数据库访问层：连接、建表、密码哈希、首次播种。

用 Python 自带的 sqlite3，不引入 ORM——表结构就这么两张，直接写 SQL 更直白，
也不用为了看数据多绕一层抽象。

注意 Python 3.14 上的两个坑：
  1. sqlite3.version 已被删除（3.12 弃用、3.14 移除），只能用 sqlite3.sqlite_version。
  2. datetime 的默认适配器同样已废弃，created_at 必须自己转成字符串再传进去，
     不能直接把 datetime 对象丢给 sqlite3。
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"

# 上一轮把题库存在这个 JSON 文件里。首次建库时如果它还在，就把它导入数据库，
# 免得你已经录过的题丢了。导入之后就不再读它了。
LEGACY_QUESTIONS_FILE = DATA_DIR / "questions.json"

OPTION_LETTERS = ["A", "B", "C", "D"]

PBKDF2_ITERATIONS = 260_000

# 每次答题最多抽多少道题。题库不足这个数就把题库整个抽出来。
QUIZ_SIZE = 10

# ---------------------------------------------------------------------------
# 初始数据。只在对应的表还是空的时候才写入。
# ---------------------------------------------------------------------------

SEED_USERS = [
    {"username": "student01", "password": "123456", "role": "student"},
    {"username": "admin", "password": "admin123", "role": "admin"},
]

SEED_QUESTIONS = [
    {
        "type": "single",
        "stem": "中国共产主义青年团成立于哪一年？",
        "option_a": "1919年",
        "option_b": "1920年",
        "option_c": "1922年",
        "option_d": "1949年",
        "answer": "C",
    },
    {
        "type": "single",
        "stem": "中国共产主义青年团的团歌是？",
        "option_a": "《歌唱祖国》",
        "option_b": "《光荣啊，中国共青团》",
        "option_c": "《五月的花海》",
        "option_d": "《我们是共产主义接班人》",
        "answer": "B",
    },
    {
        "type": "single",
        "stem": "申请加入中国共产主义青年团的年龄要求是？",
        "option_a": "12 周岁以上，25 周岁以下",
        "option_b": "14 周岁以上，28 周岁以下",
        "option_c": "16 周岁以上，30 周岁以下",
        "option_d": "18 周岁以上，28 周岁以下",
        "answer": "B",
    },
    {
        "type": "single",
        "stem": "团旗左上角黄色圆圈环绕着五角星，其中的圆圈代表什么？",
        "option_a": "中国共产党的领导",
        "option_b": "青年一代紧密团结在中国共产党周围",
        "option_c": "青年群体的光明前景",
        "option_d": "工农联盟",
        "answer": "B",
    },
    {
        "type": "single",
        "stem": "五四运动爆发于哪一年？",
        "option_a": "1915年",
        "option_b": "1919年",
        "option_c": "1921年",
        "option_d": "1922年",
        "answer": "B",
    },
    {
        "type": "single",
        "stem": "团员在几人以上的单位，可以建立团支部？",
        "option_a": "3 人",
        "option_b": "5 人",
        "option_c": "10 人",
        "option_d": "30 人",
        "answer": "A",
    },
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,
    role       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL DEFAULT 'single',
    stem       TEXT NOT NULL UNIQUE,
    option_a   TEXT NOT NULL,
    option_b   TEXT NOT NULL,
    option_c   TEXT,
    option_d   TEXT,
    answer     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 每次交卷一行。total / correct / score 是交卷那一刻算好写进来的**快照**，
-- 以后管理员改了题库，历史成绩也不会跟着变。
CREATE TABLE IF NOT EXISTS exam_record (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    total      INTEGER NOT NULL,
    correct    INTEGER NOT NULL,
    score      INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- 每次交卷里每道题的作答明细，用于逐题回顾。
-- ON DELETE CASCADE：删掉一道题会连带删掉它的作答明细（历史总分不受影响，总分是快照）。
CREATE TABLE IF NOT EXISTS answer_detail (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id     INTEGER NOT NULL REFERENCES exam_record(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES question(id) ON DELETE CASCADE,
    chosen      TEXT,
    is_correct  INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def now_iso():
    """当前的本地时间，ISO 8601 带时区偏移，例如 2026-10-10T15:04:05+08:00。

    带偏移量所以没有歧义，直接在数据库里看也是北京时间，不用心算 UTC。
    """
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def get_conn():
    """开一个数据库连接，用完就关。

    每次请求新建连接，而不是共享一个模块级连接：FastAPI 会把同步的路由函数丢进线程池执行，
    而 sqlite3 的连接默认不允许跨线程使用，共享连接会直接抛 ProgrammingError。
    连接本身开销很小，每题开一个最省心。

    正常退出时 commit，抛异常时 rollback。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite 默认不校验外键，而且这个开关是**每个连接**都要单独设的，
    # 漏掉的话 answer_detail 上的 ON DELETE CASCADE 不会生效。
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 密码
#
# 存储格式：pbkdf2_sha256$<轮数>$<盐的hex>$<哈希的hex>
# 每个密码用独立的随机盐，所以两个人用同样的密码，库里存的值也不一样。
# ---------------------------------------------------------------------------


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password, stored):
    """校验密码。stored 格式不对时返回 False，而不是抛异常炸掉登录接口。"""
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
    except (AttributeError, ValueError):
        return False

    # 用 compare_digest 而不是 ==，避免比较过程耗时随匹配长度变化而泄漏信息
    return hmac.compare_digest(digest.hex(), expected)


# ---------------------------------------------------------------------------
# 建表与播种
# ---------------------------------------------------------------------------


def _seed_users(conn):
    count = conn.execute("SELECT COUNT(*) FROM user").fetchone()[0]
    if count:
        return

    created_at = now_iso()
    conn.executemany(
        "INSERT INTO user (username, password, role, created_at) VALUES (?, ?, ?, ?)",
        [
            (u["username"], hash_password(u["password"]), u["role"], created_at)
            for u in SEED_USERS
        ],
    )
    print(f"[数据库] 已写入 {len(SEED_USERS)} 个初始账号")


def _load_legacy_questions():
    """读取上一轮遗留的 data/questions.json。读不到或格式不对就返回 None。"""
    if not LEGACY_QUESTIONS_FILE.exists():
        return None
    try:
        questions = json.loads(LEGACY_QUESTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"[数据库] 遗留题库文件读取失败，改用内置种子数据：{exc}")
        return None

    if not isinstance(questions, list) or not questions:
        return None

    # JSON 里是 {"options": {"A": ...}} 的嵌套结构，要摊平成四个字段
    converted = []
    for q in questions:
        options = q.get("options") or {}
        converted.append(
            {
                "type": q.get("type", "single"),
                "stem": q.get("stem", ""),
                "option_a": options.get("A"),
                "option_b": options.get("B"),
                "option_c": options.get("C"),
                "option_d": options.get("D"),
                "answer": q.get("answer", ""),
            }
        )
    return converted


def _seed_questions(conn):
    count = conn.execute("SELECT COUNT(*) FROM question").fetchone()[0]
    if count:
        return

    legacy = _load_legacy_questions()
    questions = legacy if legacy else SEED_QUESTIONS
    source = "遗留的 data/questions.json" if legacy else "内置种子数据"

    created_at = now_iso()
    conn.executemany(
        "INSERT INTO question "
        "(type, stem, option_a, option_b, option_c, option_d, answer, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                q["type"],
                q["stem"],
                q["option_a"],
                q["option_b"],
                q["option_c"],
                q["option_d"],
                q["answer"],
                created_at,
            )
            for q in questions
        ],
    )
    print(f"[数据库] 已从{source}导入 {len(questions)} 道题")


def init_db():
    """建表 + 首次播种。可以重复执行，已经存在的表和数据不会被动。"""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _seed_users(conn)
        _seed_questions(conn)


if __name__ == "__main__":
    init_db()
    print(f"[数据库] 位置：{DB_PATH}")

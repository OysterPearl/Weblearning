"""命令行建号工具。

密码改成哈希存储之后，没法再打开数据库手敲一个账号了，所以用这个小工具补上。

用法：
    python create_user.py <用户名> <密码> <角色>
    python create_user.py student02 123456 student
    python create_user.py teacher  888888 admin

已有的两个测试账号（密码照旧，只是库里存的是哈希）：
    student01 / 123456
    admin     / admin123
"""

import sqlite3
import sys

import db

VALID_ROLES = ("student", "admin")


def create_user(username, password, role):
    """成功返回 (True, 提示)，失败返回 (False, 原因)。"""
    username = username.strip()
    if not username:
        return False, "用户名不能为空"
    if not password:
        return False, "密码不能为空"
    if role not in VALID_ROLES:
        return False, f"角色只能是 {' 或 '.join(VALID_ROLES)}，收到的是「{role}」"

    try:
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO user (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                (username, db.hash_password(password), role, db.now_iso()),
            )
    except sqlite3.IntegrityError:
        return False, f"用户名「{username}」已经存在"

    return True, f"已创建 {role} 账号「{username}」"


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip())
        return 1

    db.init_db()
    ok, message = create_user(argv[1], argv[2], argv[3])
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

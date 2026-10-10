# 团青课堂答题系统

一个面向共青团知识学习的答题系统。学生登录后答题，管理员登录后维护题库。

> **当前状态**：登录、角色区分、管理员录题（增删改查）已经跑通并落到数据库。
> **学生端答题功能尚未实现**——详情见下面的[功能现状](#功能现状)。

---

## 技术栈

| 层 | 用了什么 | 说明 |
|---|---|---|
| 后端 | FastAPI + Uvicorn | 只作 JSON 接口，不渲染页面 |
| 数据库 | SQLite（Python 自带的 `sqlite3`） | 直连、手写 SQL，没有 ORM |
| 前端 | 原生 HTML / CSS / JavaScript | 无框架、无构建步骤，双击就能打开 |

没有 `package.json`，也不需要 `npm install`。前端就是几个静态文件。

---

## 目录结构

```
Weblearning/
├── backend/
│   ├── main.py             FastAPI 应用与全部路由
│   ├── db.py               数据库连接、建表、密码哈希、首次播种
│   ├── create_user.py      命令行建号工具
│   ├── data/
│   │   └── app.db          SQLite 数据库（自动生成，不进版本库）
│   └── venv/               虚拟环境
│
├── frontend/
│   ├── Login.html          【入口】登录页
│   ├── Home.html           路由页：登录成功后按角色分发
│   ├── Student.html        学生端
│   ├── Admin.html          管理员端
│   ├── Admin.js            管理员端逻辑（题库增删改查）
│   ├── Common.css          全部页面共用的样式
│   └── Common.js           全部页面共用的逻辑（鉴权、退出、请求封装）
│
└── README.md
```

> ⚠️ **前端没有 `index.html`，入口就是 `Login.html`**，直接双击它。
> 如果你用 `python -m http.server` 起静态服务，访问根路径 `/` 会看到目录列表，
> 需要手动访问 `/Login.html`。

---

## 快速开始

### 1. 启动后端

```bash
cd backend
venv/Scripts/python.exe -m uvicorn main:app --reload
```

看到 `Application startup complete.` 就是好了，服务在 `http://127.0.0.1:8000`。

> **Windows 用的是 `venv/Scripts/python.exe`**。如果你在 macOS / Linux 上跑，路径是 `venv/bin/python`。
>
> `--reload` 表示改动 `backend/` 下的 `.py` 文件会自动重启。**强烈建议加上**，
> 否则改了代码必须手动重启才生效（见[常见问题](#常见问题)）。

首次启动会自动创建 `backend/data/app.db`，建好两张表并写入初始数据。

### 2. 打开前端

直接双击 `frontend/Login.html`，用浏览器打开即可。

前端通过 `Common.js` 里的 `API_BASE` 访问后端，默认是 `http://127.0.0.1:8000`。
**换端口的话记得改这里。**

### 测试账号

| 用户名 | 密码 | 角色 | 登录后进入 |
|---|---|---|---|
| `student01` | `123456` | 学生 | `Student.html` |
| `admin` | `admin123` | 管理员 | `Admin.html` |

密码在数据库里是 **pbkdf2 哈希**，不是明文，所以不能直接改库加账号——用下面的 `create_user.py`。

---

## 功能现状

### ✅ 已完成

**登录与权限**

- 账号密码登录，密码用 pbkdf2 哈希校验
- 按角色自动跳转到对应页面（学生 → `Student.html`，管理员 → `Admin.html`）
- 访问隔离：学生手动打开 `Admin.html` 会被弹回 `Student.html`，反之亦然；未登录一律回 `Login.html`
- 退出登录

**管理员端（全部真实落库）**

- 题库列表从数据库读取
- 新增题目
- 编辑题目（点「编辑」把题目回填到表单，改完保存）
- 删除题目（有二次确认）
- 校验：题干必填、选项 A/B 必填（C/D 可留空）、答案必须在已填选项内、拒绝重复题干

### ❌ 未完成（重要）

- **学生端答题与判分完全没有实现。** `Student.html` 上的「开始答题」按钮只会弹一个「开发中」的提示，
  没有抽题、作答、提交、判分中的任何一步。
- **所有统计数字都是假的。** 学生端的「待答题数 / 平均分 / 正确率」和历史成绩表格、
  管理员端的「学生数 / 提交次数 / 待批阅」都是写死的示例数据。
  （管理员端的「题库总数」是真实的。）
- **接口没有服务端身份校验。** 任何人都能直接调 `POST/PUT/DELETE /api/questions` 改题库，
  前端的角色隔离只是跳转控制，改一下 `localStorage` 就能绕过。
  **本地测试可以，真要部署必须先在服务端补上鉴权。**
- 只支持单选题。

---

## 接口一览

所有接口的响应都是 **HTTP 200**，靠响应体里的 `code` 字段区分成败。

| code | 含义 |
|---|---|
| `0` | 成功 |
| `1001` | 用户名或密码错误 |
| `1002` | 字段校验失败（`message` 里有具体原因） |
| `1003` | 题目不存在（可能已被删除） |
| `-1` | 连不上后端（前端 `Common.js` 里兜底返回的） |

### `POST /api/login`

```json
请求：{ "username": "student01", "password": "123456" }
成功：{ "code": 0, "data": { "id": 1, "username": "student01", "role": "student" } }
失败：{ "code": 1001, "message": "用户名或密码错误" }
```

用户名不存在和密码错误返回**同一句提示**，不会泄漏某个用户名是否存在。

### `GET /api/questions`

```json
{ "code": 0, "data": [
  { "id": 1, "type": "single", "stem": "……",
    "options": { "A": "……", "B": "……", "C": "……", "D": "……" },
    "answer": "C" }
] }
```

`options` 里只会出现实际填了的选项——如果录题时 C、D 留空，这里就没有 C、D。

### `POST /api/questions`

```json
请求：{ "stem": "题干", "options": { "A": "…", "B": "…", "C": "…", "D": "…" }, "answer": "C", "type": "single" }
成功：{ "code": 0, "data": { ...新题目，含服务端分配的 id... } }
```

### `PUT /api/questions/{id}`

请求体同上。成功返回更新后的题目；id 不存在返回 `1003`。

### `DELETE /api/questions/{id}`

```json
成功：{ "code": 0, "data": { "id": 7 } }
```

> 交互式接口文档：后端跑起来后访问 <http://127.0.0.1:8000/docs>

---

## 数据库

位置：`backend/data/app.db`（已加入 `.gitignore`，不会进版本库）

### 表结构

```sql
CREATE TABLE user (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,          -- pbkdf2_sha256$轮数$盐$哈希
    role       TEXT NOT NULL,          -- student / admin
    created_at TEXT NOT NULL           -- ISO 8601，带时区，如 2026-10-10T15:06:08+08:00
);

CREATE TABLE question (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL DEFAULT 'single',
    stem       TEXT NOT NULL UNIQUE,
    option_a   TEXT NOT NULL,
    option_b   TEXT NOT NULL,
    option_c   TEXT,                   -- 可空：允许只录两个选项
    option_d   TEXT,
    answer     TEXT NOT NULL,          -- 单选存 "C"；以后多选可存 "AC"
    created_at TEXT NOT NULL
);
```

选项拆成 `option_a`~`option_d` 四列而不是存一段 JSON，这样能用 SQL 直接查。
`answer` 用 TEXT，以后加多选题存 `"AC"` 不用改表结构。

### 重置数据库

删掉 `backend/data/app.db` 再重启后端，会自动重新建表并写入初始数据。

```bash
rm backend/data/app.db
```

### 加账号

密码是哈希存的，不能直接改库，用 `create_user.py`：

```bash
cd backend
venv/Scripts/python.exe create_user.py <用户名> <密码> <角色>

# 例：加一个学生
venv/Scripts/python.exe create_user.py student02 123456 student
```

角色只能是 `student` 或 `admin`。用户名重复会报错（数据库上有 `UNIQUE` 约束）。

### 直接查库

```bash
cd backend
venv/Scripts/python.exe -c "import sqlite3; [print(r) for r in sqlite3.connect('data/app.db').execute('SELECT id, username, role FROM user')]"
```

---

## 常见问题

### 改了后端代码，但没生效

按顺序查这两条：

1. **端口是不是被残留进程占着。** 用 `--reload` 起 uvicorn 时，如果之前有一个没退干净的进程还占着 8000，
   新进程会绑定失败，而旧进程继续用**旧代码**应答，看起来就像"改了没生效"。

   ```bash
   netstat -ano | grep -E ':8000\s+0\.0\.0\.0:0\s+LISTENING'
   ```

   正常应该只有**一行**。出现多行就是有残留，用 `taskkill //PID <号> //F` 清掉再重启。

2. **新代码本身有没有语法错误。** `--reload` 遇到语法错误时不会把服务搞崩，
   表现是接口莫名 404，报错信息不显眼。直接编译一下最干脆：

   ```bash
   cd backend
   venv/Scripts/python.exe -m py_compile main.py && echo OK
   ```

### 中文乱码

Windows 上 Python 读写文件默认用 cp936，处理中文会乱码甚至抛 `UnicodeEncodeError`。
所有文件读写都要**显式指定 `encoding="utf-8"`**，`db.py` 里已经这么做了。

### `AttributeError: module 'sqlite3' has no attribute 'version'`

Python 3.12 弃用、3.14 移除了 `sqlite3.version`。用 `sqlite3.sqlite_version` 代替。

### 前端样式或脚本没加载

先确认后端在跑，再确认 `Common.js` 里的 `API_BASE` 指向的地址和端口正确。
页面上的提示文字（比如"无法连接后端服务"）会直接告诉你连不上。

---

## 待办

- [ ] 学生端答题：抽题、作答、提交
- [ ] 判分与成绩记录（需要新增一张 `answer_record` 表）
- [ ] 把两端写死的统计数字换成真实数据
- [ ] 接口的服务端身份校验（**部署前必须做**）
- [ ] 多选题 / 判断题

/* 团青课堂 —— 前端共用逻辑
 *
 * 登录态完全依赖 localStorage，用户是可以直接改写里面的 role 来伪装身份的。
 * 所以 requireLogin() 只是「跳转控制」，不是安全机制。
 * 真正的权限校验要等后端接口出来之后，在服务端按身份判断。
 */

const API_BASE = 'http://127.0.0.1:8000';

// 各角色的落地页。home.html 的路由和越权回跳都查这张表。
const ROLE_HOME = {
  student: 'student.html',
  admin: 'admin.html',
};

const ROLE_LABEL = {
  student: '学生',
  admin: '管理员',
};

/** 读取当前登录用户，未登录或数据被写坏时返回 null。 */
function getUser() {
  const raw = localStorage.getItem('user');
  if (!raw) return null;
  try {
    const user = JSON.parse(raw);
    return user && user.role ? user : null;
  } catch (e) {
    return null;
  }
}

/**
 * 页面入口守卫：未登录回登录页；已登录但角色不符，则送回他自己的页面
 * （学生手输 admin.html 会被弹回 student.html，反之亦然）。
 *
 * @param {'student'|'admin'} role 本页要求的角色
 * @returns {object|null} 通过校验时返回当前用户
 */
function requireLogin(role) {
  const user = getUser();

  if (!user) {
    window.location.replace('index.html');
    return null;
  }

  if (user.role !== role) {
    const home = ROLE_HOME[user.role];
    if (home) {
      window.location.replace(home);
    } else {
      // 角色对不上任何页面，清掉登录态重来，免得在两个页面之间来回跳成死循环
      localStorage.removeItem('user');
      window.location.replace('index.html');
    }
    return null;
  }

  return user;
}

function logout() {
  localStorage.removeItem('user');
  window.location.replace('index.html');
}

/**
 * fetch 封装：自动拼 API_BASE、带上 JSON 请求头并解析响应。
 *
 * 后端没启动时 fetch 会直接抛异常，这里统一兜住并转成 {code: -1}，
 * 这样各页面只判断 code 一处，就能覆盖「服务连不上」这个最常见的情况。
 * 返回值形状和 /api/login 一致：成功 code === 0，失败带 message。
 */
async function api(path, options = {}) {
  const { headers, ...rest } = options;

  let res;
  try {
    res = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json', ...headers },
      ...rest,
    });
  } catch (e) {
    return { code: -1, message: `无法连接后端服务（${API_BASE}），请确认它已经启动。` };
  }

  try {
    return await res.json();
  } catch (e) {
    return { code: -1, message: `后端返回了非 JSON 内容（HTTP ${res.status}）。` };
  }
}

/**
 * 把当前用户填进页面：所有带 data-user-name / data-role-label 的元素。
 * 建议在 HTML 里写上占位文字，这样 JS 没跑起来时页面也不至于空着。
 */
function fillUser(user) {
  document.querySelectorAll('[data-user-name]').forEach(function (el) {
    el.textContent = user.username;
  });
  document.querySelectorAll('[data-role-label]').forEach(function (el) {
    el.textContent = ROLE_LABEL[user.role] || user.role;
  });
}

/** 本轮只做了界面骨架，按钮还没有真实逻辑，统一给个提示。 */
function notReady(feature) {
  alert(feature + '功能正在开发中，本轮先完成界面部分。');
}

/* 管理员端 —— 题库录题（增删改查）
 *
 * 依赖 Common.js 提供的：requireLogin / getUser / fillUser / logout / api。
 * 页面的鉴权在 Admin.html 的 <head> 里已经做过了，这里只管录题逻辑。
 */

// 正在编辑的题目 id。null 表示「新增」模式。
let editingId = null;

const els = {};

document.addEventListener('DOMContentLoaded', init);

function init() {
  els.form = document.getElementById('question-form');
  els.formTitle = document.getElementById('form-title');
  els.stem = document.getElementById('stem');
  els.answer = document.getElementById('answer');
  els.optionInputs = {
    A: document.getElementById('opt-a'),
    B: document.getElementById('opt-b'),
    C: document.getElementById('opt-c'),
    D: document.getElementById('opt-d'),
  };
  els.saveBtn = document.getElementById('save-btn');
  els.cancelBtn = document.getElementById('cancel-edit-btn');
  els.formMsg = document.getElementById('form-msg');
  els.tbody = document.getElementById('question-tbody');
  els.listMsg = document.getElementById('list-msg');
  els.count = document.getElementById('question-count');

  els.form.addEventListener('submit', onSubmit);
  els.cancelBtn.addEventListener('click', onCancelEdit);

  const user = getUser();
  if (user) fillUser(user);

  loadQuestions();
}

/* ------------------------------ 提示消息 ------------------------------ */

function setMsg(el, text, kind) {
  el.textContent = text || '';
  el.className = 'form-msg' + (kind ? ' ' + kind : '');
}

/* ------------------------------ 数据读写 ------------------------------ */

async function loadQuestions() {
  const result = await api('/api/questions');

  if (result.code !== 0) {
    renderEmptyRow(result.message || '题库加载失败');
    els.count.textContent = '—';
    return;
  }

  renderQuestions(result.data);
  els.count.textContent = result.data.length;
}

/**
 * 渲染题库列表。
 *
 * 所有来自后端的内容（题干、选项）一律用 textContent 写入，不拼 innerHTML——
 * 题库是管理员手输的，拼字符串会留下 XSS 口子。
 */
function renderQuestions(questions) {
  els.tbody.textContent = '';

  if (!questions.length) {
    renderEmptyRow('题库还是空的，用上面的表单录第一道题吧。');
    return;
  }

  // 新录的排最前，方便确认刚才确实存进去了
  [...questions]
    .sort((a, b) => b.id - a.id)
    .forEach(function (q) {
      const tr = document.createElement('tr');

      tr.appendChild(makeCell(q.id));

      const typeCell = makeCell();
      typeCell.appendChild(makeTag('单选'));
      tr.appendChild(typeCell);

      const stemCell = makeCell(q.stem, 'stem-cell');
      tr.appendChild(stemCell);

      const answerCell = makeCell();
      answerCell.appendChild(makeTag(q.answer));
      tr.appendChild(answerCell);

      tr.appendChild(makeActionsCell(q));

      els.tbody.appendChild(tr);
    });
}

function renderEmptyRow(text) {
  els.tbody.textContent = '';
  const tr = document.createElement('tr');
  const cell = makeCell(text, 'empty-cell');
  cell.colSpan = 5;
  tr.appendChild(cell);
  els.tbody.appendChild(tr);
}

function makeCell(text, className) {
  const el = document.createElement('td');
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = text;
  return el;
}

function makeTag(text) {
  const span = document.createElement('span');
  span.className = 'tag';
  span.textContent = text;
  return span;
}

function makeActionsCell(q) {
  const cell = makeCell();
  const box = document.createElement('div');
  box.className = 'row-actions';

  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'btn';
  editBtn.textContent = '编辑';
  editBtn.addEventListener('click', function () {
    startEdit(q);
  });

  const deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'btn btn-danger';
  deleteBtn.textContent = '删除';
  deleteBtn.addEventListener('click', function () {
    onDelete(q);
  });

  box.appendChild(editBtn);
  box.appendChild(deleteBtn);
  cell.appendChild(box);
  return cell;
}

/* ------------------------------ 新增 / 编辑 ------------------------------ */

function readForm() {
  return {
    type: 'single',
    stem: els.stem.value.trim(),
    options: {
      A: els.optionInputs.A.value.trim(),
      B: els.optionInputs.B.value.trim(),
      C: els.optionInputs.C.value.trim(),
      D: els.optionInputs.D.value.trim(),
    },
    answer: els.answer.value,
  };
}

async function onSubmit(event) {
  event.preventDefault();

  const editing = editingId !== null;
  const payload = readForm();
  const targetId = editingId;

  setBusy(true);
  setMsg(els.formMsg, '');

  const result = editing
    ? await api(`/api/questions/${targetId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
    : await api('/api/questions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

  setBusy(false);

  if (result.code !== 0) {
    setMsg(els.formMsg, result.message || '保存失败', 'error');
    return;
  }

  const done = editing
    ? `已保存对编号 ${targetId} 的修改。`
    : `已新增题目（编号 ${result.data.id}）。`;

  exitEditMode();
  setMsg(els.formMsg, done, 'success');
  await loadQuestions();
}

function startEdit(q) {
  editingId = q.id;
  els.stem.value = q.stem;

  const options = q.options || {};
  ['A', 'B', 'C', 'D'].forEach(function (letter) {
    els.optionInputs[letter].value = options[letter] || '';
  });
  els.answer.value = q.answer;

  els.formTitle.textContent = `编辑题目（编号 ${q.id}）`;
  els.cancelBtn.classList.remove('hidden');
  updateSaveLabel();
  setMsg(els.formMsg, '');

  els.form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  els.stem.focus();
}

function onCancelEdit() {
  const id = editingId;
  exitEditMode();
  setMsg(els.formMsg, `已取消编辑编号 ${id}，回到新增模式。`);
}

/** 回到「新增」模式并清空表单。不碰提示文字，交给调用方决定说什么。 */
function exitEditMode() {
  editingId = null;
  els.form.reset();
  els.formTitle.textContent = '新增题目';
  els.cancelBtn.classList.add('hidden');
  updateSaveLabel();
}

function setBusy(busy) {
  els.saveBtn.disabled = busy;
  els.cancelBtn.disabled = busy;
  if (busy) {
    els.saveBtn.textContent = '保存中…';
  } else {
    updateSaveLabel();
  }
}

function updateSaveLabel() {
  els.saveBtn.textContent = editingId !== null ? '保存修改' : '保存题目';
}

/* -------------------------------- 删除 -------------------------------- */

async function onDelete(q) {
  const confirmed = confirm(`确定删除编号 ${q.id} 这道题吗？\n\n${q.stem}\n\n删除后无法恢复。`);
  if (!confirmed) return;

  const result = await api(`/api/questions/${q.id}`, { method: 'DELETE' });

  if (result.code !== 0) {
    setMsg(els.listMsg, result.message || '删除失败', 'error');
    return;
  }

  // 正在编辑的恰好是被删掉的那题，就退出编辑态，
  // 否则接着点「保存修改」会打到一个已经不存在的 id 上
  if (editingId === q.id) exitEditMode();

  setMsg(els.listMsg, `已删除题目（编号 ${q.id}）。`, 'success');
  await loadQuestions();
}

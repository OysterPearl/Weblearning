/* 学生端 —— 答题
 *
 * 依赖 Common.js 提供的：requireLogin / getUser / fillUser / logout / api。
 * 页面的鉴权在 Student.html 的 <head> 里已经做过了，这里只管答题逻辑。
 *
 * 判分在后端：/api/quiz 返回的题目**不含答案**，交卷后由 /api/quiz/submit 比对。
 * 所以这个文件里没有任何正确答案，F12 也看不到。
 *
 * 页面状态：idle（未开始）→ answering（答题中）→ result（已出分）
 */

let questions = [];   // 本次抽到的题
const answers = {};   // {题目id: "B"}

const els = {};

document.addEventListener('DOMContentLoaded', init);

function init() {
  els.startBtn = document.getElementById('start-btn');
  els.placeholder = document.getElementById('quiz-placeholder');
  els.placeholderMsg = document.getElementById('quiz-placeholder-msg');
  els.quizArea = document.getElementById('quiz-area');
  els.questionList = document.getElementById('question-list');
  els.progress = document.getElementById('quiz-progress');
  els.submitBtn = document.getElementById('submit-btn');
  els.resultArea = document.getElementById('result-area');
  els.resultSummary = document.getElementById('result-summary');
  els.resultDetails = document.getElementById('result-details');
  els.restartBtn = document.getElementById('restart-btn');
  els.historyBody = document.getElementById('history-tbody');
  els.statQuestionTotal = document.getElementById('stat-question-total');
  els.statExamCount = document.getElementById('stat-exam-count');
  els.statAvgScore = document.getElementById('stat-avg-score');
  els.statAccuracy = document.getElementById('stat-accuracy');

  els.startBtn.addEventListener('click', startQuiz);
  els.submitBtn.addEventListener('click', submitQuiz);
  els.restartBtn.addEventListener('click', function () {
    setIdle('点右上角「开始答题」，随机抽一套题。');
  });

  const user = getUser();
  if (user) fillUser(user);

  loadStats();
  loadHistory();
}

/* ------------------------------ 小工具 ------------------------------ */

function makeCell(text, className) {
  const el = document.createElement('td');
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = text;
  return el;
}

/** "2026-10-10T15:06:08+08:00" -> "2026-10-10 15:06"。直接切字符串，不做时区换算。 */
function formatTime(iso) {
  if (!iso || iso.length < 16) return iso || '';
  return iso.slice(0, 10) + ' ' + iso.slice(11, 16);
}

function rateOf(correct, total) {
  return total ? Math.round((correct / total) * 100) + '%' : '—';
}

function emptyRow(text) {
  const tr = document.createElement('tr');
  const cell = makeCell(text, 'empty-cell');
  cell.colSpan = 5;
  tr.appendChild(cell);
  return tr;
}

/* ------------------------------ 状态切换 ------------------------------ */

/** 回到「未开始」。message 显示在占位框里。 */
function setIdle(message) {
  questions = [];
  Object.keys(answers).forEach(function (key) {
    delete answers[key];
  });

  els.placeholderMsg.textContent = message;
  els.placeholder.classList.remove('hidden');
  els.quizArea.classList.add('hidden');
  els.resultArea.classList.add('hidden');
  els.startBtn.classList.remove('hidden');
  els.startBtn.disabled = false;
}

/* ------------------------------ 统计与历史 ------------------------------ */

async function loadStats() {
  const user = getUser();
  if (!user) return;

  const result = await api(`/api/students/${user.id}/stats`);
  if (result.code !== 0) return;

  const data = result.data;
  els.statQuestionTotal.textContent = data.question_total;
  els.statExamCount.textContent = data.exam_count;
  els.statAvgScore.textContent = data.avg_score;
  els.statAccuracy.textContent = data.accuracy;
}

async function loadHistory() {
  const user = getUser();
  if (!user) return;

  const result = await api(`/api/students/${user.id}/exams`);

  els.historyBody.textContent = '';

  if (result.code !== 0) {
    els.historyBody.appendChild(emptyRow(result.message || '历史成绩加载失败'));
    return;
  }
  if (!result.data.length) {
    els.historyBody.appendChild(emptyRow('还没有答题记录，开始第一次答题吧。'));
    return;
  }

  result.data.forEach(function (exam) {
    const tr = document.createElement('tr');
    tr.appendChild(makeCell(formatTime(exam.created_at)));
    tr.appendChild(makeCell(exam.total));
    tr.appendChild(makeCell(exam.score));
    tr.appendChild(makeCell(rateOf(exam.correct, exam.total)));

    const statusCell = makeCell();
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = '已完成';
    statusCell.appendChild(tag);
    tr.appendChild(statusCell);

    els.historyBody.appendChild(tr);
  });
}

/* ------------------------------ 抽题与作答 ------------------------------ */

async function startQuiz() {
  els.startBtn.disabled = true;
  els.startBtn.textContent = '抽题中…';

  const result = await api('/api/quiz');

  els.startBtn.disabled = false;
  els.startBtn.textContent = '开始答题';

  if (result.code !== 0) {
    setIdle(result.message || '抽题失败，请稍后再试。');
    return;
  }
  if (!result.data.total) {
    setIdle('题库还是空的，请联系管理员先录入题目。');
    return;
  }

  questions = result.data.questions;
  Object.keys(answers).forEach(function (key) {
    delete answers[key];
  });

  renderQuestions();
  updateProgress();

  els.placeholder.classList.add('hidden');
  els.resultArea.classList.add('hidden');
  els.quizArea.classList.remove('hidden');
  els.startBtn.classList.add('hidden');

  els.quizArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * 渲染题目。
 *
 * 题干和选项都是管理员手输的，一律用 textContent 写入、用 createElement 建节点，
 * 不拼 innerHTML——和 Admin.js 保持一致，不留 XSS 口子。
 */
function renderQuestions() {
  els.questionList.textContent = '';

  questions.forEach(function (q, index) {
    const card = document.createElement('div');
    card.className = 'quiz-question';

    const stem = document.createElement('p');
    stem.className = 'quiz-stem';
    stem.textContent = (index + 1) + '. ' + q.stem;
    card.appendChild(stem);

    const optionList = document.createElement('div');
    optionList.className = 'quiz-options';

    Object.keys(q.options).forEach(function (letter) {
      const label = document.createElement('label');
      label.className = 'quiz-option';

      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'question-' + q.id;
      radio.value = letter;
      radio.addEventListener('change', function () {
        answers[q.id] = letter;
        updateProgress();
      });

      const text = document.createElement('span');
      text.textContent = letter + '. ' + q.options[letter];

      label.appendChild(radio);
      label.appendChild(text);
      optionList.appendChild(label);
    });

    card.appendChild(optionList);
    els.questionList.appendChild(card);
  });
}

function updateProgress() {
  const done = questions.filter(function (q) {
    return answers[q.id];
  }).length;

  els.progress.textContent = '已作答 ' + done + ' / ' + questions.length + ' 道';
  els.progress.classList.toggle('all-done', questions.length > 0 && done === questions.length);
}

/* ------------------------------ 交卷与结果 ------------------------------ */

async function submitQuiz() {
  const user = getUser();
  if (!user) return;

  const unanswered = questions.filter(function (q) {
    return !answers[q.id];
  }).length;

  if (unanswered && !confirm('还有 ' + unanswered + ' 道题没作答，未作答会算错。确定交卷吗？')) {
    return;
  }

  // 每道题都要出现在 answers 里，没作答的传空字符串——后端按题数校验
  const payload = { user_id: user.id, answers: {} };
  questions.forEach(function (q) {
    payload.answers[q.id] = answers[q.id] || '';
  });

  els.submitBtn.disabled = true;
  els.submitBtn.textContent = '判分中…';

  const result = await api('/api/quiz/submit', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  els.submitBtn.disabled = false;
  els.submitBtn.textContent = '交卷';

  if (result.code !== 0) {
    alert(result.message || '交卷失败，请稍后再试。');
    return;
  }

  showResult(result.data);

  // 交卷后统计和历史成绩都变了，重新拉一次
  loadStats();
  loadHistory();
}

function showResult(data) {
  els.resultSummary.textContent = '';

  const score = document.createElement('div');
  score.className = 'result-score';
  score.textContent = data.score;
  const unit = document.createElement('small');
  unit.textContent = ' 分';
  score.appendChild(unit);

  const desc = document.createElement('p');
  desc.className = 'result-desc';
  desc.textContent = '共 ' + data.total + ' 道题，答对 ' + data.correct + ' 道。';

  els.resultSummary.appendChild(score);
  els.resultSummary.appendChild(desc);

  els.resultDetails.textContent = '';

  data.details.forEach(function (d, index) {
    const item = document.createElement('div');
    item.className = 'result-item ' + (d.is_correct ? 'correct' : 'wrong');

    const stem = document.createElement('p');
    stem.className = 'result-stem';
    stem.textContent = (index + 1) + '. ' + d.stem;
    item.appendChild(stem);

    const line = document.createElement('p');
    line.className = 'result-line';
    line.textContent = d.is_correct
      ? '你的答案：' + d.chosen + '　✓ 答对了'
      : '你的答案：' + (d.chosen || '未作答') + '　✗ 正确答案：' + d.answer;
    item.appendChild(line);

    els.resultDetails.appendChild(item);
  });

  els.quizArea.classList.add('hidden');
  els.resultArea.classList.remove('hidden');
  els.resultArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

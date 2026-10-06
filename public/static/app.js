const STORAGE_KEY = 'stillpoint-reflections-v1';
const chatBox = document.querySelector('#chat-messages');
const input = document.querySelector('#chat-input');
const form = document.querySelector('#chat-form');
const sendButton = document.querySelector('.send-button');
let conversation = [];

function makeMessage(role, content, sources = [], typing = false) {
  const row = document.createElement('div');
  row.className = `message ${role === 'user' ? 'user-message' : 'assistant-message'}${typing ? ' typing' : ''}`;
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? 'Y' : 's';
  const wrap = document.createElement('div');
  wrap.className = 'bubble-wrap';
  const speaker = document.createElement('span');
  speaker.className = 'speaker';
  speaker.textContent = role === 'user' ? 'YOU' : 'STILLPOINT · AI REFLECTION';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = content;
  if (sources.length) {
    const answerLayout = document.createElement('div');
    answerLayout.className = 'answer-layout';
    answerLayout.append(bubble);
    const sourceBox = document.createElement('div');
    sourceBox.className = 'sources';
    const heading = document.createElement('strong');
    heading.textContent = 'DOCUMENTED PASSAGE';
    sourceBox.append(heading);
    sources.forEach((source) => {
      const link = document.createElement('a');
      link.href = source.url || '#';
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = `${source.title || 'Source passage'}${source.topic ? ` · ${source.topic}` : ''} ↗`;
      sourceBox.append(link);
      if (source.excerpt) {
        const excerpt = document.createElement('div');
        excerpt.textContent = `“${source.excerpt}${source.excerpt.length >= 340 ? '…' : ''}”`;
        sourceBox.append(excerpt);
      }
    });
    const label = document.createElement('span');
    label.className = 'interpretation-label';
    label.textContent = 'The reflection above is AI generated; the excerpt and source are from the writings.';
    sourceBox.append(label);
    answerLayout.append(sourceBox);
    wrap.append(speaker, answerLayout);
  } else {
    wrap.append(speaker, bubble);
  }
  row.append(avatar, wrap);
  return { row, bubble };
}

function renderConversation() {
  chatBox.replaceChildren();
  if (!conversation.length) {
    const { row } = makeMessage('assistant', 'Welcome. What’s been weighing on you lately? We can take it one step at a time.');
    row.querySelector('.speaker').textContent = 'STILLPOINT';
    row.querySelector('time')?.remove();
    chatBox.append(row);
    return;
  }
  for (const item of conversation) {
    const { row } = makeMessage(item.role, item.content, item.sources || []);
    chatBox.append(row);
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

function saveConversation() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversation));
}

try {
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  if (Array.isArray(stored)) conversation = stored.filter((item) => ['user', 'assistant'].includes(item.role) && typeof item.content === 'string');
} catch { conversation = []; }
renderConversation();

async function sendMessage(text) {
  const message = text.trim();
  if (!message || sendButton.disabled) return;
  document.querySelector('#suggestions').classList.add('hidden');
  conversation.push({ role: 'user', content: message });
  const userNode = makeMessage('user', message).row;
  chatBox.append(userNode);
  const assistant = makeMessage('assistant', 'Gathering a reflection…', [], true);
  chatBox.append(assistant.row);
  chatBox.scrollTop = chatBox.scrollHeight;
  input.value = '';
  input.style.height = '35px';
  sendButton.disabled = true;
  let responseText = '';
  let foundSources = [];
  try {
    const history = conversation.slice(-10).map(({ role, content }) => ({ role, content }));
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history: history.slice(0, -1) }),
    });
    if (!response.ok || !response.body) throw new Error('The reflection service is unavailable. Please try again in a moment.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        const event = block.match(/^event: (.+)$/m)?.[1];
        const data = block.match(/^data: (.+)$/m)?.[1];
        if (!data) continue;
        if (event === 'sources') {
          foundSources = JSON.parse(data);
          assistant.row.remove();
          const replacement = makeMessage('assistant', '', foundSources);
          assistant.row = replacement.row;
          assistant.bubble = replacement.bubble;
          chatBox.append(assistant.row);
        } else if (event === 'token') {
          responseText += JSON.parse(data);
          assistant.bubble.textContent = responseText;
          assistant.row.classList.remove('typing');
          chatBox.scrollTop = chatBox.scrollHeight;
        }
      }
      if (done) break;
    }
    if (!responseText) responseText = 'I’m here with you. Could you share a little more about what feels hardest right now?';
    assistant.bubble.textContent = responseText;
    assistant.row.classList.remove('typing');
    conversation.push({ role: 'assistant', content: responseText, sources: foundSources });
    saveConversation();
  } catch (error) {
    assistant.bubble.textContent = error.message || 'Something went wrong. Please try again.';
    assistant.row.classList.remove('typing');
    conversation.pop();
    saveConversation();
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => { event.preventDefault(); sendMessage(input.value); });
input.addEventListener('input', () => { input.style.height = '35px'; input.style.height = `${Math.min(input.scrollHeight, 110)}px`; });
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendMessage(input.value);
  }
});
document.querySelectorAll('.suggestions button').forEach((button) => button.addEventListener('click', () => sendMessage(button.textContent)));
document.querySelector('#clear-chat').addEventListener('click', () => {
  conversation = [];
  localStorage.removeItem(STORAGE_KEY);
  document.querySelector('#suggestions').classList.remove('hidden');
  renderConversation();
});

const titles = { mentor: 'What’s on your mind?', practice: 'Make space to feel a little steadier.', quiz: 'Explore a teaching, then make it your own.' };
document.querySelectorAll('.nav-link').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.nav-link').forEach((nav) => nav.classList.toggle('active', nav === button));
  document.querySelectorAll('.view-panel').forEach((view) => view.classList.toggle('hidden', view.id !== `view-${button.dataset.view}`));
  document.querySelector('#section-title').textContent = titles[button.dataset.view];
  if (button.dataset.view === 'quiz' && !quizLoaded) loadQuiz();
  window.scrollTo({ top: document.querySelector('.content-wrap').offsetTop - 8, behavior: 'smooth' });
}));

async function refreshQuote() {
  const queries = ['fear courage self confidence', 'strength weakness effort', 'education knowledge character', 'perseverance work goal'];
  const query = queries[Math.floor(Math.random() * queries.length)];
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    if (!data.length) return;
    const source = data[Math.floor(Math.random() * Math.min(data.length, 3))];
    const card = document.querySelector('#featured-quote');
    card.replaceChildren();
    const mark = document.createElement('span'); mark.className = 'quote-mark'; mark.textContent = '“';
    const excerpt = document.createElement('p'); excerpt.textContent = source.excerpt + (source.excerpt.length >= 340 ? '…' : '');
    const attribution = document.createElement('div'); attribution.className = 'quote-attribution'; attribution.textContent = '— Swami Vivekananda';
    const sourceLine = document.createElement('div'); sourceLine.className = 'quote-source-note';
    sourceLine.append(document.createTextNode('Documented excerpt · '));
    const link = document.createElement('a'); link.href = source.url || '#'; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = `${source.title} ↗`;
    sourceLine.append(link);
    card.append(mark, excerpt, attribution, sourceLine);
  } catch { /* Keep the bundled, cited excerpt visible when offline. */ }
}
document.querySelector('#new-quote').addEventListener('click', refreshQuote);
refreshQuote();

let quizQuestions = [];
let quizIndex = 0;
let quizScore = 0;
let quizSelected = false;
let quizLoaded = false;
async function loadQuiz() {
  quizLoaded = true;
  try {
    const response = await fetch('/api/quiz');
    quizQuestions = await response.json();
    quizIndex = 0; quizScore = 0;
    renderQuiz();
  } catch { document.querySelector('#quiz-content').textContent = 'The quiz could not load. Please try again.'; }
}
function renderQuiz() {
  const root = document.querySelector('#quiz-content');
  root.replaceChildren();
  if (quizIndex >= quizQuestions.length) {
    const eyebrow = document.createElement('div'); eyebrow.className = 'eyebrow'; eyebrow.textContent = 'A MOMENT TO REFLECT';
    const title = document.createElement('h3'); title.className = 'quiz-question'; title.textContent = `You explored ${quizQuestions.length} ideas.`;
    const score = document.createElement('p'); score.className = 'grounding-card'; score.textContent = `You found ${quizScore} thoughtful answer${quizScore === 1 ? '' : 's'}. There’s no score for living these ideas perfectly. What is one you’d like to carry with you?`;
    const again = document.createElement('button'); again.className = 'primary-button'; again.textContent = 'Reflect again'; again.addEventListener('click', () => { quizIndex = 0; quizScore = 0; renderQuiz(); });
    root.append(eyebrow, title, score, again); return;
  }
  const item = quizQuestions[quizIndex];
  const progressText = document.createElement('div'); progressText.className = 'quiz-progress'; progressText.textContent = `QUESTION ${String(quizIndex + 1).padStart(2, '0')} OF ${String(quizQuestions.length).padStart(2, '0')}`;
  const track = document.createElement('div'); track.className = 'progress-track';
  const fill = document.createElement('span'); fill.style.width = `${(quizIndex / quizQuestions.length) * 100}%`; track.append(fill);
  const question = document.createElement('h3'); question.className = 'quiz-question'; question.textContent = item.question;
  const options = document.createElement('div'); options.className = 'quiz-options';
  const feedback = document.createElement('div'); feedback.className = 'quiz-feedback hidden';
  item.options.forEach((option, index) => {
    const button = document.createElement('button'); button.className = 'quiz-option'; button.textContent = `${String.fromCharCode(65 + index)}.  ${option}`;
    button.addEventListener('click', () => {
      if (quizSelected) return;
      quizSelected = true;
      const correct = index === item.answer;
      if (correct) quizScore++;
      button.classList.add(correct ? 'correct' : 'wrong');
      options.querySelectorAll('button')[item.answer].classList.add('correct');
      feedback.classList.remove('hidden');
      feedback.textContent = `${correct ? 'That’s it. ' : 'A useful distinction to notice. '}${item.explanation} `;
      if (item.source?.url) {
        const link = document.createElement('a'); link.href = item.source.url; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = `Read “${item.source.title}” ↗`; feedback.append(link);
      }
      next.textContent = quizIndex === quizQuestions.length - 1 ? 'Finish reflection →' : 'Next question →';
    });
    options.append(button);
  });
  const actions = document.createElement('div'); actions.className = 'quiz-actions';
  const hint = document.createElement('span'); hint.textContent = 'Take your time. There’s no timer.';
  const next = document.createElement('button'); next.className = 'primary-button'; next.textContent = 'Skip for now →';
  next.addEventListener('click', () => { quizIndex++; quizSelected = false; renderQuiz(); });
  actions.append(hint, next);
  root.append(progressText, track, question, options, feedback, actions);
}

let breathInterval = null;
let breathActive = false;
let breathPhase = 0;
let breathRemaining = 4;
let breathCycles = 0;
const breathButton = document.querySelector('#breath-start');
function updateBreathDisplay() {
  const labels = ['Breathe in', 'Pause', 'Breathe out'];
  const durations = [4, 4, 6];
  const circle = document.querySelector('#breathing-circle');
  circle.className = `breathing-circle ${breathPhase === 0 ? 'inhale' : breathPhase === 2 ? 'exhale' : ''}`;
  document.querySelector('#breath-label').textContent = breathActive ? labels[breathPhase] : 'Paused';
  document.querySelector('#breath-count').textContent = breathActive ? `${breathRemaining} seconds` : 'Take a natural breath';
  document.querySelector('#breath-rounds').textContent = `${breathCycles} of 3 gentle rounds`;
}
function stopBreathing(completed = false) {
  clearInterval(breathInterval);
  breathInterval = null;
  breathActive = false;
  const circle = document.querySelector('#breathing-circle');
  circle.className = 'breathing-circle';
  document.querySelector('#breath-label').textContent = completed ? 'Well done' : 'Paused';
  document.querySelector('#breath-count').textContent = completed ? 'Return to your day gently' : 'Take a natural breath';
  breathButton.textContent = completed ? 'Begin again' : 'Continue';
}
breathButton.addEventListener('click', () => {
  if (breathActive) { stopBreathing(); return; }
  if (breathCycles >= 3) { breathCycles = 0; breathPhase = 0; breathRemaining = 4; }
  breathActive = true;
  breathButton.textContent = 'Pause practice';
  updateBreathDisplay();
  breathInterval = setInterval(() => {
    breathRemaining--;
    if (breathRemaining <= 0) {
      if (breathPhase === 2) { breathCycles++; breathPhase = 0; }
      else breathPhase++;
      if (breathCycles >= 3) { stopBreathing(true); return; }
      breathRemaining = [4, 4, 6][breathPhase];
    }
    updateBreathDisplay();
  }, 1000);
});
document.querySelector('#grounding-reset').addEventListener('click', () => document.querySelectorAll('.grounding-list input').forEach((input) => { input.checked = false; }));

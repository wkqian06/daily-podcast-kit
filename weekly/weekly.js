const byId = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const labels = {
  coverage:['阅读覆盖','Reading window'], issue:['期号','Issue'], date:['编排日期','Prepared'],
  all:['全部','All'], findings:['关键发现','Key findings'], summary:['内容概述','Summary'],
  relevance:['与你研究的关联','Research relevance'], path:['建议阅读路径','Reading path'],
  limits:['局限与剩余问题','Limitations & remaining questions'], reason:['为什么值得读','Why read it'],
  original:['阅读原文 ↗','Read original ↗'], evidence:['证据定位','Evidence anchors'],
  load:['▶ 加载音频','▶ Load audio'], failed:['加载失败，点击重试','Load failed — retry'],
  download:['下载音频 ↓','Download audio ↓']
};
function external(url) {
  const parsed = new URL(url, location.href);
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Unsupported link: ' + url);
  return escape(parsed.href);
}
function renderReport(issue, lang, category, query) {
  const text = value => typeof value === 'string' ? value : value[lang];
  const label = key => labels[key][lang === 'zh' ? 0 : 1];
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-zh]').forEach(el => { el.textContent = el.dataset[lang]; });
  byId('language').textContent = lang === 'zh' ? 'EN' : '中文';
  byId('search').placeholder = lang === 'zh' ? '搜索论文、概念…' : 'Search papers, concepts…';
  byId('title').textContent = text(issue.title);
  document.title = text(issue.title) + ' · Research Weekly';
  byId('subtitle').textContent = text(issue.subtitle);
  byId('issue-label').textContent = `VOL. ${issue.number.toString().padStart(2, '0')}`;
  byId('metadata').innerHTML = [['issue', '#' + issue.number], ['coverage', issue.window], ['date', issue.date]]
    .map(([key, value]) => `<span><b>${label(key)}</b>${escape(value)}</span>`).join('');
  byId('thread').textContent = text(issue.thread);
  byId('note').textContent = text(issue.note);
  byId('filters').innerHTML = ['all', ...new Set(issue.papers.flatMap(p => p.tags))].map(tag =>
    `<button data-tag="${escape(tag)}" aria-pressed="${tag === category}">${escape(tag === 'all' ? label('all') : text(issue.topics[tag]))}</button>`).join('');
  const papers = issue.papers.filter(p => (category === 'all' || p.tags.includes(category)) &&
    JSON.stringify(p).toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  byId('count').textContent = lang === 'zh' ? `${papers.length} / ${issue.papers.length} 篇` : `${papers.length} / ${issue.papers.length} papers`;
  byId('empty').hidden = papers.length !== 0;
  byId('papers').innerHTML = papers.map(p => `<article class="paper">
    <div class="paper-top"><span>${escape(text(p.priority))}</span><span>${escape(text(p.reading))}</span></div>
    <h3>${escape(text(p.title))}</h3>${lang === 'zh' ? `<p class="original">${escape(p.title.en)}</p>` : ''}
    <div class="bibliography">${escape(p.authors)} · ${escape(p.venue)} · ${escape(p.year)}</div>
    <div class="tags">${p.tags.map(tag => `<span class="tag">${escape(text(issue.topics[tag]))}</span>`).join('')}</div>
    <h4>${label('summary')}</h4><p>${escape(text(p.summary))}</p>
    <h4>${label('findings')}</h4><ul>${p.findings.map(item => `<li>${escape(text(item))}</li>`).join('')}</ul>
    <div class="detail-grid">${['reason','relevance','path'].map(key => `<div><h4>${label(key)}</h4><p>${escape(text(p[key]))}</p></div>`).join('')}</div>
    <div class="limitations"><b>${label('limits')}</b><p>${escape(text(p.limits))}</p></div>
    <div class="sources"><a href="${external(p.url)}" target="_blank" rel="noopener">${label('original')}</a></div>
    <div class="evidence">${label('evidence')} · ${escape(p.evidence)}</div></article>`).join('');
  byId('progress').innerHTML = issue.progress.map(item => `<article class="progress-card"><h3>${escape(text(item.title))}</h3><p>${escape(text(item.text))}</p></article>`).join('');
  byId('progress-section').hidden = issue.progress.length === 0;
  byId('briefs').innerHTML = issue.briefs.map(item => `<article class="brief"><span>${escape(text(item.category))}</span><div><h3>${escape(text(item.title))}</h3><p>${escape(text(item.text))}</p><a href="${external(item.url)}" target="_blank" rel="noopener">${label('original')}</a></div></article>`).join('');
  byId('briefs-section').hidden = issue.briefs.length === 0;
}
function renderAudio(issue, lang) {
  const text = value => typeof value === 'string' ? value : value[lang];
  byId('audio').replaceChildren();
  for (const item of issue.audio) {
    const card = document.createElement('section');
    card.className = 'audio-card';
    const title = document.createElement('h3'); title.textContent = text(item.title);
    const note = document.createElement('p'); note.textContent = text(item.note);
    card.append(title, note);
    if (item.url) {
      const url = new URL(item.url, location.href);
      if (url.origin !== location.origin) throw new Error('Audio must be a bundled site asset');
      const button = document.createElement('button');
      const audio = document.createElement('audio'); audio.controls = true; audio.hidden = true;
      button.textContent = labels.load[lang === 'zh' ? 0 : 1];
      button.onclick = async () => {
        button.disabled = true;
        try {
          const response = await fetch(url);
          if (!response.ok) throw new Error(`Audio HTTP ${response.status}`);
          audio.src = URL.createObjectURL(await response.blob());
          audio.hidden = false; button.hidden = true;
          await audio.play();
        } catch (error) {
          button.textContent = labels.failed[lang === 'zh' ? 0 : 1];
          button.disabled = false;
          console.error(error);
        }
      };
      const download = document.createElement('a'); download.href = url.href;
      download.download = ''; download.target = '_blank'; download.rel = 'noopener';
      download.textContent = labels.download[lang === 'zh' ? 0 : 1];
      card.append(button, document.createTextNode(' · '), download, audio);
    }
    byId('audio').append(card);
  }
}
async function loadReports() {
  const response = await fetch('issues.json');
  if (!response.ok) throw new Error(`Report HTTP ${response.status}`);
  const issues = await response.json();
  let lang = 'zh', category = 'all';
  let issue = issues.find(item => item.id === location.hash.slice(1)) ?? issues[0];
  if (!issue) throw new Error('No issues available');
  byId('issues').innerHTML = issues.map(item => `<option value="${escape(item.id)}">#${item.number} · ${escape(item.date)}</option>`).join('');
  byId('issues').value = issue.id;
  const render = () => renderReport(issue, lang, category, byId('search').value);
  byId('language').onclick = () => { lang = lang === 'zh' ? 'en' : 'zh'; render(); renderAudio(issue, lang); };
  byId('theme').onclick = () => document.documentElement.classList.toggle('dark');
  byId('filters').onclick = event => { if (event.target.dataset.tag) { category = event.target.dataset.tag; render(); } };
  byId('search').oninput = render;
  byId('issues').onchange = () => {
    issue = issues.find(item => item.id === byId('issues').value);
    category = 'all'; byId('search').value = ''; location.hash = issue.id;
    render(); renderAudio(issue, lang);
  };
  render(); renderAudio(issue, lang);
  byId('status').hidden = true; byId('report').hidden = false;
}
loadReports().catch(error => { byId('status').textContent = '无法载入周报 / Unable to load report: ' + error.message; });

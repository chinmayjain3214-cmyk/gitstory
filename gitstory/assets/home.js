/* gitstory web mode: the link form, confirmation, progress and the
   decorative previews on the home page. Talks to the local server's JSON API. */
(function () {
  'use strict';

  var DATA = JSON.parse(document.getElementById('gitstory-data').textContent);
  var root = document.documentElement;
  var reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var THEME_KEY = 'gitstory-theme';

  function byId(id) { return document.getElementById(id); }
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    for (var key in attrs || {}) node.setAttribute(key, attrs[key]);
    if (text != null) node.textContent = text;
    return node;
  }
  function svg(tag, attrs, text) {
    var node = document.createElementNS(SVG_NS, tag);
    for (var key in attrs || {}) node.setAttribute(key, attrs[key]);
    if (text != null) node.textContent = text;
    return node;
  }

  // ---------------------------------------------------------------- theme

  function storedTheme() {
    try { return window.localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }
  function storeTheme(value) {
    try { window.localStorage.setItem(THEME_KEY, value); } catch (e) { /* storage may be off */ }
  }
  (function setupTheme() {
    var button = byId('theme-toggle');
    var saved = storedTheme();
    if (saved === 'dark' || saved === 'light') root.setAttribute('data-theme', saved);
    function label() { button.textContent = root.getAttribute('data-theme') === 'dark' ? 'Light theme' : 'Dark theme'; }
    button.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      storeTheme(next);
      label();
    });
    label();
  })();

  // ---------------------------------------------------------------- API

  function post(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(readJson);
  }
  function get(path) { return fetch(path, { cache: 'no-store' }).then(readJson); }
  function readJson(response) {
    return response.json().catch(function () { return {}; }).then(function (data) {
      if (!response.ok) throw new Error(data.error || ('The server answered ' + response.status + '.'));
      return data;
    });
  }
  function networkMessage(error) {
    var text = (error && error.message) || '';
    if (/fetch|network|load failed/i.test(text)) return 'Could not reach the gitstory server. Is it still running in your terminal?';
    return capitalise(text);
  }
  // Server messages start in lower case. Capitalise them, unless they start
  // with a repository name such as "octocat/hello", which must stay as typed.
  function capitalise(text) {
    if (!text || /^\S*\//.test(text)) return text;
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  // ---------------------------------------------------------------- steps

  var panels = { form: byId('step-form'), confirm: byId('step-confirm'), progress: byId('step-progress'), error: byId('step-error') };
  var input = byId('repo-input');
  var formError = byId('form-error');
  var submit = byId('form-submit');
  var current = { repo: null, job: null, timer: null, polling: false };

  function show(name, focusTarget) {
    for (var key in panels) panels[key].hidden = key !== name;
    if (focusTarget) focusTarget.focus({ preventScroll: true });
  }

  function setFormError(message) {
    formError.textContent = message || '';
    formError.hidden = !message;
    if (message) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
  }

  function resolve(url) {
    url = (url || '').trim();
    if (!url) { setFormError('Paste a GitHub repository link first.'); input.focus(); return; }
    setFormError('');
    submit.disabled = true;
    post('/api/resolve', { url: url }).then(function (repo) {
      current.repo = repo;
      byId('confirm-owner').textContent = repo.owner + '/';
      byId('confirm-name').textContent = repo.name;
      byId('confirm-link').href = repo.url;
      show('confirm', byId('confirm-go'));
    }).catch(function (error) {
      setFormError(networkMessage(error));
      input.focus();
    }).then(function () { submit.disabled = false; });
  }

  panels.form.addEventListener('submit', function (event) {
    event.preventDefault();
    resolve(input.value);
  });
  input.addEventListener('input', function () { if (!formError.hidden) setFormError(''); });

  byId('confirm-back').addEventListener('click', function () { show('form', input); input.select(); });
  byId('error-back').addEventListener('click', function () { show('form', input); input.select(); });
  byId('confirm-go').addEventListener('click', start);
  byId('error-retry').addEventListener('click', start);

  function start() {
    if (!current.repo) { show('form', input); return; }
    byId('progress-repo').textContent = current.repo.slug;
    renderProgress({ state: 'queued', phase: '', percent: null, detail: '', elapsed: 0 });
    show('progress');
    post('/api/stories', { url: current.repo.url }).then(function (job) {
      current.job = job.id;
      handle(job);
    }).catch(fail);
  }

  function handle(job) {
    renderProgress(job);
    if (job.state === 'done') {
      setTimeout(function () { window.location.assign(job.report_url); }, reduceMotion ? 0 : 450);
    } else if (job.state === 'error') {
      fail(new Error(job.error));
    } else {
      current.timer = setTimeout(poll, 600);
    }
  }

  function poll() {
    get('/api/stories/' + encodeURIComponent(current.job)).then(handle).catch(fail);
  }

  function fail(error) {
    clearTimeout(current.timer);
    byId('failure-text').textContent = networkMessage(error);
    show('error', byId('error-retry'));
  }

  var stepNodes = Array.prototype.slice.call(document.querySelectorAll('.step'));
  function renderProgress(job) {
    var active = 0;
    if (job.state === 'analysing') active = job.phase === 'Drawing the story' ? 2 : 1;
    if (job.state === 'done') active = 3;
    stepNodes.forEach(function (node, i) {
      node.classList.toggle('is-done', i < active);
      node.classList.toggle('is-active', i === active);
    });
    var detail = '';
    if (job.state === 'queued') detail = 'Waiting to start…';
    else if (job.state === 'cloning') {
      detail = job.phase || 'Connecting to GitHub';
      if (job.percent != null) detail += ' ' + job.percent + '%';
      if (job.detail) detail += ' · ' + job.detail;
    }
    byId('clone-detail').textContent = detail;
    var meter = byId('clone-meter');
    var pct = job.state === 'cloning' ? (job.percent || 0) : (active > 0 ? 100 : 0);
    meter.style.width = pct + '%';
    var seconds = Math.round(job.elapsed || 0);
    byId('elapsed').textContent = job.state === 'done'
      ? 'Done: ' + Number(job.summary.commits).toLocaleString('en-US') + ' commits read. Opening the story…'
      : (seconds >= 2 ? seconds + ' seconds so far' : '');
  }

  // Coming back with the Back button restores a frozen copy of this page.
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) { clearTimeout(current.timer); show('form'); }
  });

  // ---------------------------------------------------------------- examples

  var examples = byId('examples');
  if (DATA.examples && DATA.examples.length) {
    examples.appendChild(document.createTextNode('Try '));
    DATA.examples.forEach(function (slug, i) {
      var button = el('button', { type: 'button', 'class': 'example' }, slug);
      button.addEventListener('click', function () { input.value = 'https://github.com/' + slug; resolve(input.value); });
      examples.appendChild(button);
      if (i < DATA.examples.length - 1) examples.appendChild(document.createTextNode(' '));
    });
  }

  // A link such as /?repo=owner/name goes straight to the confirmation step.
  var preset = new URLSearchParams(window.location.search).get('repo');
  if (preset) { input.value = preset; resolve(preset); }

  // ---------------------------------------------------------------- previews

  // Deterministic "random" numbers so the previews look the same every time.
  function rng(seed) {
    return function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
  }

  var ART = {
    hero: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      s.appendChild(svg('text', { x: 0, y: 34, 'class': 'art-text art-accent', 'font-size': 32 }, '2,481'));
      s.appendChild(svg('text', { x: 104, y: 34, 'class': 'art-muted', 'font-size': 15 }, 'commits'));
      s.appendChild(svg('text', { x: 0, y: 64, 'class': 'art-text art-ink', 'font-size': 15 }, '+184k'));
      s.appendChild(svg('rect', { x: 56, y: 55, width: 120, height: 8, rx: 4, 'class': 'art-added' }));
      s.appendChild(svg('rect', { x: 179, y: 55, width: 40, height: 8, rx: 4, 'class': 'art-removed' }));
      s.appendChild(svg('text', { x: 228, y: 64, 'class': 'art-text art-ink', 'font-size': 15 }, '−61k'));
    },
    timeline: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      s.setAttribute('preserveAspectRatio', 'none');
      var r = rng(11), d = '', n = 40;
      for (var i = 0; i < n; i++) {
        var v = 0.25 + 0.5 * Math.sin(i / 6) * Math.sin(i / 6) + r() * 0.35;
        d += (i ? 'L' : 'M') + (i / (n - 1) * 300).toFixed(1) + ',' + (70 - v * 62).toFixed(1);
      }
      s.appendChild(svg('path', { d: d + 'L300,72L0,72Z', 'class': 'art-area' }));
      s.appendChild(svg('path', { d: d, 'class': 'art-stroke', 'vector-effect': 'non-scaling-stroke' }));
    },
    people: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      [['AO', 'hsl(213,58%,46%)', 0.95], ['ML', 'hsl(48,58%,46%)', 0.68], ['PR', 'hsl(290,58%,46%)', 0.36]].forEach(function (p, i) {
        var y = i * 25 + 11;
        s.appendChild(svg('circle', { cx: 11, cy: y, r: 11, fill: p[1] }));
        s.appendChild(svg('text', { x: 11, y: y + 4, 'text-anchor': 'middle', fill: '#fff', 'font-size': 9, 'class': 'art-text' }, p[0]));
        s.appendChild(svg('rect', { x: 32, y: y - 4, width: 260, height: 8, rx: 4, 'class': 'art-track' }));
        s.appendChild(svg('rect', { x: 32, y: y - 4, width: 260 * p[2], height: 8, rx: 4, 'class': 'art-accent' }));
      });
    },
    heatmap: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      var r = rng(5);
      for (var d = 0; d < 7; d++) {
        for (var h = 0; h < 24; h++) {
          var base = Math.max(0, Math.sin((h - 7) / 24 * Math.PI * 2)) * (d < 5 ? 1 : 0.35);
          var v = Math.min(1, base * (0.4 + r() * 0.9));
          s.appendChild(svg('rect', { x: h * 12.5, y: d * 10.3, width: 10.5, height: 8.6, rx: 2, 'class': 'art-track' }));
          if (v > 0.12) s.appendChild(svg('rect', { x: h * 12.5, y: d * 10.3, width: 10.5, height: 8.6, rx: 2, 'class': 'art-accent', opacity: (0.2 + 0.8 * v).toFixed(2) }));
        }
      }
    },
    churn: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      [[0.98, 0.7], [0.8, 0.6], [0.64, 0.75], [0.5, 0.55]].forEach(function (b, i) {
        var y = i * 18 + 2, w = 300 * b[0], a = w * b[1];
        s.appendChild(svg('rect', { x: 0, y: y, width: 300, height: 9, rx: 4, 'class': 'art-track' }));
        s.appendChild(svg('rect', { x: 0, y: y, width: a - 1, height: 9, rx: 4, 'class': 'art-added' }));
        s.appendChild(svg('rect', { x: a + 1, y: y, width: w - a - 1, height: 9, rx: 4, 'class': 'art-removed' }));
      });
    },
    words: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      [['fix', 1], ['add', 0.78], ['update', 0.56], ['tests', 0.4]].forEach(function (w, i) {
        var y = i * 18 + 10;
        s.appendChild(svg('text', { x: 0, y: y + 4, 'class': 'art-muted', 'font-size': 12, 'font-family': 'monospace' }, w[0]));
        s.appendChild(svg('rect', { x: 62, y: y - 4, width: 238 * w[1], height: 9, rx: 4, 'class': 'art-accent' }));
      });
    },
    facts: function (s) {
      s.setAttribute('viewBox', '0 0 300 72');
      [['🔥', '14 days'], ['💥', '3,210 lines']].forEach(function (f, i) {
        var x = i * 150;
        s.appendChild(svg('text', { x: x, y: 26, 'font-size': 22 }, f[0]));
        s.appendChild(svg('text', { x: x, y: 62, 'class': 'art-serif art-ink', 'font-size': 23 }, f[1]));
      });
    }
  };

  Array.prototype.forEach.call(document.querySelectorAll('[data-art]'), function (host) {
    var draw = ART[host.getAttribute('data-art')];
    if (!draw) return;
    var s = svg('svg', { 'aria-hidden': 'true', focusable: 'false' });
    draw(s);
    host.appendChild(s);
  });

  // ---------------------------------------------------------------- reveal

  var sections = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
  if (reduceMotion || !('IntersectionObserver' in window)) {
    sections.forEach(function (s) { s.classList.add('is-visible'); });
  } else {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        entry.target.classList.add('is-visible');
      });
    }, { threshold: 0.06 });
    sections.forEach(function (s) { observer.observe(s); });
  }

  if (!preset) input.focus({ preventScroll: true });
})();

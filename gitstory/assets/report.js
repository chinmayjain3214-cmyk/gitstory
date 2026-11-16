/* gitstory report renderer. Reads the embedded JSON and draws everything with
   plain DOM and SVG. Every string that comes from the repository is inserted
   with textContent, never as HTML. */
(function () {
  'use strict';

  var DATA = JSON.parse(document.getElementById('gitstory-data').textContent);
  var root = document.documentElement;
  var reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  var DAYS_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  var SVG_NS = 'http://www.w3.org/2000/svg';

  // ---------------------------------------------------------------- helpers

  function append(node, children) {
    if (children == null) return node;
    (Array.isArray(children) ? children : [children]).forEach(function (child) {
      if (child == null || child === false) return;
      node.appendChild(typeof child === 'object' ? child : document.createTextNode(String(child)));
    });
    return node;
  }

  function setAttrs(node, attrs) {
    for (var key in attrs) {
      var value = attrs[key];
      if (value == null || value === false) continue;
      if (key === 'text') node.textContent = value;
      else node.setAttribute(key, value);
    }
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) setAttrs(node, attrs);
    return append(node, children);
  }

  function svg(tag, attrs, children) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) setAttrs(node, attrs);
    return append(node, children);
  }

  function byId(id) { return document.getElementById(id); }

  function fmtNum(n) { return Number(n).toLocaleString('en-US'); }
  function plural(n, one, many) { return n === 1 ? one : many; }
  function count(n, one, many) { return fmtNum(n) + ' ' + plural(n, one, many); }

  // Dates arrive as ISO strings in the author's own timezone; the first ten
  // characters are the local calendar day, so no Date parsing (and no
  // timezone shifting) is needed to print them.
  function dayParts(iso) {
    var p = iso.slice(0, 10).split('-');
    return { y: +p[0], m: +p[1], d: +p[2] };
  }
  function fmtDay(iso) { var t = dayParts(iso); return t.d + ' ' + MONTHS[t.m - 1] + ' ' + t.y; }
  function fmtDayShort(iso) { var t = dayParts(iso); return t.d + ' ' + MONTHS[t.m - 1]; }
  function fmtMonth(iso) { var t = dayParts(iso); return MONTHS[t.m - 1] + ' ' + t.y; }
  function weekdayName(iso) {
    var t = dayParts(iso);
    return DAYS_LONG[(new Date(Date.UTC(t.y, t.m - 1, t.d)).getUTCDay() + 6) % 7];
  }
  function fmtRange(a, b) {
    if (a.slice(0, 10) === b.slice(0, 10)) return fmtDay(a);
    var x = dayParts(a), y = dayParts(b);
    return (x.y === y.y ? fmtDayShort(a) : fmtDay(a)) + ' to ' + fmtDay(b);
  }
  function fmtHour(h) { return (h < 10 ? '0' : '') + h + ':00'; }
  function fmtDuration(seconds) {
    if (seconds >= 2 * 86400) return count(Math.floor(seconds / 86400), 'day', 'days');
    if (seconds >= 3600) return count(Math.floor(seconds / 3600), 'hour', 'hours');
    if (seconds >= 60) return count(Math.floor(seconds / 60), 'minute', 'minutes');
    return count(seconds, 'second', 'seconds');
  }

  // ---------------------------------------------------------------- tooltip

  var tip = byId('tooltip');

  function showTip(children, clientX, clientY) {
    tip.textContent = '';
    append(tip, children);
    tip.hidden = false;
    var box = tip.getBoundingClientRect();
    var left = Math.max(8, Math.min(clientX - box.width / 2, window.innerWidth - box.width - 8));
    var top = clientY - box.height - 14;
    if (top < 8) top = clientY + 18;
    tip.style.transform = 'translate(' + Math.round(left) + 'px,' + Math.round(top) + 'px)';
  }

  function hideTip() { tip.hidden = true; }

  // ---------------------------------------------------------------- count-up

  function countUp(node) {
    var target = +node.getAttribute('data-count');
    var prefix = node.getAttribute('data-prefix') || '';
    var render = function (value) { node.textContent = prefix + fmtNum(value); };
    render(target);
    if (reduceMotion || target === 0) return;
    // Reserve the final width so the sentence does not reflow while counting.
    node.style.minWidth = node.getBoundingClientRect().width + 'px';
    var duration = 1500, started = null;
    render(0);
    function tick(now) {
      if (started === null) started = now;
      var p = Math.min(1, (now - started) / duration);
      render(Math.round(target * (1 - Math.pow(1 - p, 4))));
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function num(value, prefix) {
    return el('span', { 'class': 'num gradient-text', 'data-count': value, 'data-prefix': prefix });
  }

  // ---------------------------------------------------------------- hero

  function renderHero() {
    var s = DATA.summary;
    byId('repo-name').textContent = DATA.repo_name;
    var source = DATA.meta && DATA.meta.source;
    if (source && /^https:\/\//.test(source.url)) {
      var link = byId('hero-source');
      link.href = source.url;
      link.textContent = source.label + ' ↗';
      link.hidden = false;
    }

    append(byId('hero-lede'), [
      'It began on ', el('span', { 'class': 'date', text: fmtDay(s.first_commit) }), '. ',
      num(s.age_days), ' ' + plural(s.age_days, 'day', 'days') + ', ',
      num(s.commits), ' ' + plural(s.commits, 'commit', 'commits') + ' and ',
      num(s.contributors), ' ' + plural(s.contributors, 'contributor', 'contributors') + ' later, ',
      'the latest commit landed on ', el('span', { 'class': 'date', text: fmtDay(s.last_commit) }), '.'
    ]);

    var diff = byId('hero-diffstat');
    append(diff, el('span', null, [
      el('strong', { 'data-count': s.lines_added, 'data-prefix': '+' }),
      ' ' + plural(s.lines_added, 'line', 'lines') + ' added'
    ]));
    if (s.lines_added + s.lines_removed > 0) {
      append(diff, el('span', { 'class': 'diffbar', 'aria-hidden': 'true' }, [
        el('i', { 'class': 'is-added', style: 'flex:' + s.lines_added }),
        el('i', { 'class': 'is-removed', style: 'flex:' + s.lines_removed })
      ]));
    }
    append(diff, el('span', null, [
      el('strong', { 'data-count': s.lines_removed, 'data-prefix': '−' }),
      ' ' + plural(s.lines_removed, 'line', 'lines') + ' removed'
    ]));

    var filters = (DATA.meta && DATA.meta.filters) || {};
    var active = ['since', 'until', 'author'].filter(function (key) { return filters[key]; });
    if (active.length) {
      var note = byId('hero-filters');
      note.hidden = false;
      note.textContent = 'Showing only commits matching ' + active.map(function (key) {
        return key + ' "' + filters[key] + '"';
      }).join(', ') + '.';
    }

    Array.prototype.forEach.call(document.querySelectorAll('.hero [data-count]'), countUp);
  }

  // ---------------------------------------------------------------- timeline

  function niceTicks(max, target) {
    var rough = Math.max(1, max / target);
    var pow = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10));
    var step = [1, 2, 5, 10].map(function (m) { return m * pow; })
      .filter(function (v) { return v >= rough; })[0] || 10 * pow;
    step = Math.max(1, Math.round(step));
    var ticks = [];
    for (var v = 0; v < max + step; v += step) ticks.push(v);
    return ticks;
  }

  function renderTimeline() {
    var weeks = DATA.timeline;
    var host = byId('timeline-chart');
    var n = weeks.length;
    var bars = n <= 26;
    var maxCommits = Math.max.apply(null, weeks.map(function (w) { return w.commits; }).concat([1]));
    var state = { progress: reduceMotion ? 1 : 0, active: -1, geom: null, animating: false };

    var busiest = weeks.reduce(function (best, w) { return w.commits > best.commits ? w : best; }, weeks[0]);
    byId('timeline-lede').textContent = n === 1
      ? 'Every commit so far landed in the week of ' + fmtDay(weeks[0].start) + '.'
      : 'Commits per week across ' + count(n, 'week', 'weeks') + '. The busiest began on ' +
        fmtDay(busiest.start) + ', with ' + count(busiest.commits, 'commit', 'commits') + '.';

    function draw() {
      var width = Math.max(260, Math.floor(host.clientWidth));
      var height = width < 520 ? 220 : 300;
      var m = { t: 14, r: 14, b: 30, l: 38 };
      var iw = width - m.l - m.r, ih = height - m.t - m.b;
      var ticks = niceTicks(maxCommits, width < 520 ? 3 : 4);
      var top = ticks[ticks.length - 1];
      var band = iw / n;
      var x = bars
        ? function (i) { return m.l + band * (i + 0.5); }
        : function (i) { return m.l + iw * i / (n - 1); };
      var y = function (v) { return m.t + ih * (1 - v / top); };

      var defs = svg('defs', null, [
        svg('linearGradient', { id: 'tl-stroke', gradientUnits: 'userSpaceOnUse', x1: m.l, y1: 0, x2: width - m.r, y2: 0 }, [
          svg('stop', { offset: '0', 'class': 'stop-a' }), svg('stop', { offset: '1', 'class': 'stop-b' })
        ]),
        svg('linearGradient', { id: 'tl-fill', gradientUnits: 'userSpaceOnUse', x1: 0, y1: m.t, x2: 0, y2: m.t + ih }, [
          svg('stop', { offset: '0', 'class': 'stop-b', 'stop-opacity': '0.34' }),
          svg('stop', { offset: '1', 'class': 'stop-a', 'stop-opacity': '0.02' })
        ]),
        svg('clipPath', { id: 'tl-clip' }, svg('rect', { x: 0, y: 0, width: width * state.progress, height: height }))
      ]);

      var axes = svg('g', { 'aria-hidden': 'true' });
      ticks.forEach(function (t) {
        append(axes, [
          svg('line', { 'class': 'tl-grid', x1: m.l, x2: width - m.r, y1: y(t), y2: y(t) }),
          svg('text', { 'class': 'tl-label', x: m.l - 8, y: y(t) + 4, 'text-anchor': 'end', text: fmtNum(t) })
        ]);
      });
      var maxLabels = Math.max(2, Math.floor(iw / 96));
      var every = Math.ceil(n / maxLabels);
      for (var i = 0; i < n; i += every) {
        var lx = x(i);
        var anchor = lx < m.l + 30 ? 'start' : (lx > width - m.r - 30 ? 'end' : 'middle');
        append(axes, svg('text', {
          'class': 'tl-label', x: anchor === 'start' ? m.l : lx, y: height - 8, 'text-anchor': anchor,
          text: n > 20 ? fmtMonth(weeks[i].start) : fmtDayShort(weeks[i].start)
        }));
      }

      var marks = svg('g', { 'clip-path': 'url(#tl-clip)', 'class': bars ? 'tl-bars' : 'tl-area' });
      var barNodes = [];
      if (bars) {
        var bw = Math.max(2, Math.min(34, band - 2));
        weeks.forEach(function (w, i) {
          if (!w.commits) { barNodes.push(null); return; }
          var x0 = x(i) - bw / 2, y0 = y(0), y1 = y(w.commits);
          var r = Math.min(4, bw / 2, y0 - y1);
          var bar = svg('path', {
            'class': 'tl-bar', fill: 'url(#tl-stroke)',
            d: 'M' + x0 + ',' + y0 + 'V' + (y1 + r) + 'Q' + x0 + ',' + y1 + ' ' + (x0 + r) + ',' + y1 +
               'H' + (x0 + bw - r) + 'Q' + (x0 + bw) + ',' + y1 + ' ' + (x0 + bw) + ',' + (y1 + r) + 'V' + y0 + 'Z'
          });
          barNodes.push(bar);
          append(marks, bar);
        });
      } else {
        var line = weeks.map(function (w, i) {
          return (i ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(w.commits).toFixed(1);
        }).join('');
        append(marks, [
          svg('path', { fill: 'url(#tl-fill)', d: line + 'L' + x(n - 1) + ',' + y(0) + 'L' + x(0) + ',' + y(0) + 'Z' }),
          svg('path', { 'class': 'tl-line', stroke: 'url(#tl-stroke)', d: line })
        ]);
      }

      var guide = svg('line', { 'class': 'tl-guide', y1: m.t, y2: y(0), visibility: 'hidden' });
      var dot = svg('circle', { 'class': 'tl-dot', r: 5, visibility: 'hidden' });
      var hit = svg('rect', { x: m.l, y: 0, width: iw, height: height - m.b + 4, fill: 'transparent' });

      var chart = svg('svg', {
        viewBox: '0 0 ' + width + ' ' + height, width: width, height: height, role: 'img', tabindex: '0',
        'aria-label': 'Commits per week from ' + fmtDay(weeks[0].start) + ' to ' + fmtDay(weeks[n - 1].start) +
          '. Peak of ' + count(busiest.commits, 'commit', 'commits') + ' in the week of ' + fmtDay(busiest.start) +
          '. Use the left and right arrow keys to read each week.'
      }, [defs, axes, marks, guide, dot, hit]);

      state.geom = { x: x, y: y, m: m, iw: iw, band: band, chart: chart, guide: guide, dot: dot, marks: marks, barNodes: barNodes };

      hit.addEventListener('pointermove', onPointer);
      hit.addEventListener('pointerdown', onPointer);
      hit.addEventListener('pointerleave', function () { setActive(-1); });
      chart.addEventListener('keydown', onKey);
      chart.addEventListener('focus', function () { if (state.active < 0) setActive(n - 1); });
      chart.addEventListener('blur', function () { setActive(-1); });

      host.textContent = '';
      host.appendChild(chart);
      if (state.active >= 0) setActive(state.active);
    }

    function onPointer(event) {
      var g = state.geom;
      var box = g.chart.getBoundingClientRect();
      var px = (event.clientX - box.left) * (g.chart.viewBox.baseVal.width / box.width) - g.m.l;
      var i = bars ? Math.floor(px / g.band) : Math.round(px / g.iw * (n - 1));
      setActive(Math.max(0, Math.min(n - 1, i)));
    }

    function onKey(event) {
      var next = state.active;
      if (event.key === 'ArrowLeft') next -= 1;
      else if (event.key === 'ArrowRight') next += 1;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = n - 1;
      else if (event.key === 'Escape') { setActive(-1); return; }
      else return;
      event.preventDefault();
      setActive(Math.max(0, Math.min(n - 1, next)));
    }

    function setActive(i) {
      var g = state.geom;
      if (!g) return;
      if (state.active >= 0 && g.barNodes[state.active]) g.barNodes[state.active].classList.remove('is-active');
      state.active = i;
      if (i < 0) {
        g.guide.setAttribute('visibility', 'hidden');
        g.dot.setAttribute('visibility', 'hidden');
        g.marks.classList.remove('has-active');
        hideTip();
        return;
      }
      var week = weeks[i], cx = g.x(i), cy = g.y(week.commits);
      if (bars) {
        g.marks.classList.add('has-active');
        if (g.barNodes[i]) g.barNodes[i].classList.add('is-active');
      } else {
        setAttrs(g.guide, { x1: cx, x2: cx, visibility: 'visible' });
        setAttrs(g.dot, { cx: cx, cy: cy, visibility: 'visible' });
      }
      var box = g.chart.getBoundingClientRect();
      var scale = box.width / g.chart.viewBox.baseVal.width;
      showTip([
        el('strong', { text: count(week.commits, 'commit', 'commits') }),
        'Week of ' + fmtDay(week.start),
        week.top_message ? el('em', { text: '“' + week.top_message + '”' }) : null
      ], box.left + cx * scale, box.top + cy * scale);
    }

    function start() {
      if (state.progress >= 1 || state.animating) return;
      state.animating = true;
      var duration = 1700, began = null;
      function tick(now) {
        if (began === null) began = now;
        var p = Math.min(1, (now - began) / duration);
        state.progress = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
        var clip = document.querySelector('#tl-clip rect');
        if (clip && state.geom) clip.setAttribute('width', state.geom.chart.viewBox.baseVal.width * state.progress);
        if (p < 1) requestAnimationFrame(tick);
        else { state.progress = 1; state.animating = false; }
      }
      requestAnimationFrame(tick);
    }

    draw();
    var pending = false, lastWidth = host.clientWidth;
    function redraw() {
      if (pending || host.clientWidth === lastWidth) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; lastWidth = host.clientWidth; hideTip(); draw(); });
    }
    if (window.ResizeObserver) new ResizeObserver(redraw).observe(host);
    else window.addEventListener('resize', redraw);

    return start;
  }

  // ---------------------------------------------------------------- contributors

  function sparkline(values) {
    var w = 240, h = 38, pad = 3, n = values.length;
    var max = Math.max.apply(null, values.concat([1]));
    var x = function (i) { return n === 1 ? w / 2 : i / (n - 1) * w; };
    var y = function (v) { return h - pad - v / max * (h - pad * 2); };
    var line = values.map(function (v, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1); }).join('');
    return svg('svg', { 'class': 'spark', viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none', 'aria-hidden': 'true' }, [
      svg('path', { 'class': 'spark-area', d: line + 'L' + w + ',' + h + 'L0,' + h + 'Z' }),
      svg('path', { 'class': 'spark-line', d: line })
    ]);
  }

  function diffText(added, removed) {
    return [
      el('i', { 'class': 'swatch is-added', 'aria-hidden': 'true' }), '+' + fmtNum(added),
      el('i', { 'class': 'swatch is-removed', 'aria-hidden': 'true' }), '−' + fmtNum(removed)
    ];
  }

  function renderContributors() {
    var people = DATA.contributors, total = DATA.summary.contributors, commits = DATA.summary.commits;
    var lead = people[0];
    byId('contributors-lede').textContent = total === 1
      ? lead.name + ' wrote every commit.'
      : fmtNum(total) + ' people have committed. ' + lead.name + ' leads with ' +
        count(lead.commits, 'commit', 'commits') + ' (' + Math.round(lead.commits / commits * 100) + '% of the total).';

    var list = byId('people'), initial = 6;
    people.forEach(function (p, i) {
      var card = el('li', { 'class': 'person' }, [
        el('div', { 'class': 'person-head' }, [
          el('span', { 'class': 'avatar', style: 'background:' + p.color, 'aria-hidden': 'true', text: p.initials }),
          el('span', { 'class': 'person-name', title: p.name, text: p.name }),
          el('span', { 'class': 'person-rank', text: '#' + (i + 1) })
        ]),
        el('div', { 'class': 'person-stats' }, [
          el('span', { 'class': 'person-commits' }, [fmtNum(p.commits), el('small', { text: plural(p.commits, 'commit', 'commits') })]),
          el('span', { 'class': 'person-lines' }, diffText(p.lines_added, p.lines_removed))
        ]),
        sparkline(p.sparkline),
        el('div', { 'class': 'person-dates', text: 'Active ' + fmtRange(p.first_active, p.last_active) })
      ]);
      if (i >= initial) card.hidden = true;
      list.appendChild(card);
    });

    var more = byId('people-more');
    var notShown = total - people.length;
    var tail = notShown > 0 ? 'Plus ' + count(notShown, 'more contributor', 'more contributors') + ' not listed here.' : '';
    if (people.length > initial) {
      var button = el('button', { type: 'button', text: 'Show all ' + people.length + ' contributors' });
      button.addEventListener('click', function () {
        Array.prototype.forEach.call(list.children, function (card) { card.hidden = false; });
        more.textContent = tail;
      });
      more.appendChild(button);
    } else {
      more.textContent = tail;
    }
  }

  // ---------------------------------------------------------------- heatmap

  function heat(value, max) { return value ? (0.16 + 0.84 * Math.sqrt(value / max)).toFixed(3) : 0; }

  function renderHeatmap() {
    var grid = DATA.heatmap, host = byId('heatmap');
    var max = 1, peak = { day: 0, hour: 0, count: 0 };
    grid.forEach(function (row, d) {
      row.forEach(function (v, h) {
        if (v > max) max = v;
        if (v > peak.count) peak = { day: d, hour: h, count: v };
      });
    });

    byId('rhythm-lede').textContent = 'Each square is one hour of the week, in the local time of whoever made the commit.';

    host.setAttribute('role', 'img');
    host.setAttribute('aria-label', 'Heatmap of commits by day of week and hour. Busiest hour: ' +
      DAYS_LONG[peak.day] + 's at ' + fmtHour(peak.hour) + ' with ' + count(peak.count, 'commit', 'commits') + '.');

    host.appendChild(el('span'));
    for (var h = 0; h < 24; h++) host.appendChild(el('span', { 'class': 'hm-hour', text: h % 3 === 0 ? h : '' }));
    grid.forEach(function (row, d) {
      host.appendChild(el('span', { 'class': 'hm-day', text: DAYS[d] }));
      row.forEach(function (v, hour) {
        host.appendChild(el('i', {
          'class': 'hm-cell', style: '--v:' + heat(v, max) + ';--col:' + hour,
          'data-day': d, 'data-hour': hour, 'data-count': v
        }));
      });
    });

    function onMove(event) {
      var cell = event.target.closest ? event.target.closest('.hm-cell') : null;
      if (!cell) { hideTip(); return; }
      var hour = +cell.getAttribute('data-hour'), n = +cell.getAttribute('data-count');
      var box = cell.getBoundingClientRect();
      showTip([
        el('strong', { text: count(n, 'commit', 'commits') }),
        DAYS_LONG[+cell.getAttribute('data-day')] + 's, ' + fmtHour(hour) + ' to ' + fmtHour((hour + 1) % 24)
      ], box.left + box.width / 2, box.top);
    }
    host.addEventListener('pointermove', onMove);
    host.addEventListener('pointerdown', onMove);
    host.addEventListener('pointerleave', hideTip);

    var legend = byId('heatmap-legend');
    legend.appendChild(el('span', { text: 'Fewer' }));
    [0, 0.25, 0.5, 0.75, 1].forEach(function (step) {
      legend.appendChild(el('i', { 'class': 'hm-cell', style: '--v:' + heat(step * max, max) }));
    });
    legend.appendChild(el('span', { text: 'More commits' }));

    var persona = DATA.persona;
    append(byId('persona'), [
      el('div', { 'class': 'persona-emoji', 'aria-hidden': 'true', text: persona.emoji }),
      el('div', { 'class': 'persona-label', text: persona.label }),
      el('p', { 'class': 'persona-text', text: persona.description }),
      el('p', { 'class': 'persona-peak', text: 'Busiest hour of the week: ' + DAYS_LONG[peak.day] + 's at ' +
        fmtHour(peak.hour) + ' (' + count(peak.count, 'commit', 'commits') + ').' })
    ]);
  }

  // ---------------------------------------------------------------- bar lists

  // `fill` is a list of coloured segments, or null for a single solid bar.
  // `title` marks the label as a file path: monospace, full path on hover.
  function barRow(index, label, value, widthPct, fill, title) {
    return el('li', { 'class': 'bar-row' }, [
      el('div', { 'class': 'bar-head' }, [
        el('div', { 'class': 'bar-label' + (title ? ' mono' : ''), title: title }, label),
        el('div', { 'class': 'bar-value' }, value)
      ]),
      el('div', { 'class': 'bar-track' }, el('div', {
        'class': 'bar-fill' + (fill ? '' : ' is-solid'), style: '--w:' + widthPct.toFixed(2) + '%;--i:' + index
      }, fill))
    ]);
  }

  function renderChurn() {
    var files = DATA.files, extensions = DATA.extensions;
    var fileList = byId('churn-files'), extList = byId('churn-extensions');
    byId('churn-lede').textContent = 'The files that changed the most, by lines added and removed. Renamed files keep their history.';

    if (!files.length) {
      byId('churn-legend').hidden = true;
      fileList.appendChild(el('li', { 'class': 'empty', text: 'No file changes were recorded for these commits.' }));
    } else {
      append(byId('churn-legend'), [
        el('span', null, [el('i', { 'class': 'swatch is-added' }), 'Lines added']),
        el('span', null, [el('i', { 'class': 'swatch is-removed' }), 'Lines removed'])
      ]);
      var maxLines = Math.max.apply(null, files.map(function (f) { return f.lines_added + f.lines_removed; }).concat([1]));
      files.forEach(function (f, i) {
        var slash = f.path.lastIndexOf('/');
        var total = f.lines_added + f.lines_removed;
        fileList.appendChild(barRow(i, [
          slash >= 0 ? el('span', { 'class': 'path-dir', text: f.path.slice(0, slash + 1) }) : null,
          el('span', { 'class': 'path-name', text: f.path.slice(slash + 1) })
        ], [
          '+' + fmtNum(f.lines_added) + ' −' + fmtNum(f.lines_removed),
          el('small', { text: count(f.commits, 'commit', 'commits') })
        ], total / maxLines * 100, [
          f.lines_added ? el('i', { 'class': 'is-added', style: 'flex:' + f.lines_added }) : null,
          f.lines_removed ? el('i', { 'class': 'is-removed', style: 'flex:' + f.lines_removed }) : null
        ], f.path));
      });
    }

    if (!extensions.length) {
      extList.appendChild(el('li', { 'class': 'empty', text: 'Nothing to show yet.' }));
    } else {
      var maxShare = Math.max.apply(null, extensions.map(function (e) { return e.share; }).concat([0.0001]));
      extensions.forEach(function (e, i) {
        var named = e.language !== e.extension;
        extList.appendChild(barRow(i, [
          el('span', { 'class': 'path-name', text: e.language }),
          named ? el('span', { 'class': 'hint mono', text: e.extension }) : null
        ], [
          Math.round(e.share * 100) + '%',
          el('small', { text: count(e.lines_changed, 'line', 'lines') })
        ], e.share / maxShare * 100, null));
      });
    }
  }

  // ---------------------------------------------------------------- messages

  function tile(value, unit, label, extra) {
    return el('div', { 'class': 'tile' }, [
      el('div', { 'class': 'tile-value' }, [value, unit ? el('small', { text: unit }) : null]),
      el('div', { 'class': 'tile-label', text: label }),
      extra
    ]);
  }

  function quote(kind, ref) {
    return el('figure', { 'class': 'quote', style: 'margin:0' }, [
      el('div', { 'class': 'quote-kind', text: kind + ', ' + count(ref.length, 'character', 'characters') }),
      el('blockquote', { 'class': 'quote-text', style: 'margin-left:0;margin-right:0', text: ref.text || '(empty message)' }),
      el('figcaption', { 'class': 'quote-meta' }, [ref.author + ', ' + fmtDay(ref.when) + ', ', el('span', { 'class': 'mono', text: ref.hash })])
    ]);
  }

  function renderMessages() {
    var m = DATA.messages, merges = DATA.summary.merges;
    byId('messages-lede').textContent = 'Based on the subject line of ' + count(m.analysed, 'commit', 'commits') +
      (merges && m.analysed < DATA.summary.commits ? ' (' + count(merges, 'merge commit', 'merge commits') + ' left out).' : '.');

    var chips = m.conventional_types.length ? el('div', { 'class': 'chips' }, m.conventional_types.map(function (t) {
      return el('span', { 'class': 'chip' }, [t.type, el('b', { text: fmtNum(t.count) })]);
    })) : null;
    append(byId('message-tiles'), [
      tile(fmtNum(m.average_length), 'characters', 'Average message length'),
      tile(fmtNum(m.average_words), 'words', 'Average words per message'),
      tile(Math.round(m.conventional_share * 100) + '%', null,
        'Use a conventional-commit prefix (' + fmtNum(m.conventional_count) + ' of ' + fmtNum(m.analysed) + ')', chips)
    ]);

    var words = byId('message-words');
    if (!m.common_words.length) {
      words.appendChild(el('li', { 'class': 'empty', text: 'Not enough words to count yet.' }));
    } else {
      var maxCount = m.common_words[0].count;
      words.className = 'bars is-two-col';
      words.style.setProperty('--rows', Math.ceil(m.common_words.length / 2));
      m.common_words.forEach(function (w, i) {
        words.appendChild(barRow(i, el('span', { 'class': 'path-name', text: w.word }),
          fmtNum(w.count), w.count / maxCount * 100, null));
      });
    }

    var quotes = byId('message-quotes');
    if (m.longest) quotes.appendChild(quote('Longest message', m.longest));
    if (m.shortest) quotes.appendChild(quote('Shortest message', m.shortest));
  }

  // ---------------------------------------------------------------- fun facts

  function fact(emoji, title, value, detail) {
    return el('div', { 'class': 'fact' }, [
      el('div', { 'class': 'fact-emoji', 'aria-hidden': 'true', text: emoji }),
      el('div', { 'class': 'fact-title', text: title }),
      el('div', { 'class': 'fact-value', text: value }),
      el('div', { 'class': 'fact-detail' }, detail)
    ]);
  }

  function renderFacts() {
    var f = DATA.facts, cards = byId('fact-cards');
    var big = f.biggest_commit;
    if (big) {
      cards.appendChild(fact('💥', 'Biggest single commit',
        count(big.lines_added + big.lines_removed, 'line', 'lines'), [
          el('q', { text: big.subject || '(empty message)' }),
          ' by ' + big.author + ' on ' + fmtDay(big.when) + ', touching ' + count(big.files, 'file', 'files') + ' (',
          el('span', { 'class': 'mono', text: big.hash }), ').'
        ]));
    }
    var streak = f.longest_streak;
    cards.appendChild(fact('🔥', 'Longest streak', count(streak.days, 'day', 'days'),
      streak.days === 1
        ? 'No two days in a row with commits yet.'
        : 'A commit every day from ' + fmtRange(streak.start, streak.end) + '.'));
    var gap = f.longest_gap;
    cards.appendChild(fact('🏖️', 'Longest gap',
      gap ? fmtDuration(gap.seconds) : 'None yet',
      !gap ? 'A gap needs at least two commits.'
        : gap.start.slice(0, 10) === gap.end.slice(0, 10)
          ? 'The longest wait between two commits, on ' + fmtDay(gap.start) + '.'
          : 'Nothing was committed from ' + fmtRange(gap.start, gap.end) + '.'));
    var busy = f.busiest_day;
    cards.appendChild(fact('📅', 'Busiest day ever', count(busy.commits, 'commit', 'commits'),
      weekdayName(busy.day) + ', ' + fmtDay(busy.day) + '.'));
  }

  // ---------------------------------------------------------------- page chrome

  function renderFooter() {
    var meta = DATA.meta || {};
    byId('footer-meta').textContent = (meta.version ? ' ' + meta.version : '') +
      (meta.generated_at ? ' on ' + fmtDay(meta.generated_at) : '') + '.';
  }

  // Pages served by `gitstory --serve` remember the theme picked on the home
  // page. A standalone report file keeps the theme it was generated with.
  var served = !!(DATA.meta && DATA.meta.links && DATA.meta.links.length);
  var THEME_KEY = 'gitstory-theme';

  function setupTheme() {
    var button = byId('theme-toggle');
    if (served) {
      try {
        var saved = window.localStorage.getItem(THEME_KEY);
        if (saved === 'dark' || saved === 'light') root.setAttribute('data-theme', saved);
      } catch (e) { /* storage may be unavailable */ }
    }
    function label() { button.textContent = root.getAttribute('data-theme') === 'dark' ? 'Light theme' : 'Dark theme'; }
    button.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      if (served) { try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* ignore */ } }
      label();
    });
    label();
  }

  function renderNav() {
    var links = (DATA.meta && DATA.meta.links) || [];
    var nav = byId('report-nav');
    links.forEach(function (link) {
      // Only same-site paths: the nav is for the local web mode.
      if (typeof link.href !== 'string' || link.href.charAt(0) !== '/' || link.href.charAt(1) === '/') return;
      nav.appendChild(el('a', { href: link.href, text: link.label }));
    });
    nav.hidden = !nav.children.length;
  }

  function setupReveal(hooks) {
    var sections = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
    function show(section) {
      section.classList.add('is-visible');
      if (hooks[section.id]) hooks[section.id]();
    }
    if (reduceMotion || !('IntersectionObserver' in window)) { sections.forEach(show); return; }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        show(entry.target);
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -6% 0px' });
    sections.forEach(function (section) { observer.observe(section); });
  }

  setupTheme();
  renderNav();
  renderHero();
  var startTimeline = renderTimeline();
  renderContributors();
  renderHeatmap();
  renderChurn();
  renderMessages();
  renderFacts();
  renderFooter();
  setupReveal({ timeline: startTimeline });
  window.addEventListener('scroll', hideTip, { passive: true });
})();

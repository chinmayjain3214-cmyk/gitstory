/* gitstory report renderer. Reads the embedded JSON and draws everything with
   plain DOM and SVG. Every string that comes from the repository is inserted
   with textContent, never as HTML. */
(function () {
  'use strict';

  // The page exactly as it arrived, before any drawing: "Download story → HTML"
  // saves this, so the copy works offline and draws itself again when opened.
  var PRISTINE = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;

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
      more.setAttribute('data-export-text', tail);   // what an image or PDF shows instead of the button
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

  // ---------------------------------------------------------------- commit history

  function ordinal(n) {
    var v = n % 100;
    var suffix = (v >= 11 && v <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th');
    return fmtNum(n) + suffix;
  }

  function fmtTime(iso) {
    var offset = (iso.match(/([+-]\d\d:\d\d)$/) || [])[1];
    var zone = !offset || offset === '+00:00' || offset === '-00:00' ? 'UTC' : 'UTC' + offset;
    return iso.slice(11, 16) + ' ' + zone;
  }

  function splitPath(path) {
    var slash = path.lastIndexOf('/');
    return [
      slash >= 0 ? el('span', { 'class': 'path-dir', text: path.slice(0, slash + 1) }) : null,
      el('span', { 'class': 'path-name', text: path.slice(slash + 1) })
    ];
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }
  function legacyCopy(text) {
    var area = el('textarea', { readonly: 'readonly', style: 'position:fixed;top:-100px;opacity:0' });
    area.value = text;
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(area);
    if (!ok) throw new Error('copy failed');
  }

  var STATUS_LABEL = { A: 'New', D: 'Deleted', R: 'Renamed', M: 'Changed' };
  var PAGE = 10;

  // Returns a function other chapters can call to jump to a commit by hash,
  // or null when the report has no history.
  function renderHistory() {
    var H = DATA.history;
    if (!H || !H.commits || !H.commits.length) return null;
    var section = byId('history');
    section.hidden = false;

    var source = DATA.meta && DATA.meta.source;
    var githubBase = source && /^https:\/\/github\.com\/[^/]+\/[^/]+$/.test(source.url) ? source.url : null;

    var commits = H.commits.map(function (row, index) {
      var author = H.authors[row[3]];
      return {
        index: index, hash: row[0], subject: row[1], body: row[2],
        author: author[0], initials: author[1], color: author[2],
        when: row[4], type: row[5], merge: !!row[6], number: row[7], authorNumber: row[8],
        sincePrevious: row[9], added: row[10], removed: row[11], filesTotal: row[12],
        files: row[13].map(function (f) {
          return {
            path: H.paths[f[0]], oldPath: f[1] >= 0 ? H.paths[f[1]] : null, status: f[2],
            added: f[3], removed: f[4], binary: !!f[5], lineage: f[6], touch: f[7], touches: f[8]
          };
        }),
        haystack: null
      };
    });
    var total = commits.length;

    var state = { query: '', type: '', lineage: 0, shown: 0, matches: commits };
    var list = byId('commit-list');
    var status = byId('history-status');
    var more = byId('history-more');
    var search = byId('history-search');
    var fileFilter = byId('history-file-filter');
    var browser = byId('history-browser');
    var opener = byId('history-open');

    byId('history-open-hint').textContent = total > PAGE
      ? 'Start with the latest ' + PAGE + ' of ' + count(H.total, 'commit', 'commits') + ', then load more'
      : 'See all ' + count(total, 'commit', 'commits') + ', newest first';

    // ---- filters

    var typeCounts = {}, merges = 0;
    commits.forEach(function (c) {
      if (c.merge) merges++;
      if (c.type) typeCounts[c.type] = (typeCounts[c.type] || 0) + 1;
    });
    var types = Object.keys(typeCounts).sort(function (a, b) { return typeCounts[b] - typeCounts[a] || (a < b ? -1 : 1); }).slice(0, 6);
    var typeHost = byId('history-types');
    var typeButtons = [];
    function typeButton(value, label, n) {
      var button = el('button', { type: 'button', 'class': 'type-filter', 'aria-pressed': value === state.type ? 'true' : 'false' }, [label, el('b', { text: fmtNum(n) })]);
      button.addEventListener('click', function () { state.type = state.type === value && value ? '' : value; refresh(true); });
      button._value = value;
      typeButtons.push(button);
      typeHost.appendChild(button);
    }
    if (types.length || merges) {
      typeButton('', 'All', total);
      types.forEach(function (t) { typeButton(t, t, typeCounts[t]); });
      if (merges) typeButton(':merge', 'Merges', merges);
    }

    function haystack(c) {
      if (c.haystack === null) {
        c.haystack = [c.subject, c.body, c.author, c.hash].concat(
          c.files.map(function (f) { return f.path + ' ' + (f.oldPath || ''); })
        ).join('\n').toLowerCase();
      }
      return c.haystack;
    }

    function matches(c) {
      if (state.type === ':merge' && !c.merge) return false;
      if (state.type && state.type !== ':merge' && c.type !== state.type) return false;
      if (state.lineage && !c.files.some(function (f) { return f.lineage === state.lineage; })) return false;
      if (!state.query) return true;
      var text = haystack(c);
      return state.query.split(/\s+/).every(function (word) { return text.indexOf(word) >= 0; });
    }

    // ---- rendering

    function factChip(text, milestone) {
      return el('span', { 'class': 'commit-fact' + (milestone ? ' is-milestone' : ''), text: text });
    }

    function fileRow(f, j, maxLines) {
      var lines = f.added + f.removed;
      var label = f.binary ? 'Binary' : STATUS_LABEL[f.status];
      var statusClass = f.binary && f.status === 'M' ? 'M' : f.status;
      var history;
      if (f.touches <= 1) {
        history = el('span', { 'class': 'cfile-history', title: 'No other commit changed this file', text: 'Only change' });
      } else {
        history = el('button', {
          type: 'button', 'class': 'cfile-history',
          title: 'Show every commit that changed this file',
          'aria-label': 'Change ' + f.touch + ' of ' + f.touches + ' to ' + f.path + '. Show every commit that changed it.',
          text: 'Change ' + fmtNum(f.touch) + ' of ' + fmtNum(f.touches) + ' ↗'
        });
        history.addEventListener('click', function (event) {
          event.stopPropagation();
          showFileHistory(f.lineage, f.path);
        });
      }
      return el('li', { 'class': 'cfile' + (state.lineage && f.lineage === state.lineage ? ' is-followed' : ''), style: '--j:' + Math.min(j, 20) }, [
        el('span', { 'class': 'cfile-status s-' + statusClass, text: label }),
        el('div', { 'class': 'cfile-path', title: f.path }, splitPath(f.path).concat([
          f.oldPath ? el('small', { text: 'renamed from ' + f.oldPath }) : null
        ])),
        el('span', { 'class': 'cfile-lines', text: f.binary ? 'binary' : '+' + fmtNum(f.added) + ' −' + fmtNum(f.removed) }),
        lines ? el('span', { 'class': 'cfile-bar', 'aria-hidden': 'true', style: 'width:' + Math.max(2, lines / maxLines * 100).toFixed(1) + '%' }, [
          f.added ? el('i', { 'class': 'is-added', style: 'flex:' + f.added }) : null,
          f.removed ? el('i', { 'class': 'is-removed', style: 'flex:' + f.removed }) : null
        ]) : null,
        history
      ]);
    }

    function details(c) {
      var facts = [
        factChip('Commit ' + fmtNum(c.number) + ' of ' + fmtNum(H.total)),
        c.number === 1 ? factChip('🌱 The very first commit', true) : null,
        c.authorNumber === 1
          ? factChip('🎉 ' + c.author + "'s first commit", true)
          : factChip(c.author + "'s " + ordinal(c.authorNumber) + ' commit'),
        factChip(weekdayName(c.when) + ', ' + fmtTime(c.when)),
        c.sincePrevious >= 0
          ? factChip(c.sincePrevious < 60 ? 'Right after the previous commit' : fmtDuration(c.sincePrevious) + ' after the previous commit')
          : null
      ];

      var body = c.body ? el('pre', { 'class': 'commit-body', text: c.body }) : null;

      var filesBlock;
      if (!c.files.length) {
        filesBlock = el('p', { 'class': 'cfiles-note', text: c.merge
          ? 'Merge commits do not list file changes; the changes show up on the commits that were merged.'
          : 'This commit did not change any files.' });
      } else {
        var maxLines = Math.max.apply(null, c.files.map(function (f) { return f.added + f.removed; }).concat([1]));
        var counts = { A: 0, D: 0, R: 0 };
        c.files.forEach(function (f) { if (counts[f.status] != null) counts[f.status]++; });
        var summary = [
          counts.A ? fmtNum(counts.A) + ' new' : null,
          counts.D ? fmtNum(counts.D) + ' deleted' : null,
          counts.R ? fmtNum(counts.R) + ' renamed' : null
        ].filter(Boolean).join(' · ');
        filesBlock = [
          el('div', { 'class': 'cfiles-title' }, [
            'Files changed (' + fmtNum(c.filesTotal) + ')',
            summary ? el('small', { text: summary }) : null
          ]),
          el('ul', { 'class': 'cfiles' }, c.files.map(function (f, j) { return fileRow(f, j, maxLines); })),
          c.filesTotal > c.files.length
            ? el('p', { 'class': 'cfiles-more', text: 'Plus ' + count(c.filesTotal - c.files.length, 'smaller change', 'smaller changes') + ' not listed here.' })
            : null
        ];
      }

      var copy = el('button', { type: 'button', title: 'Copy the full commit hash' }, [
        el('span', { 'class': 'mono', text: c.hash.slice(0, 10) }), el('span', { text: 'Copy hash' })
      ]);
      copy.addEventListener('click', function () {
        var label = copy.lastChild;
        copyText(c.hash).then(function () { label.textContent = 'Copied ✓'; }, function () { label.textContent = 'Copy failed'; })
          .then(function () { setTimeout(function () { label.textContent = 'Copy hash'; }, 1600); });
      });
      var actions = el('div', { 'class': 'commit-actions' }, [
        copy,
        githubBase ? el('a', { href: githubBase + '/commit/' + c.hash, target: '_blank', rel: 'noopener noreferrer', text: 'View on GitHub ↗' }) : null
      ]);

      return el('div', { 'class': 'commit-details-body' }, [
        el('div', { 'class': 'commit-facts' }, facts), body
      ].concat(filesBlock).concat([actions]));
    }

    function card(c, i) {
      var id = 'commit-' + c.hash.slice(0, 12);
      var item = el('li', { 'class': 'commit is-entering' + (c.merge ? ' is-merge' : ''), id: id, style: '--i:' + i });
      var tag = c.merge ? el('span', { 'class': 'type-tag t-merge', text: 'merge' })
        : (c.type ? el('span', { 'class': 'type-tag t-' + c.type, text: c.type }) : null);
      var lines = c.added + c.removed;
      var head = el('button', { type: 'button', 'class': 'commit-head', 'aria-expanded': 'false', 'aria-controls': id + '-details' }, [
        el('span', { 'class': 'avatar is-small', style: 'background:' + c.color, 'aria-hidden': 'true', text: c.initials }),
        el('span', { 'class': 'commit-main' }, [
          el('span', { 'class': 'commit-subject' }, [tag, el('span', { 'class': 'commit-subject-text', text: c.subject || '(empty message)' })]),
          el('span', { 'class': 'commit-meta', style: 'display:block', text: c.author + ' · ' + fmtDay(c.when) + ', ' + c.when.slice(11, 16) + ' · ' + c.hash.slice(0, 7) })
        ]),
        c.merge && !c.filesTotal ? el('span', { 'class': 'commit-side' }, el('span', { 'class': 'commit-files' }, [
          'merged branch', el('span', { 'class': 'commit-chevron', 'aria-hidden': 'true', text: '▾' })
        ])) : el('span', { 'class': 'commit-side' }, [
          el('span', { 'class': 'commit-diff' }, [
            el('span', { 'class': 'add', text: '+' + fmtNum(c.added) }),
            el('span', { 'class': 'del', text: '−' + fmtNum(c.removed) })
          ]),
          lines ? el('span', { 'class': 'diffbar', 'aria-hidden': 'true' }, [
            c.added ? el('i', { 'class': 'is-added', style: 'flex:' + c.added }) : null,
            c.removed ? el('i', { 'class': 'is-removed', style: 'flex:' + c.removed }) : null
          ]) : null,
          el('span', { 'class': 'commit-files' }, [
            count(c.filesTotal, 'file', 'files'),
            el('span', { 'class': 'commit-chevron', 'aria-hidden': 'true', text: '▾' })
          ])
        ])
      ]);
      var inner = el('div', { 'class': 'commit-details-inner' });
      var panel = el('div', { 'class': 'commit-details', id: id + '-details', role: 'region', 'aria-label': 'Changes in ' + c.hash.slice(0, 7) }, inner);
      head.addEventListener('click', function () { toggle(item, head, inner, c); });
      item.addEventListener('animationend', function (event) {
        if (event.target === item) item.classList.remove('is-entering');
      });
      return append(item, el('article', { 'class': 'commit-card' }, [head, panel]));
    }

    function toggle(item, head, inner, c, forceOpen) {
      var open = forceOpen != null ? forceOpen : !item.classList.contains('is-open');
      if (open && !inner.firstChild) inner.appendChild(details(c)); // built on first open only
      item.classList.toggle('is-open', open);
      head.setAttribute('aria-expanded', String(open));
    }

    function updateStatus() {
      var n = state.matches.length;
      var filtered = state.query || state.type || state.lineage;
      var text;
      if (!n) text = 'No commits match.';
      else if (filtered) text = 'Showing ' + fmtNum(state.shown) + ' of ' + count(n, 'matching commit', 'matching commits') + '.';
      else text = 'Showing ' + fmtNum(state.shown) + ' of ' + count(n, 'commit', 'commits') + ', newest first.';
      if (H.total > total && !filtered) text += ' This report includes the newest ' + fmtNum(total) + ' of ' + fmtNum(H.total) + '.';
      status.textContent = text;
      var left = n - state.shown;
      more.parentNode.hidden = left <= 0;
      more.textContent = '';
      append(more, ['Load ' + Math.min(PAGE, left) + ' more', el('small', { text: '(' + fmtNum(left) + ' left)' })]);
      typeButtons.forEach(function (b) { b.setAttribute('aria-pressed', String(b._value === state.type)); });
    }

    function showMore(focusFirst) {
      var next = state.matches.slice(state.shown, state.shown + PAGE);
      var first = null;
      next.forEach(function (c, i) {
        var node = card(c, i);
        if (!first) first = node;
        list.appendChild(node);
      });
      state.shown += next.length;
      updateStatus();
      if (focusFirst && first) first.querySelector('.commit-head').focus({ preventScroll: true });
    }

    function refresh(reset) {
      state.matches = commits.filter(matches);
      if (reset) {
        list.textContent = '';
        state.shown = 0;
        showMore(false);
      } else {
        updateStatus();
      }
    }

    function showFileHistory(lineage, path) {
      state.lineage = lineage;
      // Name the file by its newest name, from the most recent commit that touched it.
      var latest = path;
      for (var i = 0; i < commits.length; i++) {
        var hit = commits[i].files.filter(function (f) { return f.lineage === lineage; })[0];
        if (hit) { latest = hit.path; break; }
      }
      fileFilter.textContent = '';
      append(fileFilter, [
        el('span', null, ['Every commit that changed ', el('span', { 'class': 'mono', text: latest })]),
        (function () {
          var clear = el('button', { type: 'button', text: 'Show all commits ✕' });
          clear.addEventListener('click', function () { state.lineage = 0; fileFilter.hidden = true; refresh(true); });
          return clear;
        })()
      ]);
      fileFilter.hidden = false;
      refresh(true);
      section.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }

    var debounce = null;
    search.addEventListener('input', function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        state.query = search.value.trim().toLowerCase();
        refresh(true);
      }, 150);
    });

    more.addEventListener('click', function (event) { showMore(event.detail === 0); });

    function open() {
      if (!browser.hidden) return;
      byId('history-start').hidden = true;
      opener.setAttribute('aria-expanded', 'true');
      browser.hidden = false;
      if (!reduceMotion) browser.classList.add('is-entering');
      refresh(true);
      list.focus({ preventScroll: true });
    }
    opener.addEventListener('click', open);

    // Used by other chapters: open the history on one commit.
    return function jumpTo(hashPrefix) {
      open();
      state.query = hashPrefix.toLowerCase();
      state.type = '';
      state.lineage = 0;
      fileFilter.hidden = true;
      search.value = hashPrefix;
      refresh(true);
      var item = list.firstChild;
      if (item) {
        toggle(item, item.querySelector('.commit-head'), item.querySelector('.commit-details-inner'),
          state.matches[0], true);
        item.classList.add('is-flash');
      }
      section.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    };
  }

  var jumpToCommit = null;

  // A short hash that opens the commit in the history chapter, when there is one.
  function hashRef(hash) {
    if (!jumpToCommit) return el('span', { 'class': 'mono', text: hash });
    var button = el('button', { type: 'button', 'class': 'hash-link', title: 'Open this commit in the commit history', text: hash });
    button.addEventListener('click', function () { jumpToCommit(hash); });
    return button;
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
      el('figcaption', { 'class': 'quote-meta' }, [ref.author + ', ' + fmtDay(ref.when) + ', ', hashRef(ref.hash)])
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
          hashRef(big.hash), ').'
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
      if (!isLocalPath(link.href)) return;
      nav.appendChild(el('a', { href: link.href, text: link.label }));
    });
    if (nav.children.length) document.body.classList.add('has-nav-links');
    nav.appendChild(renderDownload());
    nav.hidden = false;
  }

  function isLocalPath(href) {
    return typeof href === 'string' && href.charAt(0) === '/' && href.charAt(1) !== '/';
  }

  // ---------------------------------------------------------------- download

  var DOWNLOADS = [
    { kind: 'png', title: 'Long image', ext: '.png',
      text: 'One tall picture of the whole story, ready to share.' },
    { kind: 'pdf', title: 'PDF', ext: '.pdf',
      text: 'Numbered A4 pages to print or attach, split between sections.' },
    { kind: 'html', title: 'HTML', ext: '.html',
      text: 'Works offline, anywhere, with the clickable commit history and search.' }
  ];

  var ICONS = {
    png: 'M4 5h16v14H4zM4 15l4.5-4.5 4 4 2.5-2.5L20 17M15.5 9.5h.01',
    pdf: 'M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 15.5h5M10 19h3',
    html: 'M8.5 8 4.5 12l4 4M15.5 8l4 4-4 4M13.5 6l-3 12'
  };

  function icon(kind) {
    return svg('svg', { viewBox: '0 0 24 24', width: 20, height: 20, 'aria-hidden': 'true' },
      [svg('path', { d: ICONS[kind] })]);
  }

  function fileStem() {
    var stem = String(DATA.repo_name || 'story').replace(/[^\w.-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '');
    return (stem || 'story') + '-gitstory';
  }

  function renderDownload() {
    var wrap = el('div', { 'class': 'dl' });
    var button = el('button', {
      'class': 'dl-button', type: 'button', id: 'download-button',
      'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-controls': 'download-menu'
    }, [
      svg('svg', { viewBox: '0 0 24 24', width: 16, height: 16, 'aria-hidden': 'true' },
        [svg('path', { d: 'M12 4v11M7 10.5l5 5 5-5M5 20h14' })]),
      'Download story',
      el('span', { 'class': 'dl-caret', 'aria-hidden': 'true', text: '▾' })
    ]);
    var menu = el('div', { 'class': 'dl-menu', id: 'download-menu', role: 'menu', 'aria-label': 'Download story', hidden: 'hidden' });
    var status = el('p', { 'class': 'dl-status', role: 'status', 'aria-live': 'polite' });
    var busy = false;

    menu.appendChild(el('p', { 'class': 'dl-menu-title', text: 'Save this story as' }));
    var items = DOWNLOADS.map(function (option, i) {
      var item = el('button', { 'class': 'dl-item', type: 'button', role: 'menuitem', 'data-kind': option.kind, style: '--i:' + i }, [
        el('span', { 'class': 'dl-icon' }, [icon(option.kind)]),
        el('span', { 'class': 'dl-text' }, [
          el('strong', { text: option.title }),
          el('small', { text: option.text })
        ]),
        el('span', { 'class': 'dl-ext', text: option.ext })
      ]);
      item.addEventListener('click', function () { run(option, item); });
      menu.appendChild(item);
      return item;
    });
    menu.appendChild(status);
    menu.appendChild(el('p', { 'class': 'dl-note', text:
      'The image and PDF leave out the commit history and other buttons, since paper cannot be clicked. The HTML keeps everything.' }));
    append(wrap, [button, menu]);

    function open() {
      if (!menu.hidden) return;
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      wrap.classList.add('is-open');
      items[0].focus({ preventScroll: true });
      document.addEventListener('mousedown', outside, true);
    }
    function close(refocus) {
      if (menu.hidden || busy) return;
      menu.hidden = true;
      button.setAttribute('aria-expanded', 'false');
      wrap.classList.remove('is-open');
      document.removeEventListener('mousedown', outside, true);
      if (refocus) button.focus({ preventScroll: true });
    }
    function outside(event) { if (!wrap.contains(event.target)) close(false); }

    button.addEventListener('click', function () { if (menu.hidden) open(); else close(true); });
    wrap.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { event.preventDefault(); close(true); return; }
      if (menu.hidden || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return;
      event.preventDefault();
      var at = items.indexOf(document.activeElement);
      var next = event.key === 'ArrowDown' ? at + 1 : at - 1;
      items[(next + items.length) % items.length].focus();
    });

    function say(text, tone) {
      status.textContent = text;
      status.className = 'dl-status' + (tone ? ' is-' + tone : '');
    }

    function run(option, item) {
      if (busy) return;
      busy = true;
      wrap.classList.add('is-busy');
      items.forEach(function (other) { other.disabled = true; });
      item.classList.add('is-working');
      var name = fileStem() + option.ext;
      var job = option.kind === 'html' ? saveHtml(name)
        : makeSnapshot(say).then(function (shot) {
          return option.kind === 'png' ? savePng(shot, name, say) : savePdf(shot, name, say);
        });
      job.then(function () {
        say('Saved ' + name, 'done');
      }, function (error) {
        say(error && error.userMessage ? error.userMessage :
          'Could not make the ' + option.title.toLowerCase() + ' in this browser. Try Chrome, Edge or Firefox, ' +
          'or download the HTML and use your browser\'s Print → Save as PDF.', 'error');
        if (window.console) console.error(error);
      }).then(function () {
        busy = false;
        wrap.classList.remove('is-busy');
        item.classList.remove('is-working');
        items.forEach(function (other) { other.disabled = false; });
        item.focus({ preventScroll: true });
      });
    }

    return wrap;
  }

  function saveBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = el('a', { href: url, download: name });
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function fail(message) { var error = new Error(message); error.userMessage = message; return error; }

  // HTML: in web mode the server sends a clean copy (no links back to it);
  // a page opened from a file saves the copy it was opened from.
  function saveHtml(name) {
    var server = DATA.meta && DATA.meta.download;
    if (isLocalPath(server) && /^https?:$/.test(location.protocol)) {
      return fetch(server).then(function (response) {
        if (!response.ok) throw fail('The server no longer has this story. Build it again from the home page.');
        return response.blob();
      }).then(function (blob) { saveBlob(blob, name); });
    }
    var theme = root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    var page = PRISTINE.replace(/(<html\b[^>]*?\bdata-theme=")[^"]*"/, '$1' + theme + '"');
    saveBlob(new Blob([page], { type: 'text/html;charset=utf-8' }), name);
    return Promise.resolve();
  }

  // ---- drawing the page onto a canvas
  // The visible page is copied into an SVG <foreignObject> with the report's
  // own stylesheet, every animation finished, and drawn onto a canvas. No
  // libraries and no network: everything the page needs is already inline.

  var MAX_SIDE = 32000;          // browsers refuse taller canvases
  var MAX_AREA = 120 * 1000 * 1000;
  var BREAK_AT = 'h2, h3, p, li, .panel, .tile, .fact, .persona, .footer';

  // One painted frame; a timer backs it up because hidden tabs pause animation frames.
  function nextFrame() {
    return new Promise(function (done) {
      var finished = false;
      function go() { if (!finished) { finished = true; done(); } }
      requestAnimationFrame(go);
      setTimeout(go, 120);
    });
  }

  function each(scope, selector, fn) { Array.prototype.forEach.call(scope.querySelectorAll(selector), fn); }

  // A copy of the story made for paper: every animation at its end, every
  // contributor shown, and nothing that only works when clicked (the commit
  // history, "show all" buttons, jump-to-commit links).
  function printableCopy() {
    return [document.querySelector('main'), document.querySelector('.footer')].map(function (part) {
      var copy = part.cloneNode(true);
      each(copy, '#history, script, .tooltip', function (node) { node.remove(); });
      each(copy, '.reveal', function (node) { node.classList.add('is-visible'); });
      each(copy, '.num[data-count]', function (node) {
        node.textContent = (node.getAttribute('data-prefix') || '') + fmtNum(+node.getAttribute('data-count'));
      });
      each(copy, '#tl-clip rect', function (node) { node.setAttribute('width', '100000'); });
      each(copy, '.people > [hidden]', function (node) { node.removeAttribute('hidden'); });
      each(copy, '[data-export-text]', function (node) {
        node.textContent = node.getAttribute('data-export-text');
        if (!node.textContent) node.remove();
      });
      each(copy, 'button.hash-link', function (node) {
        node.parentNode.replaceChild(el('span', { 'class': 'mono', text: node.textContent }), node);
      });
      return copy;
    });
  }

  // Lay the copy out off-screen (same width, same media queries) to learn
  // its height and where pages may be cut, without moving the live page.
  function measure(parts, width) {
    var box = el('div', { 'aria-hidden': 'true' });
    box.setAttribute('style', 'position:fixed;left:0;top:0;width:' + width + 'px;display:flow-root;' +
      'visibility:hidden;pointer-events:none;z-index:-1');
    parts.forEach(function (part) { box.appendChild(part); });
    document.body.appendChild(box);
    var top = box.getBoundingClientRect().top;
    var height = Math.ceil(box.getBoundingClientRect().height);
    var breaks = [0];
    each(box, BREAK_AT, function (node) {
      var rect = node.getBoundingClientRect();
      if (!rect.height) return;                       // not displayed
      var y = Math.round(rect.top - top);
      if (y > 0 && y < height) breaks.push(y);
    });
    breaks.sort(function (a, b) { return a - b; });
    box.remove();
    return { height: height, breaks: breaks };
  }

  function makeSnapshot(say) {
    say('Getting the page ready…');
    root.classList.add('is-capturing');
    return nextFrame().then(function () {
      var width = root.clientWidth;
      var parts = printableCopy();
      var layout = measure(parts, width);
      var source = shotMarkup(parts, width, layout.height);
      root.classList.remove('is-capturing');
      say('Drawing the page…');
      return loadImage(source).then(function (image) {
        var height = layout.height;
        var scale = Math.min(2, MAX_SIDE / height, Math.sqrt(MAX_AREA / (width * height)));
        var canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.floor(width * scale));
        canvas.height = Math.max(1, Math.floor(height * scale));
        var ctx = canvas.getContext('2d');
        ctx.fillStyle = cssVar('--bg') || '#0a1020';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        return { canvas: canvas, width: width, height: height, scale: canvas.width / width, breaks: layout.breaks };
      });
    }).catch(function (error) { root.classList.remove('is-capturing'); throw error; });
  }

  function cssVar(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }

  function shotMarkup(parts, width, height) {
    var css = Array.prototype.map.call(document.querySelectorAll('style'), function (s) { return s.textContent; }).join('\n');
    // Custom properties live on :root, which a copied <body> does not have.
    var vars = {};
    (css.match(/--[\w-]+(?=\s*:)/g) || []).forEach(function (name) { vars[name] = cssVar(name); });
    var inline = Object.keys(vars).map(function (name) { return name + ':' + vars[name]; }).join(';');

    var body = document.createElement('body');
    body.className = document.body.className;      // same classes as when measured
    body.setAttribute('data-theme', root.getAttribute('data-theme') || 'dark');
    body.setAttribute('style', inline + ';margin:0;width:' + width + 'px;height:' + height + 'px;overflow:hidden');
    var style = document.createElement('style');
    style.textContent = css + '\n*,*::before,*::after{animation:none!important;transition:none!important}';
    body.appendChild(style);
    parts.forEach(function (part) { body.appendChild(part); });

    var xhtml = new XMLSerializer().serializeToString(body);
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '">' +
      '<foreignObject x="0" y="0" width="100%" height="100%">' + xhtml + '</foreignObject></svg>';
  }

  function loadImage(markup) {
    return new Promise(function (resolve, reject) {
      var image = new Image();
      image.onload = function () { resolve(image); };
      image.onerror = function () { reject(new Error('the page could not be drawn as an image')); };
      image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(markup);
    });
  }

  function toBlob(canvas, type, quality) {
    return new Promise(function (resolve, reject) {
      try {
        canvas.toBlob(function (blob) {
          if (blob) resolve(blob); else reject(new Error('the browser could not encode the image'));
        }, type, quality);
      } catch (error) { reject(error); }   // a "tainted" canvas (Safari) throws here
    });
  }

  function savePng(shot, name, say) {
    say('Saving the image…');
    return toBlob(shot.canvas, 'image/png').then(function (blob) { saveBlob(blob, name); });
  }

  // ---- PDF: the drawing cut into A4 pages, each page one JPEG.
  var A4 = { w: 595.28, h: 841.89 };
  var PAGE_FOOTER = 40;                // CSS pixels kept free at the bottom of each page

  function pageSlices(shot) {
    var pageHeight = Math.floor(shot.width * A4.h / A4.w);
    var pad = 28;                      // breathing room above the content on later pages
    var slices = [], y = 0;
    while (y < shot.height - 2) {
      var room = pageHeight - (slices.length ? pad : 0) - PAGE_FOOTER;
      var end = y + room;
      if (end >= shot.height) { end = shot.height; }
      else {
        // Cut just above the last block that starts on this page, unless
        // that would leave the page less than half full.
        var cut = end;
        for (var i = shot.breaks.length - 1; i >= 0; i--) {
          var b = shot.breaks[i] - 12;
          if (b <= end && b > y + room * 0.5) { cut = b; break; }
          if (b <= y + room * 0.5) break;
        }
        end = cut;
      }
      slices.push({ top: y, height: end - y, pad: slices.length ? pad : 0, pageHeight: pageHeight });
      y = end;
    }
    return slices;
  }

  function savePdf(shot, name, say) {
    var slices = pageSlices(shot);
    var scale = shot.scale, background = cssVar('--bg') || '#0a1020';
    var pages = [];
    var chain = Promise.resolve();
    slices.forEach(function (slice, i) {
      chain = chain.then(function () {
        say('Laying out page ' + (i + 1) + ' of ' + slices.length + '…');
        var page = document.createElement('canvas');
        page.width = Math.round(shot.width * scale);
        page.height = Math.round(slice.pageHeight * scale);
        var ctx = page.getContext('2d');
        ctx.fillStyle = background;
        ctx.fillRect(0, 0, page.width, page.height);
        var sy = Math.round(slice.top * scale), sh = Math.round(slice.height * scale);
        ctx.drawImage(shot.canvas, 0, sy, shot.canvas.width, sh, 0, Math.round(slice.pad * scale), page.width, sh);
        pageFooter(ctx, scale, shot.width, slice.pageHeight, i + 1, slices.length);
        return toBlob(page, 'image/jpeg', 0.9).then(function (blob) { return blob.arrayBuffer(); }).then(function (buffer) {
          pages.push({ bytes: new Uint8Array(buffer), width: page.width, height: page.height });
        });
      });
    });
    return chain.then(function () {
      say('Saving the PDF…');
      saveBlob(buildPdf(pages, DATA.repo_name + ' · gitstory'), name);
    });
  }

  // "repo · gitstory" on the left, "Page 2 of 5" on the right, in the margin of the drawing.
  function pageFooter(ctx, scale, width, height, number, total) {
    var gutter = parseFloat(cssVar('--gutter')) || 40;
    var y = (height - PAGE_FOOTER / 2) * scale;
    ctx.save();
    ctx.scale(scale, scale);
    ctx.font = '12px ' + (cssVar('--sans') || 'sans-serif');
    ctx.fillStyle = cssVar('--muted') || '#8d97b5';
    ctx.textBaseline = 'middle';
    ctx.strokeStyle = cssVar('--line') || 'rgba(160,176,224,0.16)';
    ctx.beginPath();
    ctx.moveTo(gutter, height - PAGE_FOOTER + 6);
    ctx.lineTo(width - gutter, height - PAGE_FOOTER + 6);
    ctx.stroke();
    ctx.textAlign = 'left';
    ctx.fillText(DATA.repo_name + ' · gitstory', gutter, y / scale);
    ctx.textAlign = 'right';
    ctx.fillText('Page ' + number + ' of ' + total, width - gutter, y / scale);
    ctx.restore();
  }

  function pdfText(text) {
    // UTF-16BE with a byte-order mark, as hex: safe for any title.
    var hex = 'FEFF';
    for (var i = 0; i < text.length; i++) hex += ('000' + text.charCodeAt(i).toString(16)).slice(-4).toUpperCase();
    return '<' + hex + '>';
  }

  function buildPdf(pages, title) {
    var encoder = new TextEncoder();
    var parts = [], offsets = [], length = 0;
    function add(chunk) {
      var bytes = typeof chunk === 'string' ? encoder.encode(chunk) : chunk;
      parts.push(bytes);
      length += bytes.length;
    }
    function object(id, body, stream) {
      offsets[id] = length;
      add(id + ' 0 obj\n' + body + '\n');
      if (stream) { add('stream\n'); add(stream); add('\nendstream\n'); }
      add('endobj\n');
    }
    var w = A4.w.toFixed(2), h = A4.h.toFixed(2);
    add('%PDF-1.4\n');
    add(new Uint8Array([0x25, 0xE2, 0xE3, 0xCF, 0xD3, 0x0A]));
    var kids = pages.map(function (_, i) { return (4 + i * 3) + ' 0 R'; }).join(' ');
    object(1, '<< /Type /Catalog /Pages 2 0 R >>');
    object(2, '<< /Type /Pages /Kids [' + kids + '] /Count ' + pages.length + ' >>');
    object(3, '<< /Title ' + pdfText(title) + ' /Creator (gitstory) /Producer (gitstory) >>');
    pages.forEach(function (page, i) {
      var id = 4 + i * 3;
      var draw = encoder.encode('q ' + w + ' 0 0 ' + h + ' 0 0 cm /Im0 Do Q');
      object(id, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + w + ' ' + h + '] ' +
        '/Resources << /XObject << /Im0 ' + (id + 2) + ' 0 R >> >> /Contents ' + (id + 1) + ' 0 R >>');
      object(id + 1, '<< /Length ' + draw.length + ' >>', draw);
      object(id + 2, '<< /Type /XObject /Subtype /Image /Width ' + page.width + ' /Height ' + page.height +
        ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ' + page.bytes.length + ' >>', page.bytes);
    });
    var count = 3 + pages.length * 3;
    var xref = length;
    var table = 'xref\n0 ' + (count + 1) + '\n0000000000 65535 f \n';
    for (var id = 1; id <= count; id++) table += ('000000000' + offsets[id]).slice(-10) + ' 00000 n \n';
    add(table);
    add('trailer\n<< /Size ' + (count + 1) + ' /Root 1 0 R /Info 3 0 R >>\nstartxref\n' + xref + '\n%%EOF\n');
    return new Blob(parts, { type: 'application/pdf' });
  }

  function setupReveal(hooks) {
    var sections = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
    function show(section) {
      if (section.classList.contains('is-visible')) return;
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
  jumpToCommit = renderHistory();
  renderMessages();
  renderFacts();
  renderFooter();
  setupReveal({ timeline: startTimeline });
  window.addEventListener('scroll', hideTip, { passive: true });
})();

/* MaterialScope landing — page behavior.
   Vanilla JS by design: the page needs reveals, one SVG plot renderer, and a
   waitlist POST; pulling an animation library in for that would be the
   heavier option. Honors prefers-reduced-motion throughout. */
(function () {
    'use strict';

    var TRACES = window.MS_TRACES || {};
    var ORDER = ['dsc', 'tga', 'dta', 'ftir', 'raman', 'xrd'];
    var MODALITY_SCOPE = {
        dsc: 'Thermal events, onset, and melting behavior across scans.',
        tga: 'Mass-loss steps and comparative thermal stability.',
        dta: 'Differential thermal response and run-to-run comparison.',
        ftir: 'Spectra, absorption bands, and functional-group review.',
        raman: 'Spectral comparison and peak-focused inspection.',
        xrd: 'Diffraction patterns, peak lists, and phase review.'
    };
    var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var SVG_NS = 'http://www.w3.org/2000/svg';

    function scrollToEl(target, block) {
        if (!target) return;
        if (target.scrollIntoView) {
            target.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: block || 'start' });
        }
    }

    function $(sel, root) { return (root || document).querySelector(sel); }
    function el(tag, attrs, kids) {
        var node = document.createElementNS(SVG_NS, tag);
        if (attrs) { for (var k in attrs) node.setAttribute(k, attrs[k]); }
        (kids || []).forEach(function (child) { node.appendChild(child); });
        return node;
    }
    function txt(tag, attrs, content) {
        var node = el(tag, attrs);
        node.textContent = content;
        return node;
    }
    function rAFThrottle(fn) {
        var queued = false;
        return function () {
            if (queued) return;
            queued = true;
            requestAnimationFrame(function () { queued = false; fn(); });
        };
    }

    /* ── Theme toggle ─────────────────────────────────────────────────── */

    var root = document.documentElement;
    var themeBtn = $('#theme-toggle');
    if (themeBtn) {
        function syncThemeLabel() {
            var dark = root.getAttribute('data-theme') === 'dark';
            themeBtn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
        }
        themeBtn.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            try { localStorage.setItem('ms-theme', next); } catch (e) { /* private mode */ }
            syncThemeLabel();
        });
        syncThemeLabel();
    }

    /* ── Navbar: solidify on scroll, mobile sheet, scrollspy ──────────── */

    var nav = $('#nav');
    if (nav) {
        var syncNav = rAFThrottle(function () {
            nav.classList.toggle('nav--solid', window.scrollY > 8);
        });
        window.addEventListener('scroll', syncNav, { passive: true });
        syncNav();
    }

    var burger = $('#nav-burger');
    var sheet = $('#nav-sheet');
    function setSheet(open) {
        if (!burger || !sheet) return;
        sheet.hidden = !open;
        burger.setAttribute('aria-expanded', open ? 'true' : 'false');
        burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    }
    if (burger && sheet) {
        burger.addEventListener('click', function () { setSheet(sheet.hidden); });
        sheet.addEventListener('click', function (e) {
            if (e.target.closest('a')) setSheet(false);
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !sheet.hidden) { setSheet(false); burger.focus(); }
        });
        window.addEventListener('resize', function () {
            if (window.innerWidth > 880) setSheet(false);
        });
    }

    var spySections = ['#why', '#how', '#capabilities', '#modalities', '#who']
        .map(function (id) { return document.querySelector(id); })
        .filter(Boolean);
    if (spySections.length && 'IntersectionObserver' in window) {
        var spy = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                var link = document.querySelector('.nav-links a[href="#' + entry.target.id + '"]');
                if (link && entry.isIntersecting) {
                    spySections.forEach(function (sec) {
                        var a = document.querySelector('.nav-links a[href="#' + sec.id + '"]');
                        if (a && sec !== entry.target) a.classList.remove('is-current');
                    });
                    link.classList.add('is-current');
                }
            });
        }, { rootMargin: '-35% 0px -55% 0px' });
        spySections.forEach(function (sec) { spy.observe(sec); });
    }

    /* ── Scroll reveals ────────────────────────────────────────────────── */

    var revealables = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    if (REDUCED || !('IntersectionObserver' in window)) {
        revealables.forEach(function (node) { node.classList.add('is-in'); });
    } else {
        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-in');
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
        revealables.forEach(function (node) { revealObserver.observe(node); });
    }

    /* ── Trace panel: real sample curves rendered as an SVG plot ───────── */

    var stage = $('#trace-stage');
    var tabsHost = $('#trace-tabs');
    var fileLabel = $('#trace-file');
    var metaChip = $('#trace-meta');
    var readout = $('#trace-readout');
    var current = TRACES.xrd ? 'xrd' : ORDER[0];

    var W = 760, H = 430, ML = 66, MR = 18, MT = 28, MB = 48;
    var PW = W - ML - MR, PH = H - MT - MB;

    function fmtValue(v, unit) {
        var out;
        if (Math.abs(v) >= 1000) out = Math.round(v).toLocaleString('en-US');
        else if (Math.abs(v) >= 100) out = v.toFixed(1).replace(/\.0$/, '');
        else out = v.toFixed(2).replace(/\.?0+$/, '') || '0';
        return unit ? out + ' ' + unit : out;
    }

    function toPx(trace, nx, ny) {
        var x = trace.xReversed ? 1 - nx : nx;
        return [ML + x * PW, MT + ny * PH];
    }

    function buildPath(trace, close) {
        var pts = trace.points;
        var d = '';
        for (var i = 0; i < pts.length; i++) {
            var p = toPx(trace, pts[i][0], pts[i][1]);
            d += (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1);
        }
        if (close && pts.length) {
            var last = toPx(trace, pts[pts.length - 1][0], 1);
            var first = toPx(trace, pts[0][0], 1);
            d += 'L' + last[0].toFixed(1) + ' ' + (MT + PH).toFixed(1) +
                 'L' + first[0].toFixed(1) + ' ' + (MT + PH).toFixed(1) + 'Z';
        }
        return d;
    }

    function renderTrace(trace, animate) {
        if (!stage || !trace) return;
        var svg = el('svg', {
            viewBox: '0 0 ' + W + ' ' + H,
            role: 'img',
            'aria-label': trace.title + ' trace: ' + trace.full + ', sample file ' + trace.file
        });

        var defs = el('defs');
        var grad = el('linearGradient', { id: 'trace-area-grad', x1: '0', y1: '0', x2: '0', y2: '1' });
        grad.appendChild(el('stop', { offset: '0%', 'stop-color': 'var(--trace)', 'stop-opacity': '0.16' }));
        grad.appendChild(el('stop', { offset: '100%', 'stop-color': 'var(--trace)', 'stop-opacity': '0' }));
        defs.appendChild(grad);
        svg.appendChild(defs);

        var grid = el('g');
        var ticksX = trace.xTicks || [];
        var ticksY = trace.yTicks || [];
        ticksX.forEach(function (t, i) {
            var nx = (t - trace.xDomain[0]) / (trace.xDomain[1] - trace.xDomain[0]);
            var px = toPx(trace, nx, 0)[0];
            grid.appendChild(el('line', { x1: px, y1: MT, x2: px, y2: MT + PH, class: 'stage-grid' }));
            grid.appendChild(txt('text', { x: px, y: MT + PH + 17, 'text-anchor': 'middle', class: 'tick-label' },
                (trace.xTicksLabel && trace.xTicksLabel[i] != null) ? trace.xTicksLabel[i] : String(t)));
        });
        ticksY.forEach(function (t, i) {
            var ny = 1 - (t - trace.yDomain[0]) / (trace.yDomain[1] - trace.yDomain[0]);
            var py = MT + ny * PH;
            grid.appendChild(el('line', { x1: ML, y1: py, x2: ML + PW, y2: py, class: 'stage-grid' }));
            grid.appendChild(txt('text', { x: ML - 8, y: py + 3.5, 'text-anchor': 'end', class: 'tick-label' },
                (trace.yTicksLabel && trace.yTicksLabel[i] != null) ? trace.yTicksLabel[i] : String(t)));
        });
        grid.appendChild(txt('text', { x: W - MR, y: H - 12, 'text-anchor': 'end', class: 'axis-title' },
            trace.xLabel + ' / ' + trace.xUnit));
        grid.appendChild(txt('text', { x: 6, y: 15, 'text-anchor': 'start', class: 'axis-title' },
            trace.yLabel + ' / ' + trace.yUnit));
        svg.appendChild(grid);

        var area = el('path', { d: buildPath(trace, true), class: 'trace-area' });
        var glow = el('path', { d: buildPath(trace, false), class: 'trace-glow' });
        var line = el('path', { d: buildPath(trace, false), class: 'trace-line' });
        svg.appendChild(area);
        svg.appendChild(glow);
        svg.appendChild(line);

        var annLayer = el('g');
        var lastEnd = -Infinity;
        var row = 0;
        (trace.annotations || []).forEach(function (ann) {
            var nx = (ann.x - trace.xDomain[0]) / (trace.xDomain[1] - trace.xDomain[0]);
            var ny = 1 - (ann.y - trace.yDomain[0]) / (trace.yDomain[1] - trace.yDomain[0]);
            var p = toPx(trace, nx, ny);
            annLayer.appendChild(el('line', { x1: p[0], y1: p[1] - 6, x2: p[0], y2: MT + 6, class: 'ann-line' }));
            annLayer.appendChild(el('circle', { cx: p[0], cy: p[1], r: 3, class: 'ann-dot' }));
            var est = ann.label.length * 7.2;
            if (p[0] - est / 2 < lastEnd + 10) { row += 1; } else { row = 0; }
            lastEnd = p[0] + est / 2;
            var ly = Math.max(MT + 12, p[1] - 14 - row * 15);
            var lx = Math.min(Math.max(p[0], ML + est / 2 + 4), W - MR - est / 2 - 4);
            annLayer.appendChild(txt('text', { x: lx, y: ly, 'text-anchor': 'middle', class: 'ann-label' }, ann.label));
        });
        svg.appendChild(annLayer);

        var cursor = el('g', { 'data-cursor': 'true', opacity: '0' });
        var cLine = el('line', { y1: MT, y2: MT + PH, class: 'cursor-line' });
        var cDot = el('circle', { r: 3.6, class: 'cursor-dot' });
        cursor.appendChild(cLine);
        cursor.appendChild(cDot);
        svg.appendChild(cursor);

        stage.replaceChildren(svg);
        attachReadout(svg, trace, cLine, cDot);

        if (fileLabel) fileLabel.textContent = trace.file;
        if (metaChip) metaChip.textContent = trace.meta;
        if (readout) readout.innerHTML = '&nbsp;';

        if (animate && !REDUCED) {
            [line, glow].forEach(function (path) {
                var len = path.getTotalLength();
                path.style.strokeDasharray = String(len);
                path.style.strokeDashoffset = String(len);
                area.style.opacity = '0';
                requestAnimationFrame(function () {
                    path.style.transition = 'stroke-dashoffset 1s cubic-bezier(0.4, 0.1, 0.2, 1)';
                    area.style.transition = 'opacity 0.6s ease 0.3s';
                    path.style.strokeDashoffset = '0';
                    area.style.opacity = '1';
                    path.addEventListener('transitionend', function clear() {
                        path.style.strokeDasharray = '';
                        path.style.strokeDashoffset = '';
                        path.style.transition = '';
                        path.removeEventListener('transitionend', clear);
                    });
                });
            });
            annLayer.style.opacity = '0';
            requestAnimationFrame(function () {
                annLayer.style.transition = 'opacity 0.5s ease 0.55s';
                annLayer.style.opacity = '1';
            });
        }
    }

    function attachReadout(svg, trace, cLine, cDot) {
        if (!readout) return;
        var pts = trace.points;
        function move(sx) {
            var best = 0;
            var bestDist = Infinity;
            for (var i = 0; i < pts.length; i++) {
                var p = toPx(trace, pts[i][0], pts[i][1]);
                var dist = Math.abs(p[0] - sx);
                if (dist < bestDist) { bestDist = dist; best = i; }
            }
            var bp = toPx(trace, pts[best][0], pts[best][1]);
            cLine.setAttribute('x1', bp[0]);
            cLine.setAttribute('x2', bp[0]);
            cDot.setAttribute('cx', bp[0]);
            cDot.setAttribute('cy', bp[1]);
            cLine.parentNode.setAttribute('opacity', '1');
            var dx = trace.xDomain[0] + pts[best][0] * (trace.xDomain[1] - trace.xDomain[0]);
            var dy = trace.yDomain[0] + (1 - pts[best][1]) * (trace.yDomain[1] - trace.yDomain[0]);
            readout.textContent = trace.xLabel + ' ' + fmtValue(dx, trace.xUnit) + ' · ' + trace.yLabel + ' ' + fmtValue(dy, trace.yUnit);
        }
        function leave() {
            cLine.parentNode.setAttribute('opacity', '0');
            readout.innerHTML = '&nbsp;';
        }
        var lastX = 0;
        var schedule = rAFThrottle(function () { move(lastX); });
        svg.addEventListener('pointermove', function (e) {
            var rect = svg.getBoundingClientRect();
            if (!rect.width) return;
            lastX = (e.clientX - rect.left) / rect.width * W;
            schedule();
        });
        svg.addEventListener('pointerleave', leave);
        svg.addEventListener('pointercancel', leave);
    }

    if (tabsHost && Object.keys(TRACES).length) {
        ORDER.forEach(function (key) {
            if (!TRACES[key]) return;
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = TRACES[key].title;
            btn.setAttribute('data-key', key);
            btn.setAttribute('aria-pressed', key === current ? 'true' : 'false');
            btn.setAttribute('aria-label', 'Show ' + TRACES[key].full + ' sample trace');
            tabsHost.appendChild(btn);
        });
        tabsHost.addEventListener('click', function (e) {
            var btn = e.target.closest('button[data-key]');
            if (btn) selectModality(btn.getAttribute('data-key'), true);
        });
        tabsHost.addEventListener('keydown', function (e) {
            if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
            var keys = ORDER.filter(function (k) { return !!TRACES[k]; });
            var idx = keys.indexOf(current);
            if (idx < 0) return;
            var next = keys[(idx + (e.key === 'ArrowRight' ? 1 : keys.length - 1)) % keys.length];
            selectModality(next, true);
            var btn = tabsHost.querySelector('button[data-key="' + next + '"]');
            if (btn) btn.focus();
            e.preventDefault();
        });
    }

    function selectModality(key, animate) {
        if (!TRACES[key]) return;
        current = key;
        if (tabsHost) {
            Array.prototype.forEach.call(tabsHost.querySelectorAll('button'), function (b) {
                b.setAttribute('aria-pressed', b.getAttribute('data-key') === key ? 'true' : 'false');
            });
        }
        renderTrace(TRACES[key], !!animate);
    }

    // Draw once the panel is actually on screen — keeps first paint cheap.
    var panel = $('#trace-panel');
    var hasDrawn = false;
    var renderOnceVisible = renderTrace;
    renderTrace = function (trace, animate) {
        hasDrawn = true;
        renderOnceVisible(trace, animate);
    };
    if (panel && 'IntersectionObserver' in window && !REDUCED && Object.keys(TRACES).length) {
        var panelObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    if (!hasDrawn) renderTrace(TRACES[current], true);
                    panelObserver.disconnect();
                }
            });
        }, { threshold: 0.25 });
        panelObserver.observe(panel);
        setTimeout(function () { if (!hasDrawn && stage) renderTrace(TRACES[current], false); }, 2500);
    } else if (stage && Object.keys(TRACES).length) {
        renderTrace(TRACES[current], false);
    }

    /* ── Modality strip: real sparklines from the same datasets ────────── */

    var strip = $('#mod-strip');
    if (strip) {
        ORDER.forEach(function (key) {
            var trace = TRACES[key];
            if (!trace) return;
            var card = document.createElement('button');
            card.type = 'button';
            card.className = 'mod-card';
            card.setAttribute('data-key', key);

            var sparkPts = trace.points.filter(function (_, i) { return i % 4 === 0; });
            var d = sparkPts.map(function (p, i) {
                var x = 3 + (trace.xReversed ? 1 - p[0] : p[0]) * 194;
                var y = 3 + p[1] * 36;
                return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1);
            }).join('');

            card.innerHTML =
                '<div class="mod-card-top"><h3>' + trace.title + '</h3><span class="mod-key">view trace →</span></div>' +
                '<p class="mod-full">' + trace.full + '</p>' +
                '<svg class="mod-spark" viewBox="0 0 200 42" preserveAspectRatio="none" aria-hidden="true">' +
                '<path d="' + d + '"/></svg>' +
                '<p class="mod-scope">' + (MODALITY_SCOPE[key] || '') + '</p>';
            card.addEventListener('click', function () {
                selectModality(key, true);
                scrollToEl($('.hero'));
            });
            strip.appendChild(card);
        });
        var note = document.createElement('p');
        note.className = 'mod-sel-note';
        note.textContent = '→ click a technique to load its sample trace';
        strip.insertAdjacentElement('afterend', note);
    }

    /* ── Hero parallax (pointer + scroll), transform-only ─────────────── */

    var hero = $('.hero');
    var visual = $('.hero-visual');
    var lattice = $('.hero-deco');
    if (hero && !REDUCED && window.matchMedia && window.matchMedia('(pointer: fine)').matches) {
        var targetX = 0, targetY = 0, curX = 0, curY = 0, ticking = false;
        function tick() {
            curX += (targetX - curX) * 0.08;
            curY += (targetY - curY) * 0.08;
            if (visual) visual.style.transform =
                'perspective(1200px) rotateX(' + (-curY * 2.2).toFixed(3) + 'deg) rotateY(' + (curX * 2.6).toFixed(3) + 'deg)';
            if (lattice) lattice.style.transform = 'translate(' + (curX * 8).toFixed(2) + 'px,' + (curY * 6 + Math.min(window.scrollY, 700) * 0.05).toFixed(2) + 'px)';
            if (Math.abs(targetX - curX) > 0.002 || Math.abs(targetY - curY) > 0.002) {
                requestAnimationFrame(tick);
            } else {
                ticking = false;
            }
        }
        function kick() {
            if (!ticking) { ticking = true; requestAnimationFrame(tick); }
        }
        hero.addEventListener('pointermove', function (e) {
            var rect = hero.getBoundingClientRect();
            targetX = (e.clientX - rect.left) / rect.width - 0.5;
            targetY = (e.clientY - rect.top) / rect.height - 0.5;
            kick();
        });
        hero.addEventListener('pointerleave', function () {
            targetX = 0; targetY = 0; kick();
        });
        window.addEventListener('scroll', rAFThrottle(kick), { passive: true });
    }

    /* ── Waitlist CTA: scroll + focus the email field ──────────────────── */

    Array.prototype.forEach.call(document.querySelectorAll('[data-focus-email]'), function (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            setSheet(false);
            scrollToEl($('#waitlist'));
            var email = $('#waitlist-email');
            if (email) {
                setTimeout(function () { email.focus({ preventScroll: true }); }, REDUCED ? 30 : 520);
            }
        });
    });

    /* ── Waitlist form ─────────────────────────────────────────────────── */

    var form = $('#waitlist-form');
    if (form) {
        var emailInput = $('#waitlist-email');
        var statusEl = $('#form-status');
        var submitBtn = $('#waitlist-submit');
        var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

        function setStatus(message) {
            statusEl.textContent = message || '';
        }

        function fieldError(show) {
            var field = emailInput.closest('.field');
            field.classList.toggle('has-error', !!show);
            emailInput.setAttribute('aria-invalid', show ? 'true' : 'false');
        }

        emailInput.addEventListener('input', function () {
            fieldError(false);
            setStatus('');
        });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (submitBtn.disabled) return;
            var email = (emailInput.value || '').trim();
            if (!EMAIL_RE.test(email) || email.length > 254) {
                fieldError(true);
                setStatus('Please enter a valid email address.');
                emailInput.focus();
                return;
            }
            fieldError(false);
            setStatus('');
            var role = $('#waitlist-role') ? $('#waitlist-role').value : '';
            var honeypot = form.elements.namedItem('company');
            submitBtn.disabled = true;
            submitBtn.classList.add('loading');
            submitBtn.setAttribute('aria-busy', 'true');
            setStatus('');

            var body = JSON.stringify({
                email: email,
                role: role,
                company: honeypot ? honeypot.value : ''
            });

            fetch('/api/waitlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: body
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { ok: res.ok, status: res.status, data: data };
                });
            }).then(function (result) {
                if (result.ok) {
                    showSuccess(email, result.data && result.data.status === 'already');
                } else if (result.status === 422) {
                    var detail = (result.data && result.data.detail) || 'Please enter a valid email address.';
                    fieldError(true);
                    setStatus(typeof detail === 'string' ? detail : 'Please enter a valid email address.');
                    emailInput.focus();
                } else if (result.status === 429 || result.status === 503) {
                    setStatus((result.data && typeof result.data.detail === 'string') ? result.data.detail : 'The service is busy — please try again in a minute.');
                } else {
                    setStatus('Something went wrong on our side — please try again.');
                }
            }).catch(function () {
                setStatus("Couldn't reach the waitlist service — check your connection and try again.");
            }).finally(function () {
                submitBtn.disabled = false;
                submitBtn.classList.remove('loading');
                submitBtn.removeAttribute('aria-busy');
            });
        });

        function showSuccess(email, duplicate) {
            var success = $('#waitlist-success');
            var host = form.parentNode;
            form.hidden = true;
            success.hidden = false;
            var emailEl = $('#success-email');
            if (emailEl) emailEl.textContent = email;
            var title = $('#success-title');
            if (title) title.textContent = duplicate ? 'You\u2019re already on the list.' : 'You\u2019re on the list.';
            var detail = $('#success-detail');
            if (detail) detail.textContent = duplicate
                ? 'status · already recorded — nothing changed'
                : 'status · saved to waitlist';
            if (host) {
                host.querySelectorAll('.success-check circle, .success-check path').forEach(function (n) {
                    // restart the draw animation
                    n.style.animation = 'none';
                    void n.getBoundingClientRect();
                    n.style.animation = '';
                });
            }
            if (title) title.focus();
        }
    }

    /* ── Footer year ───────────────────────────────────────────────────── */

    var year = $('#year');
    if (year) year.textContent = String(new Date().getFullYear());
})();

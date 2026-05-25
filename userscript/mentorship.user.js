// ==UserScript==
// @name         osu! Mentorship Feedback
// @namespace    https://mentorship.yourdomain.com
// @version      1.0.0
// @description  Adds mentorship feedback panels to osu! beatmap discussion posts
// @author       you
// @match        https://osu.ppy.sh/beatmapsets/*/discussion*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @connect      mentorship.yourdomain.com
// @updateURL    https://mentorship.yourdomain.com/install
// @downloadURL  https://mentorship.yourdomain.com/install
// ==/UserScript==

(function () {
    'use strict';

    const API          = 'https://mentorship.yourdomain.com';
    const INJECTED     = 'data-ms-injected';

    // ── Auth ──────────────────────────────────────────────────────────────────

    const getToken  = ()  => GM_getValue('jwt_token', null);
    const setToken  = (t) => GM_setValue('jwt_token', t);
    const clearToken = () => GM_deleteValue('jwt_token');

    function openLoginPopup() {
        const popup = window.open(
            `${API}/auth/userscript-login`,
            'osu-mentorship-auth',
            'width=520,height=680,left=400,top=80'
        );
        if (!popup) {
            alert('Allow popups for osu.ppy.sh to log in to the mentorship tool.');
        }
    }

    window.addEventListener('message', (event) => {
        if (event.origin !== API) return;
        if (event.data?.type === 'osu-mentorship-auth' && event.data.token) {
            setToken(event.data.token);
            myMentorships = [];
            init();
        }
    });

    // ── API ───────────────────────────────────────────────────────────────────

    async function api(path, options = {}) {
        const token = getToken();
        const res = await fetch(`${API}${path}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...(options.headers || {}),
            },
        });
        if (res.status === 401) { clearToken(); return null; }
        if (!res.ok) throw new Error(`API ${res.status} on ${path}`);
        return res.json();
    }

    // ── State ─────────────────────────────────────────────────────────────────

    let myMentorships = [];   // [{id, name, my_role}]

    function getBeatmapsetId() {
        const m = location.pathname.match(/\/beatmapsets\/(\d+)/);
        return m ? parseInt(m[1]) : null;
    }

    // osu! new web stores the discussion post id in the element id or nearby anchors.
    // These selectors target the current osu-web React output — verify against live DOM
    // if something breaks after an osu! site update.
    function getPostId(el) {
        if (el.dataset.id)      return parseInt(el.dataset.id);
        if (el.dataset.postId)  return parseInt(el.dataset.postId);
        const m = el.id?.match(/(\d{6,})$/);
        if (m) return parseInt(m[1]);
        const a = el.querySelector('a[href*="/discussion#"]');
        if (a) { const lm = a.href.match(/#(\d+)$/); if (lm) return parseInt(lm[1]); }
        return null;
    }

    // ── Styles ────────────────────────────────────────────────────────────────

    function injectStyles() {
        if (document.getElementById('ms-styles')) return;
        const s = document.createElement('style');
        s.id = 'ms-styles';
        s.textContent = `
        .ms-panel{margin-top:10px;border-top:1px solid rgba(255,255,255,.08);padding-top:8px;font-size:12px}
        .ms-header{display:flex;align-items:center;gap:8px;cursor:pointer;color:rgba(255,255,255,.5);user-select:none}
        .ms-header:hover{color:rgba(255,255,255,.85)}
        .ms-header .ms-label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
        .ms-header .ms-chevron{font-size:9px;margin-left:auto}
        .ms-body{display:none;margin-top:8px}
        .ms-body.open{display:block}
        .ms-badge-discussed{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;
            background:rgba(75,210,143,.15);color:#4bd28f;border-radius:10px;font-size:10px;
            text-transform:uppercase;letter-spacing:.05em}
        .ms-btn-discussed{padding:3px 10px;background:rgba(75,210,143,.1);color:#4bd28f;
            border:1px solid rgba(75,210,143,.3);border-radius:4px;cursor:pointer;font-size:11px}
        .ms-btn-discussed:hover{background:rgba(75,210,143,.2)}
        .ms-status-pending{font-size:11px;color:rgba(255,255,255,.25)}
        .ms-notice{padding:6px 10px;background:rgba(255,200,0,.08);border:1px solid rgba(255,200,0,.2);
            border-radius:4px;color:rgba(255,200,0,.75);font-size:11px;margin-bottom:8px}
        .ms-entry{padding:6px 10px;margin-bottom:5px;background:rgba(255,255,255,.04);
            border-radius:4px;border-left:3px solid rgba(255,255,255,.1)}
        .ms-entry.role-mentor{border-color:#ff6b6b}
        .ms-entry.role-lead_mentor{border-color:#ffd93d}
        .ms-entry.role-mentee{border-color:#6bcb77}
        .ms-entry-meta{font-size:10px;color:rgba(255,255,255,.35);margin-bottom:3px}
        .ms-entry-content{color:rgba(255,255,255,.82);line-height:1.55;white-space:pre-wrap}
        .ms-empty{color:rgba(255,255,255,.28);font-style:italic;font-size:11px}
        .ms-form{display:flex;flex-direction:column;gap:6px;margin-top:8px;
            padding-top:8px;border-top:1px solid rgba(255,255,255,.06)}
        .ms-form textarea{width:100%;min-height:62px;background:rgba(0,0,0,.25);
            border:1px solid rgba(255,255,255,.12);border-radius:4px;color:#fff;
            padding:6px 8px;font-size:12px;resize:vertical;box-sizing:border-box;font-family:inherit}
        .ms-form textarea:focus{outline:none;border-color:rgba(255,255,255,.35)}
        .ms-form-row{display:flex;gap:6px;align-items:center}
        .ms-vis-label{color:rgba(255,255,255,.4);font-size:11px}
        .ms-vis-select{background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);
            border-radius:4px;color:#fff;padding:3px 6px;font-size:11px}
        .ms-submit{margin-left:auto;padding:4px 14px;background:#e8496a;color:#fff;
            border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600}
        .ms-submit:hover{background:#cf3f5e}
        .ms-submit:disabled{opacity:.45;cursor:not-allowed}
        .ms-osz-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;
            padding:6px 10px;background:rgba(255,255,255,.03);border-radius:4px}
        .ms-osz-link{color:#88c0d0;font-size:11px;text-decoration:none}
        .ms-osz-link:hover{text-decoration:underline}
        .ms-osz-none{font-size:11px;color:rgba(255,255,255,.25);font-style:italic}
        .ms-login-btn{padding:4px 12px;background:rgba(255,102,170,.12);color:#ff66aa;
            border:1px solid rgba(255,102,170,.3);border-radius:4px;cursor:pointer;font-size:12px}
        .ms-login-btn:hover{background:rgba(255,102,170,.22)}
        .ms-mentorship-select{background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.12);
            border-radius:4px;color:#fff;padding:3px 8px;font-size:11px;margin-bottom:8px;width:100%}
        `;
        document.head.appendChild(s);
    }

    // ── Panel builder ─────────────────────────────────────────────────────────

    function buildPanel(postEl, postId) {
        const beatmapsetId = getBeatmapsetId();
        const panel        = document.createElement('div');
        panel.className    = 'ms-panel';

        if (!getToken()) {
            panel.innerHTML = `<div class="ms-header">
                <span class="ms-label">🎓 Mentorship</span>
                <button class="ms-login-btn">Login with osu!</button>
            </div>`;
            panel.querySelector('.ms-login-btn').addEventListener('click', openLoginPopup);
            return panel;
        }

        if (myMentorships.length === 0) {
            panel.innerHTML = `<div class="ms-header">
                <span class="ms-label">🎓 Mentorship</span>
                <span class="ms-empty" style="margin-left:0">Not in any mentorship</span>
            </div>`;
            return panel;
        }

        // Header + collapsible body
        const header = document.createElement('div');
        header.className = 'ms-header';
        header.innerHTML = `<span class="ms-label">🎓 Mentorship Feedback</span><span class="ms-chevron">▼</span>`;

        const body = document.createElement('div');
        body.className = 'ms-body';

        header.addEventListener('click', () => {
            const open = body.classList.toggle('open');
            header.querySelector('.ms-chevron').textContent = open ? '▲' : '▼';
            if (open && !body.dataset.loaded) {
                const m = myMentorships.length === 1
                    ? myMentorships[0]
                    : null; // picker rendered inside
                loadBody(body, postId, beatmapsetId, m);
                body.dataset.loaded = '1';
            }
        });

        panel.appendChild(header);
        panel.appendChild(body);
        return panel;
    }

    async function loadBody(body, postId, beatmapsetId, mentorship) {
        body.innerHTML = '<span class="ms-empty">Loading…</span>';

        // Multiple mentorships — show a picker and re-load on change
        if (!mentorship) {
            const sel = document.createElement('select');
            sel.className = 'ms-mentorship-select';
            myMentorships.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name;
                sel.appendChild(opt);
            });
            body.innerHTML = '';
            body.appendChild(sel);
            const inner = document.createElement('div');
            body.appendChild(inner);

            const load = (id) => {
                const chosen = myMentorships.find(m => m.id === parseInt(id));
                if (chosen) loadBodyInner(inner, postId, beatmapsetId, chosen);
            };
            sel.addEventListener('change', (e) => load(e.target.value));
            load(sel.value);
            return;
        }

        loadBodyInner(body, postId, beatmapsetId, mentorship);
    }

    async function loadBodyInner(container, postId, beatmapsetId, mentorship) {
        container.innerHTML = '<span class="ms-empty">Loading…</span>';
        try {
            const [status, feedback, oszInfo] = await Promise.all([
                api(`/discussion/${postId}/status?mentorship_id=${mentorship.id}`),
                api(`/feedback/${postId}?mentorship_id=${mentorship.id}`),
                api(`/files/beatmapset/${beatmapsetId}/info?mentorship_id=${mentorship.id}`),
            ]);
            if (!status || !feedback) {
                container.innerHTML = '<span class="ms-empty">Session expired — please log in again.</span>';
                return;
            }
            renderBody(container, postId, beatmapsetId, mentorship, status, feedback, oszInfo);
        } catch (e) {
            container.innerHTML = '<span class="ms-empty">Error loading feedback.</span>';
            console.error('[mentorship]', e);
        }
    }

    function renderBody(container, postId, beatmapsetId, mentorship, status, feedback, oszInfo) {
        container.innerHTML = '';
        const isLead   = mentorship.my_role === 'lead_mentor';
        const isMentee = mentorship.my_role === 'mentee';

        // ── .osz row ──────────────────────────────────────────────────────────
        const oszRow = document.createElement('div');
        oszRow.className = 'ms-osz-row';
        if (oszInfo) {
            const sizeMb = (oszInfo.file_size_bytes / 1024 / 1024).toFixed(1);
            const href   = `${API}/files/beatmapset/${beatmapsetId}/download?mentorship_id=${mentorship.id}`;
            oszRow.innerHTML =
                `📦 <a class="ms-osz-link" href="${href}&token=${encodeURIComponent(getToken())}"
                      target="_blank" rel="noreferrer">${oszInfo.filename} (${sizeMb} MB)</a>`;
        } else {
            oszRow.innerHTML = '<span class="ms-osz-none">📦 No .osz uploaded yet — mentee: use /submit_map in Discord</span>';
        }
        container.appendChild(oszRow);

        // ── Discussed status bar ──────────────────────────────────────────────
        const statusBar = document.createElement('div');
        statusBar.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:8px;';

        if (status.is_discussed) {
            const d = new Date(status.discussed_at).toLocaleDateString();
            statusBar.innerHTML = `<span class="ms-badge-discussed">✓ Discussed ${d}</span>`;
        } else if (isLead) {
            const btn = document.createElement('button');
            btn.className   = 'ms-btn-discussed';
            btn.textContent = 'Mark as Discussed';
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = 'Saving…';
                try {
                    await api(`/discussion/${postId}/discussed?mentorship_id=${mentorship.id}`, { method: 'PATCH' });
                    status.is_discussed = true;
                    renderBody(container, postId, beatmapsetId, mentorship, status, feedback, oszInfo);
                } catch {
                    btn.disabled = false;
                    btn.textContent = 'Mark as Discussed';
                }
            });
            statusBar.appendChild(btn);
        } else {
            statusBar.innerHTML = '<span class="ms-status-pending">⏳ Pending discussion</span>';
        }
        container.appendChild(statusBar);

        // ── Limited visibility notice ─────────────────────────────────────────
        if (isMentee && !status.is_discussed) {
            const n = document.createElement('div');
            n.className   = 'ms-notice';
            n.textContent = 'Mentor feedback is hidden until a lead mentor marks this map as discussed.';
            container.appendChild(n);
        }

        // ── Feedback list ─────────────────────────────────────────────────────
        if (feedback.length === 0) {
            const e = document.createElement('div');
            e.className   = 'ms-empty';
            e.textContent = 'No feedback yet.';
            container.appendChild(e);
        } else {
            feedback.forEach(entry => {
                const item = document.createElement('div');
                item.className = `ms-entry role-${entry.author_role}`;
                const role = entry.author_role.replace('_', ' ');
                const date = new Date(entry.created_at).toLocaleDateString();
                const visTag = entry.visibility === 'immediate' ? ' · visible immediately' : '';
                item.innerHTML = `
                    <div class="ms-entry-meta">${role} · ${date}${visTag}</div>
                    <div class="ms-entry-content">${escHtml(entry.content)}</div>`;
                container.appendChild(item);
            });
        }

        // ── Submit form ───────────────────────────────────────────────────────
        const form     = document.createElement('div');
        form.className = 'ms-form';

        const ta = document.createElement('textarea');
        ta.placeholder = 'Write feedback on this mod post…';
        form.appendChild(ta);

        const row = document.createElement('div');
        row.className = 'ms-form-row';

        if (isMentee) {
            row.innerHTML = `
                <span class="ms-vis-label">Visible:</span>
                <select class="ms-vis-select">
                    <option value="after_discussed">After discussed</option>
                    <option value="immediate">Immediately</option>
                </select>`;
        }

        const submit = document.createElement('button');
        submit.className   = 'ms-submit';
        submit.textContent = 'Submit';
        row.appendChild(submit);
        form.appendChild(row);

        submit.addEventListener('click', async () => {
            const content = ta.value.trim();
            if (!content) return;
            submit.disabled = true;
            submit.textContent = 'Submitting…';
            const visibility = row.querySelector('.ms-vis-select')?.value ?? 'after_discussed';
            try {
                const entry = await api(`/feedback/${postId}`, {
                    method: 'POST',
                    body: JSON.stringify({
                        mentorship_id: mentorship.id,
                        beatmapset_id: beatmapsetId,
                        content,
                        visibility,
                    }),
                });
                if (entry) {
                    feedback.push(entry);
                    ta.value = '';
                    renderBody(container, postId, beatmapsetId, mentorship, status, feedback, oszInfo);
                    return;
                }
            } catch (e) {
                console.error('[mentorship] submit', e);
            }
            submit.disabled = false;
            submit.textContent = 'Submit';
        });

        container.appendChild(form);
    }

    function escHtml(s) {
        return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // ── DOM scanning ──────────────────────────────────────────────────────────

    function processPost(el) {
        if (el.getAttribute(INJECTED)) return;
        el.setAttribute(INJECTED, '1');
        const postId = getPostId(el);
        if (!postId) return;

        const panel = buildPanel(el, postId);

        // Try to inject after the message body; fall back to appending to the post
        const target = el.querySelector('.beatmap-discussion-post__message') || el;
        if (target.insertAdjacentElement) {
            target.insertAdjacentElement('afterend', panel);
        } else {
            el.appendChild(panel);
        }
    }

    function scan() {
        if (!location.pathname.match(/\/beatmapsets\/\d+\/discussion/)) return;
        document.querySelectorAll(
            '.beatmap-discussion-post, [class*="beatmap-discussion-post"]'
        ).forEach(processPost);
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    async function init() {
        const token = getToken();
        if (token) {
            try {
                const data = await api('/mentorship/mine');
                myMentorships = data || [];
            } catch {
                myMentorships = [];
            }
        }
        scan();
    }

    // MutationObserver for dynamically rendered posts (osu! is a React SPA)
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });

    // Also re-init on SPA navigation (title element changes when route changes)
    let lastPath = location.pathname;
    new MutationObserver(() => {
        if (location.pathname !== lastPath) {
            lastPath = location.pathname;
            if (location.pathname.match(/\/beatmapsets\/\d+\/discussion/)) {
                myMentorships = [];
                setTimeout(init, 600); // give React time to render the page
            }
        }
    }).observe(document.querySelector('title') || document.head, {
        subtree: true, childList: true, characterData: true,
    });

    injectStyles();
    init();
})();

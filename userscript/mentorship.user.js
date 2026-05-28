// ==UserScript==
// @name         osu! Mentorship Helper
// @namespace    https://mentorship.actiol.dev
// @version      2.1.0
// @description  Mentorship feedback panels on osu! beatmap discussions — with offline fallback
// @author       Actiol
// @match        https://osu.ppy.sh/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @connect      mentorship.actiol.dev
// @updateURL    https://mentorship.actiol.dev/mentorship.user.js
// @downloadURL  https://mentorship.actiol.dev/mentorship.user.js
// ==/UserScript==

(function () {
    'use strict';

    const API    = 'https://mentorship.actiol.dev';
    const ATTR   = 'data-ms-injected';
    const TOP_ID = 'ms-top-panel';

    // ═════════════════════════════════════════════════════════════════════════
    // STORAGE
    // ═════════════════════════════════════════════════════════════════════════

    const getToken   = ()  => GM_getValue('ms_jwt', null);
    const setToken   = (t) => GM_setValue('ms_jwt', t);
    const clearToken = ()  => GM_deleteValue('ms_jwt');

    function getPending() {
        try { return JSON.parse(GM_getValue('ms_pending', '[]')); } catch { return []; }
    }
    function savePending(arr) { GM_setValue('ms_pending', JSON.stringify(arr)); }
    function addPending(entry) {
        const list = getPending();
        entry.localId = `${Date.now()}-${Math.random().toString(36).slice(2,7)}`;
        list.push(entry);
        savePending(list);
        _refreshPendingBadge();
    }
    function removePending(localId) {
        savePending(getPending().filter(e => e.localId !== localId));
        _refreshPendingBadge();
    }

    // Panel position: '1' = between header and discussions, '2' = after new-discussion form
    const getPanelPos  = ()  => GM_getValue('ms_panel_pos', '1');
    const setPanelPos  = (v) => GM_setValue('ms_panel_pos', v);
    const getGlobalMode = () => GM_getValue('ms_global', false);
    const setGlobalMode = (v) => GM_setValue('ms_global', v);

    // ═════════════════════════════════════════════════════════════════════════
    // JWT
    // ═════════════════════════════════════════════════════════════════════════

    function jwtPayload(token) {
        try {
            const b64 = token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
            return JSON.parse(atob(b64));
        } catch { return null; }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // STATE
    // ═════════════════════════════════════════════════════════════════════════

    let myMentorships      = [];
    let membershipsMembers = {};
    let menteeSet          = new Set();
    let initialized        = false;
    let myOsuId            = null;
    let globalMode         = getGlobalMode();

    // ═════════════════════════════════════════════════════════════════════════
    // API
    // ═════════════════════════════════════════════════════════════════════════

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
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }
    async function safeApi(path, opts={}) { try { return await api(path, opts); } catch { return null; } }
    async function apiPost(path, body) { return api(path, { method:'POST', body: JSON.stringify(body) }); }
    async function apiPatch(path, body) { return safeApi(path, { method:'PATCH', body: JSON.stringify(body) }); }

    // ═════════════════════════════════════════════════════════════════════════
    // PAGE UTILS
    // ═════════════════════════════════════════════════════════════════════════

    const getBsid    = () => { const m = location.pathname.match(/\/beatmapsets\/(\d+)/); return m ? parseInt(m[1]) : null; };
    const isDiscPage = () => /\/beatmapsets\/\d+\/discussion/.test(location.pathname);
    const esc        = s  => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const avatarUrl  = id => `https://a.ppy.sh/${id}`;
    const roleLabel  = r  => ({ lead_mentor:'Lead Mentor', mentor:'Mentor', mentee:'Mentee' }[r] || r);

    // Get the osu! discussion ID (data-id on beatmap-discussion__discussion)
    // and the post author ID (data-user-id in the top-user card).
    // These are extracted from the OUTER .beatmap-discussion container.
    function getDiscussionInfo(el) {
        const inner = el.querySelector('.beatmap-discussion__discussion[data-id]');
        if (!inner) return null;
        const postId = parseInt(inner.dataset.id);
        if (!postId || isNaN(postId)) return null;

        // Author is in beatmap-discussion__top-user, NOT inside the replies
        const authorLink = el.querySelector('.beatmap-discussion__top-user a[data-user-id]');
        if (!authorLink) return null;
        const authorId = parseInt(authorLink.dataset.userId);
        if (!authorId || isNaN(authorId)) return null;

        return { postId, authorId, inner };
    }

    // ═════════════════════════════════════════════════════════════════════════
    // INIT
    // ═════════════════════════════════════════════════════════════════════════

    async function init() {
        initialized = false;
        document.getElementById(TOP_ID)?.remove();
        document.querySelectorAll(`[${ATTR}]`).forEach(el => {
            el.querySelectorAll('.ms-panel').forEach(p => p.remove());
            el.removeAttribute(ATTR);
        });

        if (!isDiscPage()) return;

        const token = getToken();
        if (token) {
            const p = jwtPayload(token);
            myOsuId = p ? parseInt(p.sub) : null;
            const ms = await safeApi('/mentorship/mine');
            myMentorships = ms || [];
            membershipsMembers = {};
            menteeSet = new Set();
            await Promise.all(myMentorships.map(async m => {
                const members = await safeApi(`/mentorship/${m.id}/members`);
                membershipsMembers[m.id] = members || [];
                (members||[]).forEach(mem => { if (mem.role==='mentee') menteeSet.add(mem.osu_user_id); });
            }));
        }

        globalMode = getGlobalMode();
        initialized = true;
        injectTopPanel();
        scan();
        if (getPending().length && getToken()) syncPending();
    }

    // ═════════════════════════════════════════════════════════════════════════
    // TOP PANEL
    // ═════════════════════════════════════════════════════════════════════════

    function injectTopPanel() {
        if (!isDiscPage()) return;
        document.getElementById(TOP_ID)?.remove();
        const panel = document.createElement('div');
        panel.id = TOP_ID;

        // ── Controls row (always shown): position + global toggle ─────────────
        const ctrlRow = `
            <div class="ms-top-ctrl-row">
                <button class="ms-link-btn ms-pos-btn" title="Toggle panel position">📌 Move</button>
                <label class="ms-form-label ms-global-wrap">
                    <input type="checkbox" class="ms-global-chk" ${globalMode ? 'checked' : ''}/>
                    Global mode <span class="ms-muted">(show on all mods)</span>
                </label>
                ${_pendingHtml()}
            </div>`;

        if (!getToken()) {
            panel.innerHTML = `<div class="ms-card ms-top-card">
                <div class="ms-top-row">
                    <span class="ms-section-label">🎓 Mentorship</span>
                    <button class="ms-btn ms-btn-primary" id="ms-login-btn">Login with osu!</button>
                </div>${ctrlRow}</div>`;
            panel.querySelector('#ms-login-btn').addEventListener('click', openLoginPopup);
            _bindTopCtrls(panel);
            return _insertTop(panel);
        }

        if (!myMentorships.length) {
            panel.innerHTML = `<div class="ms-card ms-top-card">
                <div class="ms-top-row">
                    <span class="ms-section-label">🎓 Mentorship</span>
                    <span class="ms-muted">Not a member of any mentorship</span>
                </div>${ctrlRow}</div>`;
            _bindTopCtrls(panel);
            return _insertTop(panel);
        }

        panel.innerHTML = `<div class="ms-card ms-top-card">
            <div class="ms-top-row">
                <span class="ms-section-label">🎓 Mentorship</span>
                ${myMentorships.length > 1
                    ? `<select class="ms-select ms-m-pick">${myMentorships.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select>`
                    : `<strong class="ms-m-name">${esc(myMentorships[0].name)}</strong>`}
            </div>
            ${ctrlRow}
            <div class="ms-top-body"></div>
        </div>`;

        const sel    = panel.querySelector('.ms-m-pick');
        const getMid = () => sel ? parseInt(sel.value) : myMentorships[0].id;

        async function renderTop(mid) {
            const body = panel.querySelector('.ms-top-body');
            body.innerHTML = '<span class="ms-muted">Loading…</span>';
            const bsid = getBsid();
            const role = myMentorships.find(m => m.id===mid)?.my_role;
            const [fileInfo, session] = await Promise.all([
                safeApi(`/files/beatmapset/${bsid}/info?mentorship_id=${mid}`),
                safeApi(`/beatmapset/${bsid}/session?mentorship_id=${mid}`),
            ]);
            body.innerHTML = '';

            // ── OSZ row ───────────────────────────────────────────────────────
            const oszRow = document.createElement('div');
            oszRow.className = 'ms-osz-row';
            if (fileInfo) {
                const mb = (fileInfo.file_size_bytes/1024/1024).toFixed(1);
                const dt = new Date(fileInfo.uploaded_at).toLocaleDateString();
                oszRow.innerHTML = `<span>📦</span>
                    <button class="ms-link-btn ms-dl-btn"
                        data-mid="${mid}" data-bsid="${bsid}" data-fn="${esc(fileInfo.filename)}">
                        ${esc(fileInfo.filename)} <span class="ms-muted">${mb} MB · submitted ${dt}</span>
                    </button>`;
                oszRow.querySelector('.ms-dl-btn').addEventListener('click', async e => {
                    const b=e.currentTarget, orig=b.innerHTML;
                    b.textContent='Downloading…';
                    await downloadOsz(+b.dataset.bsid, +b.dataset.mid, b.dataset.fn);
                    b.innerHTML=orig;
                });
            } else if (role === 'mentee') {
                oszRow.innerHTML = `<span>📦</span>
                    <span class="ms-muted">No .osz submitted yet</span>
                    <input class="ms-input ms-url-in" placeholder="Paste download URL (catbox.moe etc.)…"/>
                    <button class="ms-btn ms-btn-primary ms-url-go">Submit URL</button>
                    <span class="ms-muted ms-alt-note">or use <code>/submit_map</code> in Discord to attach a file directly</span>`;
                oszRow.querySelector('.ms-url-go').addEventListener('click', async e => {
                    const inp=oszRow.querySelector('.ms-url-in'), url=inp.value.trim();
                    if (!url) return;
                    const btn=e.currentTarget;
                    btn.disabled=true; btn.textContent='Uploading…';
                    const fd=new FormData();
                    fd.append('mentorship_id',mid); fd.append('beatmapset_id',bsid); fd.append('url',url);
                    try {
                        const r=await fetch(`${API}/files/beatmapset/from-url`,{
                            method:'POST',
                            headers: getToken()?{Authorization:`Bearer ${getToken()}`}:{},
                            body:fd,
                        });
                        if (r.ok) return renderTop(mid);
                        btn.textContent=`Failed (${r.status}) — retry`;
                    } catch { btn.textContent='Network error — retry'; }
                    btn.disabled=false;
                });
            } else {
                oszRow.innerHTML=`<span>📦</span><span class="ms-muted">No .osz uploaded yet</span>`;
            }
            body.appendChild(oszRow);

            // ── Session row ───────────────────────────────────────────────────
            let menteeId = session?.mentee_osu_id ?? null;
            if (!menteeId && role!=='mentee') {
                const mentees=(membershipsMembers[mid]||[]).filter(m=>m.role==='mentee');
                if (mentees.length===1) menteeId=mentees[0].osu_user_id;
            }
            if (role==='mentee') menteeId=myOsuId;

            const sessRow=document.createElement('div');
            sessRow.className='ms-sess-row';

            function renderSess(isRev,revAt) {
                sessRow.innerHTML='';
                if (isRev) {
                    const d=revAt?new Date(revAt).toLocaleDateString():'?';
                    const badge=document.createElement('span');
                    badge.className='ms-badge-reviewed';
                    badge.textContent=`✓ Reviewed ${d}`;
                    sessRow.appendChild(badge);
                    if (role==='lead_mentor'&&menteeId) {
                        sessRow.appendChild(_btn('Undo','ms-btn ms-btn-ghost ms-btn-sm', async b=>{
                            b.disabled=true;
                            const r=await apiPatch(`/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeId}`,{is_discussed:false});
                            if(r){renderSess(false,null);_broadcastSession(mid,false);}else b.disabled=false;
                        }));
                    }
                } else {
                    if (role==='mentee') {
                        sessRow.innerHTML=`<span class="ms-muted">⏳ Pending review — mentor feedback is hidden until reviewed</span>`;
                    } else if (role==='lead_mentor'&&menteeId) {
                        if (session?.mentee_username)
                            sessRow.innerHTML=`<span class="ms-muted">Mentee: <strong>${esc(session.mentee_username)}</strong></span> `;
                        sessRow.appendChild(_btn('✓ Mark as Reviewed','ms-btn ms-btn-primary ms-btn-sm', async b=>{
                            b.disabled=true; b.textContent='Saving…';
                            const r=await apiPatch(`/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeId}`,{is_discussed:true});
                            if(r){renderSess(true,new Date().toISOString());_broadcastSession(mid,true);}
                            else{b.disabled=false;b.textContent='✓ Mark as Reviewed';}
                        }));
                    } else {
                        sessRow.innerHTML=`<span class="ms-muted">⏳ Not yet reviewed</span>`;
                    }
                }
            }
            renderSess(session?.is_discussed??false, session?.discussed_at);
            body.appendChild(sessRow);
        }

        if (sel) sel.addEventListener('change', ()=>renderTop(getMid()));
        _bindTopCtrls(panel);
        renderTop(getMid());
        _insertTop(panel);
    }

    // ── Top panel position ────────────────────────────────────────────────────
    // pos '1': between beatmap-discussions-header-bottom and the discussions page
    // pos '2': after the beatmap-discussion-new-float (New Discussion form)

    function _insertTop(panel) {
        const pos = getPanelPos();
        let ref = null;
        if (pos === '2') {
            ref = document.querySelector('.beatmap-discussion-new-float');
            if (ref) { ref.insertAdjacentElement('afterend', panel); return; }
        }
        // Default / pos '1': after the osu-page--small that holds the header-bottom
        const headerBottom = document.querySelector('.beatmap-discussions-header-bottom');
        ref = headerBottom?.closest('.osu-page');
        if (ref) { ref.insertAdjacentElement('afterend', panel); return; }
        // Fallback
        const discussions = document.querySelector('.beatmap-discussions');
        if (discussions) { discussions.insertAdjacentElement('beforebegin', panel); return; }
        document.body.insertBefore(panel, document.body.firstChild);
    }

    function _bindTopCtrls(root) {
        // Position toggle
        root.querySelector('.ms-pos-btn')?.addEventListener('click', () => {
            const next = getPanelPos()==='1' ? '2' : '1';
            setPanelPos(next);
            injectTopPanel();   // re-inject at new position
        });
        // Global mode toggle
        const chk = root.querySelector('.ms-global-chk');
        if (chk) {
            chk.addEventListener('change', () => {
                globalMode = chk.checked;
                setGlobalMode(globalMode);
                // Re-run scan with new mode
                document.querySelectorAll(`[${ATTR}]`).forEach(el => {
                    el.querySelectorAll('.ms-panel').forEach(p => p.remove());
                    el.removeAttribute(ATTR);
                });
                scan();
            });
        }
        _bindPending(root);
    }

    function _broadcastSession(mid, isRev) {
        document.querySelectorAll(`.ms-panel[data-mid="${mid}"]`).forEach(p =>
            p.dispatchEvent(new CustomEvent('ms:session',{detail:{is_discussed:isRev}}))
        );
    }

    // ═════════════════════════════════════════════════════════════════════════
    // OFFLINE / PENDING
    // ═════════════════════════════════════════════════════════════════════════

    function _pendingHtml() {
        const n=getPending().length;
        if (!n) return '';
        return `<span class="ms-pending-badge" id="ms-pending-badge">⚠ ${n} unsent
            <button class="ms-link-btn ms-sync-btn">Retry</button>
            <button class="ms-link-btn ms-export-btn">Export .txt</button></span>`;
    }
    function _refreshPendingBadge() {
        const badge=document.getElementById('ms-pending-badge');
        if (!badge) return;
        const n=getPending().length;
        if (!n){badge.remove();return;}
        badge.innerHTML=`⚠ ${n} unsent
            <button class="ms-link-btn ms-sync-btn">Retry</button>
            <button class="ms-link-btn ms-export-btn">Export .txt</button>`;
        _bindPending(badge.closest('#ms-top-panel')||document);
    }
    function _bindPending(root) {
        root.querySelector('.ms-sync-btn')?.addEventListener('click', syncPending);
        root.querySelector('.ms-export-btn')?.addEventListener('click', exportPending);
    }

    async function syncPending() {
        let synced=0;
        for (const e of [...getPending()]) {
            try {
                const r=await apiPost(`/feedback/${e.postId}`,{
                    mentorship_id:e.mentorshipId, beatmapset_id:e.beatmapsetId,
                    mentee_osu_id:e.menteeOsuId,  content:e.content,
                    visibility:e.visibility,       is_anonymous:e.isAnonymous,
                });
                if(r){removePending(e.localId);synced++;}
            } catch {}
        }
        if (synced) {
            document.querySelectorAll('.ms-panel-body[data-loaded]').forEach(b=>{
                b.removeAttribute('data-loaded');
                if(b.style.display!=='none') b.innerHTML='<span class="ms-muted">Refreshing…</span>';
            });
        }
    }

    function exportPending() {
        const list=getPending();
        if (!list.length){alert('No unsent feedback to export.');return;}
        const lines=['osu! Mentorship — Unsent Feedback Export',
            `Generated: ${new Date().toLocaleString()}`,`Count: ${list.length}`,'═'.repeat(60)];
        list.forEach((e,i)=>{
            lines.push('',`[${i+1}] Post #${e.postId}  •  Beatmapset #${e.beatmapsetId}`,
                `Mentorship ID : ${e.mentorshipId}`,
                `Role          : ${e.authorRole||'?'}`,
                `Visibility    : ${e.visibility==='immediate'?'Visible now':'Hold until reviewed'}`,
                `Anonymous     : ${e.isAnonymous?'Yes':'No'}`,
                `Global mode   : ${e.isGlobal?'Yes':'No'}`,
                `Date          : ${new Date(e.createdAt).toLocaleString()}`,
                '─'.repeat(40),e.content);
        });
        const url=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}));
        Object.assign(document.createElement('a'),{href:url,download:`mentorship-feedback-${Date.now()}.txt`}).click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // SCAN
    // ═════════════════════════════════════════════════════════════════════════
    // Scans .beatmap-discussion outer containers (not the inner post divs).
    // Author is extracted from .beatmap-discussion__top-user a[data-user-id].
    // Post ID is extracted from .beatmap-discussion__discussion[data-id].

    function scan() {
        if (!initialized||!isDiscPage()) return;
        const bsid=getBsid();
        if (!bsid) return;

        document.querySelectorAll(`.beatmap-discussion:not([${ATTR}])`).forEach(el => {
            const info = getDiscussionInfo(el);
            if (!info) return;
            const {postId, authorId, inner} = info;

            const isMenteePost = menteeSet.has(authorId);

            // Decide whether to show panel
            if (!globalMode && !isMenteePost) return;

            // Build mentorship list for this panel
            let relevant;
            if (isMenteePost) {
                relevant = myMentorships.filter(m =>
                    (membershipsMembers[m.id]||[]).some(mem=>mem.osu_user_id===authorId&&mem.role==='mentee')
                );
            } else {
                // Global mode, non-mentee post: show panel for all mentorships
                relevant = myMentorships;
            }
            if (!relevant.length) return;

            el.setAttribute(ATTR,'1');
            const panel = buildPanel(postId, bsid, authorId, relevant, !isMenteePost);

            // Inject before the bottom line, inside the discussion container
            const line = inner.querySelector('.beatmap-discussion__line');
            if (line) inner.insertBefore(panel, line);
            else inner.appendChild(panel);
        });
    }

    // ═════════════════════════════════════════════════════════════════════════
    // FEEDBACK PANEL
    // ═════════════════════════════════════════════════════════════════════════

    // isGlobal = true when the post author is NOT a registered mentee (global mode)
    function buildPanel(postId, bsid, menteeOsuId, mentorships, isGlobal=false) {
        const panel=document.createElement('div');
        panel.className='ms-panel';
        panel.dataset.mid=mentorships[0].id;

        const header=document.createElement('div');
        header.className='ms-panel-header';
        header.innerHTML=`<span class="ms-panel-label">🎓 Feedback${isGlobal?' <span class="ms-global-tag">global</span>':''}</span>`;

        let selEl=null;
        if (mentorships.length>1) {
            selEl=document.createElement('select');
            selEl.className='ms-select ms-select-sm';
            mentorships.forEach(m=>{const o=document.createElement('option');o.value=m.id;o.textContent=m.name;selEl.appendChild(o);});
            header.appendChild(selEl);
        }
        header.innerHTML+=`<span class="ms-chevron">▼</span>`;

        const body=document.createElement('div');
        body.className='ms-panel-body';
        body.style.display='none';

        let expanded=false, loadedMid=null;
        const getMid=()=>selEl?parseInt(selEl.value):mentorships[0].id;

        async function load(mid,force=false) {
            if(loadedMid===mid&&!force) return;
            loadedMid=mid;
            body.innerHTML='<span class="ms-muted">Loading…</span>';
            const [session, feedback]=await Promise.all([
                safeApi(`/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeOsuId}`),
                safeApi(`/feedback/${postId}?mentorship_id=${mid}&mentee_osu_id=${menteeOsuId}`),
            ]);
            body.dataset.loaded='1';
            renderBody(body, mid, postId, bsid, menteeOsuId, feedback||[], session?.is_discussed??false, isGlobal);
        }

        header.addEventListener('click', e=>{
            if(e.target===selEl) return;
            expanded=!expanded;
            body.style.display=expanded?'block':'none';
            header.querySelector('.ms-chevron').textContent=expanded?'▲':'▼';
            if(expanded) load(getMid());
        });
        if(selEl) selEl.addEventListener('change',()=>{loadedMid=null;if(expanded)load(getMid());});
        panel.addEventListener('ms:session',e=>{if(expanded&&loadedMid)load(loadedMid,true);});

        panel.appendChild(header);
        panel.appendChild(body);
        return panel;
    }

    function renderBody(container, mid, postId, bsid, menteeOsuId, entries, isReviewed, isGlobal) {
        container.innerHTML='';
        const myRole  =myMentorships.find(m=>m.id===mid)?.my_role;
        const isMentee=myRole==='mentee';
        const isMentor=myRole==='mentor'||myRole==='lead_mentor';

        const pending=getPending().filter(e=>e.postId===postId&&e.mentorshipId===mid);

        if (isMentee&&!isReviewed&&!isGlobal) {
            const n=document.createElement('div');
            n.className='ms-notice';
            n.textContent='Mentor feedback is hidden until this map is marked as reviewed.';
            container.appendChild(n);
        }

        const all=[...entries,...pending.map(e=>({
            _pending:true, localId:e.localId,
            author_osu_id:myOsuId, author_username:null,
            author_role:e.authorRole, content:e.content,
            visibility:e.visibility, is_anonymous:e.isAnonymous,
            created_at:e.createdAt,
        }))];

        if (!all.length) {
            const p=document.createElement('p');p.className='ms-empty';p.textContent='No feedback yet.';
            container.appendChild(p);
        }

        all.forEach(entry=>{
            const item=document.createElement('div');
            item.className=`ms-entry ms-role-${entry.author_role}${entry._pending?' ms-entry-pending':''}`;
            const name=entry.is_anonymous?`Anonymous ${roleLabel(entry.author_role)}`:(entry.author_username||`user#${entry.author_osu_id}`);
            const date=new Date(entry.created_at).toLocaleDateString();
            const visNote=(!isReviewed&&entry.visibility==='immediate')?' · Visible now':'';
            const avatar=(!entry.is_anonymous&&entry.author_osu_id)
                ?`<img class="ms-avatar" src="${avatarUrl(entry.author_osu_id)}" alt=""/>`
                :`<div class="ms-avatar ms-avatar-anon">?</div>`;
            item.innerHTML=`
                <div class="ms-entry-head">${avatar}
                    <div class="ms-entry-meta">
                        <span class="ms-entry-name">${esc(name)}</span>
                        <span class="ms-role-chip ms-role-chip-${entry.author_role}">${roleLabel(entry.author_role)}</span>
                        <span class="ms-muted">${date}${visNote}</span>
                        ${entry._pending?'<span class="ms-pending-tag">⏳ unsent</span>':''}
                    </div>
                </div>
                <div class="ms-entry-body">${esc(entry.content)}</div>`;
            if (entry._pending) {
                const rb=_btn('Retry','ms-link-btn',async b=>{
                    b.textContent='Retrying…';
                    try {
                        const r=await apiPost(`/feedback/${postId}`,{
                            mentorship_id:mid,beatmapset_id:bsid,mentee_osu_id:menteeOsuId,
                            content:entry.content,visibility:entry.visibility,is_anonymous:entry.is_anonymous,
                        });
                        if(r){removePending(entry.localId);entries.push(r);renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);}
                        else b.textContent='Retry';
                    } catch{b.textContent='Retry';}
                });
                item.querySelector('.ms-entry-meta').appendChild(rb);
            }
            container.appendChild(item);
        });

        // ── Form ──────────────────────────────────────────────────────────────
        const form=document.createElement('div');
        form.className='ms-form';
        const ta=document.createElement('textarea');
        ta.className='ms-textarea'; ta.placeholder='Write your feedback…';
        form.appendChild(ta);
        const row=document.createElement('div');
        row.className='ms-form-row';

        // Visibility selector:
        // - In global mode: always immediate (no session to hide behind)
        // - Not yet reviewed: show for all roles
        //   · mentors default to "Hold until reviewed"
        //   · mentees default to "Visible now"
        if (!isGlobal && !isReviewed) {
            row.innerHTML=`<label class="ms-form-label">
                <select class="ms-select ms-vis-sel">
                    ${isMentor
                        ?`<option value="after_discussed" selected>Hold until reviewed</option>
                          <option value="immediate">Visible now</option>`
                        :`<option value="immediate" selected>Visible now</option>
                          <option value="after_discussed">Hold until reviewed</option>`}
                </select></label>`;
        }

        if (isMentor) {
            row.innerHTML+=`<label class="ms-form-label">
                <input type="checkbox" class="ms-anon-chk"/> Anonymous</label>`;
        }

        const submitBtn=_btn('Post','ms-btn ms-btn-primary ms-btn-submit', async b=>{
            const content=ta.value.trim();
            if(!content) return;
            b.disabled=true; b.textContent='Posting…';
            // Global mode always sends as immediate (no review session)
            const visibility=isGlobal?'immediate':(form.querySelector('.ms-vis-sel')?.value??(isMentor?'after_discussed':'immediate'));
            const isAnon=form.querySelector('.ms-anon-chk')?.checked??false;
            const payload={mentorship_id:mid,beatmapset_id:bsid,mentee_osu_id:menteeOsuId,content,visibility,is_anonymous:isAnon};
            let result=null;
            try { result=await apiPost(`/feedback/${postId}`,payload); }
            catch {
                addPending({postId,mentorshipId:mid,beatmapsetId:bsid,menteeOsuId,content,visibility,
                    isAnonymous:isAnon,authorRole:myRole,createdAt:new Date().toISOString(),isGlobal});
                ta.value='';
                renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);
                return;
            }
            if(result){ta.value='';entries.push(result);renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);}
            else{b.disabled=false;b.textContent='Post';}
        });
        row.appendChild(submitBtn);
        form.appendChild(row);
        container.appendChild(form);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // OSZ DOWNLOAD
    // ═════════════════════════════════════════════════════════════════════════

    async function downloadOsz(bsid,mid,filename) {
        try {
            const res=await fetch(`${API}/files/beatmapset/${bsid}/download?mentorship_id=${mid}`,
                {headers:getToken()?{Authorization:`Bearer ${getToken()}`}:{}});
            if(!res.ok) throw new Error(`HTTP ${res.status}`);
            const url=URL.createObjectURL(await res.blob());
            Object.assign(document.createElement('a'),{href:url,download:filename}).click();
            setTimeout(()=>URL.revokeObjectURL(url),1500);
        } catch(e){alert('Download failed: '+e.message);}
    }

    // ═════════════════════════════════════════════════════════════════════════
    // AUTH
    // ═════════════════════════════════════════════════════════════════════════

    function openLoginPopup() {
        const p=window.open(`${API}/auth/userscript-login`,'ms-auth','width=520,height=680,left=400,top=80');
        if(!p) alert('Allow popups for osu.ppy.sh to use the mentorship tool.');
    }
    window.addEventListener('message',e=>{
        if(e.origin!==API) return;
        if(e.data?.type==='osu-mentorship-auth'&&e.data.token){setToken(e.data.token);init();}
    });

    // ═════════════════════════════════════════════════════════════════════════
    // SPA NAVIGATION
    // ═════════════════════════════════════════════════════════════════════════

    let _lastPath=location.pathname;
    function _handleNav() {
        if(location.pathname===_lastPath) return;
        _lastPath=location.pathname;
        if(isDiscPage()) setTimeout(init,800);
    }
    const _origPush=history.pushState.bind(history);
    const _origRepl=history.replaceState.bind(history);
    history.pushState    =(...a)=>{_origPush(...a);    _handleNav();};
    history.replaceState =(...a)=>{_origRepl(...a); _handleNav();};
    window.addEventListener('popstate',_handleNav);
    new MutationObserver(_handleNav).observe(
        document.querySelector('title')||document.documentElement,
        {childList:true,subtree:true,characterData:true}
    );
    new MutationObserver(()=>{if(initialized)scan();}).observe(document.body,{childList:true,subtree:true});

    // ═════════════════════════════════════════════════════════════════════════
    // UTIL
    // ═════════════════════════════════════════════════════════════════════════

    function _btn(text,cls,onClick) {
        const b=document.createElement('button');
        b.className=cls; b.textContent=text;
        b.addEventListener('click',()=>onClick(b));
        return b;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // STYLES
    // ═════════════════════════════════════════════════════════════════════════

    function injectStyles() {
        if(document.getElementById('ms-styles')) return;
        const s=document.createElement('style');
        s.id='ms-styles';
        s.textContent=`
        #ms-top-panel{margin:10px 0 14px}
        .ms-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#ddd}
        .ms-top-card{display:flex;flex-direction:column;gap:8px}
        .ms-top-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
        .ms-top-ctrl-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding-top:4px;border-top:1px solid rgba(255,255,255,.06)}
        .ms-top-body{display:flex;flex-direction:column;gap:7px}
        .ms-section-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700;color:rgba(255,255,255,.4)}
        .ms-m-name{color:rgba(255,255,255,.75);font-size:12px}
        .ms-muted{color:rgba(255,255,255,.32);font-size:11px}
        .ms-alt-note{font-size:10px}
        .ms-osz-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .ms-sess-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .ms-badge-reviewed{display:inline-flex;align-items:center;padding:2px 10px;background:rgba(75,210,143,.15);color:#4bd28f;border-radius:10px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:700}
        .ms-panel{margin-top:6px;border-top:1px solid rgba(255,255,255,.06);padding-top:6px;font-size:12px}
        .ms-panel-header{display:flex;align-items:center;gap:8px;cursor:pointer;color:rgba(255,255,255,.38);user-select:none}
        .ms-panel-header:hover{color:rgba(255,255,255,.75)}
        .ms-panel-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700}
        .ms-global-tag{font-size:9px;background:rgba(255,200,0,.2);color:#f0c040;padding:1px 5px;border-radius:4px;vertical-align:middle;margin-left:3px;letter-spacing:.03em}
        .ms-chevron{margin-left:auto;font-size:9px;pointer-events:none}
        .ms-panel-body{margin-top:8px}
        .ms-entry{padding:7px 9px;margin-bottom:5px;background:rgba(255,255,255,.04);border-radius:4px;border-left:3px solid rgba(255,255,255,.1)}
        .ms-role-lead_mentor{border-color:#ffd93d}.ms-role-mentor{border-color:#ff6b6b}.ms-role-mentee{border-color:#6bcb77}
        .ms-entry-pending{opacity:.7;border-style:dashed}
        .ms-entry-head{display:flex;align-items:center;gap:7px;margin-bottom:5px}
        .ms-avatar{width:22px;height:22px;border-radius:50%;flex-shrink:0;object-fit:cover;background:rgba(255,255,255,.1)}
        .ms-avatar-anon{display:inline-flex;align-items:center;justify-content:center;font-size:12px;color:rgba(255,255,255,.3);border:1px solid rgba(255,255,255,.1)}
        .ms-entry-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
        .ms-entry-name{font-weight:600;color:rgba(255,255,255,.82)}
        .ms-role-chip{font-size:9px;padding:1px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.04em;font-weight:700}
        .ms-role-chip-lead_mentor{background:rgba(255,217,61,.15);color:#ffd93d}
        .ms-role-chip-mentor{background:rgba(255,107,107,.15);color:#ff6b6b}
        .ms-role-chip-mentee{background:rgba(107,203,119,.15);color:#6bcb77}
        .ms-pending-tag{color:#f0a500;font-size:10px}
        .ms-entry-body{color:rgba(255,255,255,.78);line-height:1.55;white-space:pre-wrap}
        .ms-form{border-top:1px solid rgba(255,255,255,.06);padding-top:7px;margin-top:7px;display:flex;flex-direction:column;gap:5px}
        .ms-textarea{width:100%;min-height:58px;background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.1);border-radius:4px;color:#eee;padding:5px 8px;font-size:12px;resize:vertical;box-sizing:border-box;font-family:inherit}
        .ms-textarea:focus{outline:none;border-color:rgba(255,255,255,.28)}
        .ms-form-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .ms-form-label{display:flex;align-items:center;gap:4px;color:rgba(255,255,255,.45);font-size:11px;cursor:pointer;user-select:none}
        .ms-global-wrap{color:rgba(255,255,255,.5)}
        .ms-btn-submit{margin-left:auto}
        .ms-btn{padding:4px 12px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600;border:1px solid transparent}
        .ms-btn-sm{padding:2px 9px;font-size:10px}
        .ms-btn-primary{background:#e8496a;color:#fff}
        .ms-btn-primary:hover{background:#cf3f5e}
        .ms-btn-primary:disabled{opacity:.4;cursor:not-allowed}
        .ms-btn-ghost{background:transparent;color:rgba(255,255,255,.4);border-color:rgba(255,255,255,.15)}
        .ms-btn-ghost:hover{color:rgba(255,255,255,.75);border-color:rgba(255,255,255,.35)}
        .ms-select{background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.1);border-radius:4px;color:#ddd;padding:3px 6px;font-size:11px}
        .ms-select-sm{font-size:10px;padding:2px 5px}
        .ms-input{background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.1);border-radius:4px;color:#eee;padding:4px 8px;font-size:11px;width:260px;max-width:100%}
        .ms-input:focus{outline:none;border-color:rgba(255,255,255,.28)}
        .ms-link-btn{background:none;border:none;color:#88c0d0;cursor:pointer;font-size:11px;padding:0;text-decoration:underline}
        .ms-link-btn:hover{color:#b0d8ec}
        .ms-notice{padding:5px 9px;background:rgba(255,200,0,.07);border:1px solid rgba(255,200,0,.2);border-radius:4px;color:rgba(255,200,0,.7);font-size:11px;margin-bottom:4px}
        .ms-empty{color:rgba(255,255,255,.28);font-style:italic;font-size:11px;margin:0}
        .ms-pending-badge{display:inline-flex;align-items:center;gap:8px;padding:2px 8px;background:rgba(240,165,0,.1);border:1px solid rgba(240,165,0,.25);border-radius:6px;color:#f0a500;font-size:11px;flex-wrap:wrap}
        `;
        document.head.appendChild(s);
    }

    injectStyles();
    init();

})();

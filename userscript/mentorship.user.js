// ==UserScript==
// @name         osu! Mentorship Helper
// @namespace    https://mentorship.actiol.dev
// @version      2.3
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

    const getToken    = ()  => GM_getValue('ms_jwt', null);
    const setToken    = (t) => GM_setValue('ms_jwt', t);
    const clearToken  = ()  => GM_deleteValue('ms_jwt');

    function getPending()      { try { return JSON.parse(GM_getValue('ms_pending','[]')); } catch { return []; } }
    function savePending(arr)  { GM_setValue('ms_pending', JSON.stringify(arr)); }
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

    // Mentorship / member cache for offline use
    function getCachedMs()      { try { return JSON.parse(GM_getValue('ms_cache_ms','[]')); }   catch { return []; } }
    function getCachedMembers() { try { return JSON.parse(GM_getValue('ms_cache_mem','{}')); }  catch { return {}; } }
    function cacheMentorships(ms, mem) {
        GM_setValue('ms_cache_ms',  JSON.stringify(ms));
        GM_setValue('ms_cache_mem', JSON.stringify(mem));
    }

    const getPanelPos   = ()  => GM_getValue('ms_panel_pos','1');
    const setPanelPos   = (v) => GM_setValue('ms_panel_pos', v);
    const getSavedGlobal = () => GM_getValue('ms_global', false);
    const setSavedGlobal = (v) => GM_setValue('ms_global', v);

    // Per-session loaded feedback cache for the export feature
    // key: `${mid}-${postId}` → array of FeedbackOut entries
    const loadedFeedback = new Map();

    // ═════════════════════════════════════════════════════════════════════════
    // JWT
    // ═════════════════════════════════════════════════════════════════════════

    function jwtPayload(t) {
        try { return JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))); }
        catch { return null; }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // STATE
    // ═════════════════════════════════════════════════════════════════════════

    let myMentorships      = [];
    let membershipsMembers = {};  // {mid: [{osu_user_id, osu_username, role}]}
    let menteeSet          = new Set();
    let initialized        = false;
    let myOsuId            = null;
    let apiOnline          = null;  // null=unknown, true, false
    let globalMode         = false; // effective current value (may be forced true when offline)

    // ═════════════════════════════════════════════════════════════════════════
    // API
    // ═════════════════════════════════════════════════════════════════════════

    async function api(path, opts = {}) {
        const token = getToken();
        const res = await fetch(`${API}${path}`, {
            ...opts,
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...(opts.headers || {}),
            },
        });
        if (res.status === 401) { clearToken(); return null; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // DELETE returns {"ok":true}, others return JSON
        const ct = res.headers.get('content-type') || '';
        return ct.includes('json') ? res.json() : { ok: true };
    }
    async function safeApi(path, opts = {}) { try { return await api(path, opts); } catch { return null; } }
    async function apiPost(path, body)  { return api(path, { method:'POST',   body: JSON.stringify(body) }); }
    async function apiPatch(path, body) { return safeApi(path, { method:'PATCH',  body: JSON.stringify(body) }); }
    async function apiDel(path)         { return safeApi(path, { method:'DELETE' }); }

    // ═════════════════════════════════════════════════════════════════════════
    // PAGE UTILS
    // ═════════════════════════════════════════════════════════════════════════

    const getBsid    = () => { const m = location.pathname.match(/\/beatmapsets\/(\d+)/); return m ? parseInt(m[1]) : null; };
    const isDiscPage = () => /\/beatmapsets\/\d+\/discussion/.test(location.pathname);
    const esc        = s  => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const avatarUrl  = id => `https://a.ppy.sh/${id}`;
    const roleLabel  = r  => ({ lead_mentor:'Lead Mentor', mentor:'Mentor', mentee:'Mentee' }[r] || r);

    function getDiscussionInfo(el) {
        const inner = el.querySelector('.beatmap-discussion__discussion[data-id]');
        if (!inner) return null;
        const postId = parseInt(inner.dataset.id);
        if (!postId || isNaN(postId)) return null;
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

            if (ms !== null) {
                // API is reachable
                apiOnline = true;
                myMentorships = ms;

                membershipsMembers = {};
                menteeSet = new Set();
                await Promise.all(myMentorships.map(async m => {
                    const members = await safeApi(`/mentorship/${m.id}/members`);
                    membershipsMembers[m.id] = members || [];
                    (members||[]).forEach(mem => { if (mem.role==='mentee') menteeSet.add(mem.osu_user_id); });
                }));
                cacheMentorships(myMentorships, membershipsMembers);

                globalMode = getSavedGlobal();
            } else {
                // API unreachable — fall back to cache
                apiOnline = false;
                myMentorships = getCachedMs();
                membershipsMembers = getCachedMembers();
                menteeSet = new Set();
                Object.values(membershipsMembers).forEach(members =>
                    (members||[]).forEach(mem => { if (mem.role==='mentee') menteeSet.add(mem.osu_user_id); })
                );
                // Force global mode when offline (can't verify mentee membership)
                globalMode = true;
            }
        }

        initialized = true;
        injectTopPanel();
        scan();
        if (getPending().length && apiOnline) syncPending();
    }

    // ═════════════════════════════════════════════════════════════════════════
    // TOP PANEL
    // ═════════════════════════════════════════════════════════════════════════

    function injectTopPanel() {
        if (!isDiscPage()) return;
        document.getElementById(TOP_ID)?.remove();
        const panel = document.createElement('div');
        panel.id = TOP_ID;

        const offlineBanner = apiOnline === false
            ? `<div class="ms-offline-banner">
                ⚠ API unreachable — offline mode active. Feedback is saved locally and will sync automatically when the connection is restored.
                <button class="ms-link-btn ms-retry-btn">Retry</button>
               </div>`
            : '';

        // Mentorship selector — hidden in global mode
        const msSelector = (!globalMode && myMentorships.length > 1)
            ? `<select class="ms-select ms-m-pick">${myMentorships.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select>`
            : (myMentorships.length === 1 ? `<strong class="ms-m-name">${esc(myMentorships[0].name)}</strong>` : '');

        const ctrlRow = `
            <div class="ms-top-ctrl-row">
                <button class="ms-link-btn ms-pos-btn" title="Cycle panel position">📌 Move</button>
                <label class="ms-form-label ms-global-wrap" title="Show feedback panel under every mod post, not just mentee posts. Hides mentorship selector and visibility options.">
                    <input type="checkbox" class="ms-global-chk" ${globalMode?'checked':''}/>
                    Global mode
                </label>
                ${_pendingHtml()}
            </div>`;

        if (!getToken()) {
            panel.innerHTML = `<div class="ms-card ms-top-card">
                ${offlineBanner}
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
                ${offlineBanner}
                <div class="ms-top-row">
                    <span class="ms-section-label">🎓 Mentorship</span>
                    <span class="ms-muted">${apiOnline===false ? 'No cached mentorship data' : 'Not a member of any mentorship'}</span>
                </div>${ctrlRow}</div>`;
            _bindTopCtrls(panel);
            return _insertTop(panel);
        }

        panel.innerHTML = `<div class="ms-card ms-top-card">
            ${offlineBanner}
            <div class="ms-top-row">
                <span class="ms-section-label">🎓 Mentorship</span>
                ${msSelector}
                <div class="ms-top-right">
                    <button class="ms-icon-btn ms-export-page-btn" title="Export (visible!) page feedback to .txt">📥 Export</button>
                </div>
            </div>
            ${ctrlRow}
            <div class="ms-top-body"></div>
        </div>`;


        panel.querySelector('.ms-export-page-btn')?.addEventListener('click', () => exportAll(getBsid()));

        const sel    = panel.querySelector('.ms-m-pick');
        const getMid = () => sel ? parseInt(sel.value) : myMentorships[0]?.id;

        async function renderTop(mid) {
            const body = panel.querySelector('.ms-top-body');
            if (!mid) { body.innerHTML=''; return; }

            // --- STEP 4 APPLIED HERE ---
            body.innerHTML = _topSkeletonHtml();

            const bsid = getBsid();
            const role = myMentorships.find(m=>m.id===mid)?.my_role;

            if (apiOnline === false) {
                body.innerHTML = `<span class="ms-muted">OSZ and session info unavailable offline.</span>`;
                return;
            }

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
                    <button class="ms-link-btn ms-dl-btn" data-mid="${mid}" data-bsid="${bsid}" data-fn="${esc(fileInfo.filename)}">
                        ${esc(fileInfo.filename)} <span class="ms-muted">${mb} MB · submitted ${dt}</span>
                    </button>`;
                oszRow.querySelector('.ms-dl-btn').addEventListener('click', async e => {
                    const b=e.currentTarget, orig=b.innerHTML;
                    b.textContent='Downloading…';
                    await downloadOsz(+b.dataset.bsid, +b.dataset.mid, b.dataset.fn);
                    b.innerHTML=orig;
                });
            } else if (role==='mentee') {
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
                            method:'POST', headers:getToken()?{Authorization:`Bearer ${getToken()}`}:{}, body:fd,
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

            // ── Session / reviewed row ────────────────────────────────────────
            let menteeId = session?.mentee_osu_id ?? null;
            if (!menteeId && role!=='mentee') {
                const mentees=(membershipsMembers[mid]||[]).filter(m=>m.role==='mentee');
                if (mentees.length===1) menteeId=mentees[0].osu_user_id;
            }
            if (role==='mentee') menteeId=myOsuId;

            const sessRow=document.createElement('div');
            sessRow.className='ms-sess-row';

            function renderSess(isRev, revAt) {
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
                            const r=await apiPatch(
                                `/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeId}`,
                                {is_discussed:false}
                            );
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
                            const r=await apiPatch(
                                `/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeId}`,
                                {is_discussed:true}
                            );
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
        if (myMentorships.length) renderTop(getMid());
        _insertTop(panel);
    }

    function _insertTop(panel) {
        const pos = getPanelPos();
        if (pos==='2') {
            const ref=document.querySelector('.beatmap-discussion-new-float');
            if (ref){ ref.insertAdjacentElement('afterend',panel); return; }
        }

        // --- MODIFIED POSITION 1 ---
        // Find the element that marks the start of the extra tabs context
        const refTab = document.querySelector('.page-extra-tabs-before');
        if (refTab) {
            // Injects the panel directly before it, inside the .osu-page block
            refTab.insertAdjacentElement('beforebegin', panel);
            return;
        }

        // Fallbacks if page structure changes or hasn't fully rendered
        const hb=document.querySelector('.beatmap-discussions-header-bottom');
        const ref=hb?.closest('.osu-page');
        if (ref){ ref.insertAdjacentElement('afterbegin',panel); return; }
        const disc=document.querySelector('.beatmap-discussions');
        if (disc){ disc.insertAdjacentElement('beforebegin',panel); return; }
        document.body.insertBefore(panel,document.body.firstChild);
    }

    function _bindTopCtrls(root) {
        root.querySelector('.ms-pos-btn')?.addEventListener('click', ()=>{
            setPanelPos(getPanelPos()==='1'?'2':'1');
            injectTopPanel();
        });
        root.querySelector('.ms-retry-btn')?.addEventListener('click', init);
        const chk=root.querySelector('.ms-global-chk');
        if (chk) {
            chk.addEventListener('change', ()=>{
                globalMode=chk.checked;
                setSavedGlobal(globalMode);
                // Re-render top panel to show/hide mentorship selector
                injectTopPanel();
                // Re-scan to add/remove per-post panels
                document.querySelectorAll(`[${ATTR}]`).forEach(el=>{
                    el.querySelectorAll('.ms-panel').forEach(p=>p.remove());
                    el.removeAttribute(ATTR);
                });
                scan();
            });
        }
        _bindPending(root);
    }

    function _broadcastSession(mid, isRev) {
        document.querySelectorAll(`.ms-panel[data-mid="${mid}"]`).forEach(p=>
            p.dispatchEvent(new CustomEvent('ms:session',{detail:{is_discussed:isRev}}))
        );
    }

    // ═════════════════════════════════════════════════════════════════════════
    // OFFLINE / PENDING / SKELETON
    // ═════════════════════════════════════════════════════════════════════════

    function _topSkeletonHtml() {
        return `
            <div class="ms-skeleton-top-body">
                <div class="ms-skeleton-top-line" style="width: 70%;"></div>
                <div class="ms-skeleton-top-line" style="width: 40%;"></div>
            </div>`;
    }

    function _skeletonHtml() {
        let html = '<div class="ms-skeleton-container" style="margin-top: 12px;">';
        // Generate 2 dummy cards to simulate loading feedback posts
        for (let i = 0; i < 2; i++) {
            html += `
                <div class="ms-skeleton-card">
                    <div class="ms-skeleton-header">
                        <div class="ms-skeleton-avatar"></div>
                        <div class="ms-skeleton-line ms-skeleton-name"></div>
                    </div>
                    <div class="ms-skeleton-line ms-skeleton-text-1"></div>
                    <div class="ms-skeleton-line ms-skeleton-text-2"></div>
                </div>`;
        }
        html += '</div>';
        return html;
    }

    function _pendingHtml() {
        const n=getPending().length;
        if (!n) return '';
        return `<span class="ms-pending-badge" id="ms-pending-badge">⚠ ${n} unsent
            <button class="ms-link-btn ms-sync-btn">Sync</button>
            <button class="ms-link-btn ms-export-btn">Export .txt</button></span>`;
    }
    function _refreshPendingBadge() {
        const badge=document.getElementById('ms-pending-badge');
        if (!badge) return;
        const n=getPending().length;
        if (!n){badge.remove();return;}
        badge.innerHTML=`⚠ ${n} unsent
            <button class="ms-link-btn ms-sync-btn">Sync</button>
            <button class="ms-link-btn ms-export-btn">Export .txt</button>`;
        _bindPending(badge.closest('#ms-top-panel')||document);
    }
    function _bindPending(root) {
        root.querySelector('.ms-sync-btn')?.addEventListener('click', syncPending);
        root.querySelector('.ms-export-btn')?.addEventListener('click', ()=>exportAll(getBsid()));
    }

    async function syncPending() {
        if (!getToken()) return;
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
            // Reload any open panels
            document.querySelectorAll('.ms-panel-body[data-loaded]').forEach(b=>{
                b.removeAttribute('data-loaded');
                if(b.style.display!=='none') b.innerHTML='<span class="ms-muted">Refreshing…</span>';
            });
        }
    }

    function exportAll(bsid) {
        const lines=[
            'osu! Mentorship — Feedback Export',
            `Beatmapset: https://osu.ppy.sh/beatmapsets/${bsid}/discussion`,
            `Generated : ${new Date().toLocaleString()}`,
            '═'.repeat(70),
        ];

        // Server-loaded feedback grouped by post
        if (loadedFeedback.size) {
            lines.push('','── Stored Feedback ──');
            for (const [key, entries] of loadedFeedback) {
                if (!entries.length) continue;
                const postId=key.split('-')[1];
                lines.push('',
                    `Post #${postId}`,
                    `Permalink: https://osu.ppy.sh/beatmapsets/${bsid}/discussion/-/generalAll#/${postId}`,
                    '─'.repeat(50)
                );
                entries.forEach(e=>{
                    const name=e.is_anonymous?`Anonymous ${roleLabel(e.author_role)}`:(e.author_username||`user#${e.author_osu_id}`);
                    lines.push(`  [${roleLabel(e.author_role)}] ${name}`);
                    lines.push(`  ${new Date(e.created_at).toLocaleString()}`);
                    lines.push(`  ${e.content}`,'');
                });
            }
        }

        // Pending offline entries
        const pending=getPending();
        if (pending.length) {
            lines.push('','── Unsent (offline) Feedback ──');
            pending.forEach((e,i)=>{
                lines.push('',
                    `[UNSENT ${i+1}] Post #${e.postId}`,
                    `Permalink: https://osu.ppy.sh/beatmapsets/${e.beatmapsetId}/discussion/-/generalAll#/${e.postId}`,
                    `Role      : ${e.authorRole||'?'}`,
                    `Visibility: ${e.visibility==='immediate'?'Visible now':'Hold until reviewed'}`,
                    `Anonymous : ${e.isAnonymous?'Yes':'No'}`,
                    `Date      : ${new Date(e.createdAt).toLocaleString()}`,
                    '─'.repeat(50),
                    `  ${e.content}`,''
                );
            });
        }

        if (lines.length<=4) { alert('No feedback to export yet — you need to expand the feedback in order to save it!'); return; }
        const url=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}));
        Object.assign(document.createElement('a'),{href:url,download:`mentorship-${bsid}-${Date.now()}.txt`}).click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // BADGE SYSTEM
    // Priority: OP > Lead Mentor > Mentor > Mentee
    // Show highest badge; hide extras behind (+n) expander with tooltips.
    // ═════════════════════════════════════════════════════════════════════════

    function getBadges(entry, menteeOsuId) {
        const badges=[];

        // OP — only when not anonymous and the feedback author IS the mod author
        if (!entry.is_anonymous && entry.author_osu_id===menteeOsuId) {
            badges.push({
                label:'OP',
                cls:'ms-badge-op',
                tip:'Original Poster — this person posted this mod themselves',
            });
        }

        // Role badge with mentorship tooltip
        const rLabel=roleLabel(entry.author_role);
        const msNames=myMentorships
            .filter(m=>(membershipsMembers[m.id]||[]).some(mem=>
                mem.osu_user_id===entry.author_osu_id && mem.role===entry.author_role
            ))
            .map(m=>m.name);
        badges.push({
            label:rLabel,
            cls:`ms-role-chip ms-role-chip-${entry.author_role}`,
            tip:msNames.length ? `${rLabel} in: ${msNames.join(', ')}` : rLabel,
        });

        // Priority ordering: OP always comes first (already prepended above).
        // Within role the existing ordering is correct.
        return badges;
    }

    function renderBadges(badges) {
        const el=document.createElement('span');
        el.className='ms-badges';
        if (!badges.length) return el;

        const primary=badges[0];
        const extras=badges.slice(1);

        const primaryEl=document.createElement('span');
        primaryEl.className=primary.cls;
        primaryEl.textContent=primary.label;
        primaryEl.title=primary.tip;
        el.appendChild(primaryEl);

        if (extras.length) {
            const more=document.createElement('span');
            more.className='ms-badge-more';

            const btn=document.createElement('span');
            btn.className='ms-badge-more-btn';
            btn.textContent=`+${extras.length}`;
            more.appendChild(btn);

            const list=document.createElement('span');
            list.className='ms-badge-more-list';
            extras.forEach(b=>{
                const s=document.createElement('span');
                s.className=b.cls;
                s.textContent=b.label;
                s.title=b.tip;
                list.appendChild(s);
            });
            more.appendChild(list);

            more.addEventListener('click', e=>{
                e.stopPropagation();
                more.classList.toggle('ms-badge-more--open');
            });
            el.appendChild(more);
        }
        return el;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // SCAN
    // ═════════════════════════════════════════════════════════════════════════

    function scan() {
        if (!initialized||!isDiscPage()) return;
        const bsid=getBsid();
        if (!bsid) return;

        document.querySelectorAll(`.beatmap-discussion:not([${ATTR}])`).forEach(el=>{
            const info=getDiscussionInfo(el);
            if (!info) return;
            const {postId,authorId,inner}=info;

            const isMenteePost=menteeSet.has(authorId);
            if (!globalMode&&!isMenteePost) return;

            let relevant;
            if (isMenteePost&&!globalMode) {
                relevant=myMentorships.filter(m=>
                    (membershipsMembers[m.id]||[]).some(mem=>mem.osu_user_id===authorId&&mem.role==='mentee')
                );
            } else {
                relevant=myMentorships;
            }
            if (!relevant.length) return;

            el.setAttribute(ATTR,'1');
            const panel=buildPanel(postId,bsid,authorId,relevant,!isMenteePost||globalMode);
            const line=inner.querySelector('.beatmap-discussion__line');
            if (line) inner.insertBefore(panel,line);
            else inner.appendChild(panel);
        });
    }

    // ═════════════════════════════════════════════════════════════════════════
    // PER-POST FEEDBACK PANEL
    // ═════════════════════════════════════════════════════════════════════════

    function buildPanel(postId,bsid,menteeOsuId,mentorships,isGlobal) {
        const panel=document.createElement('div');
        panel.className='ms-panel';
        panel.dataset.mid=mentorships[0].id;

        const header=document.createElement('div');
        header.className='ms-panel-header';
        header.innerHTML=`<span class="ms-chevron">▼</span><span class="ms-panel-label">🎓 Feedback${isGlobal?' <span class="ms-global-tag">global</span>':''}</span>`;
        // In global mode: no mentorship selector (use first mentorship silently)
        let selEl=null;
        if (!isGlobal && mentorships.length>1) {
            selEl=document.createElement('select');
            selEl.className='ms-select ms-select-sm ms-m-pick';
            mentorships.forEach(m=>{
                const o=document.createElement('option');o.value=m.id;o.textContent=m.name;selEl.appendChild(o);
            });
            header.appendChild(selEl);
        }

        const body=document.createElement('div');
        body.className='ms-panel-body';
        body.style.display='none';

        let expanded=false, loadedMid=null;
        const getMid=()=>selEl?parseInt(selEl.value):mentorships[0].id;

        async function load(mid,force=false) {
            if(loadedMid===mid&&!force) return;
            loadedMid=mid;
            body.innerHTML = _skeletonHtml();

            if (apiOnline===false) {
                // Offline: show only pending entries, no API calls
                body.dataset.loaded='1';
                renderBody(body,mid,postId,bsid,menteeOsuId,[],false,isGlobal);
                return;
            }

            const [session,feedback]=await Promise.all([
                safeApi(`/beatmapset/${bsid}/session?mentorship_id=${mid}&mentee_osu_id=${menteeOsuId}`),
                safeApi(`/feedback/${postId}?mentorship_id=${mid}&mentee_osu_id=${menteeOsuId}`),
            ]);
            body.dataset.loaded='1';
            const entries=feedback||[];
            // Cache for export
            loadedFeedback.set(`${mid}-${postId}`, entries);
            renderBody(body,mid,postId,bsid,menteeOsuId,entries,session?.is_discussed??false,isGlobal);
        }

        header.addEventListener('click', e => {
            if (e.target.closest('.ms-m-pick') || e.target.closest('select')) {
                return;
            }
            expanded = !expanded;
            body.style.display = expanded ? 'block' : 'none';
            header.querySelector('.ms-chevron').textContent = expanded ? '▲' : '▼';
            if (expanded) load(getMid());
        });

        if (selEl) {
            // Extra layer of protection: stop clicks from bubbling up from the selector
            selEl.addEventListener('click', e => e.stopPropagation());
            selEl.addEventListener('change', () => {
                loadedMid = null;
                if (expanded) load(getMid());
            });
        }
        panel.addEventListener('ms:session',e=>{if(expanded&&loadedMid)load(loadedMid,true);});

        panel.appendChild(header);
        panel.appendChild(body);
        return panel;
    }

    function renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal) {
        container.innerHTML='';
        const myRole  =myMentorships.find(m=>m.id===mid)?.my_role;
        const isMentee=myRole==='mentee';
        const isMentor=myRole==='mentor'||myRole==='lead_mentor';

        // Offline notice
        if (apiOnline===false) {
            const n=document.createElement('div');n.className='ms-offline-notice';
            n.textContent='⚠ Offline — showing locally saved entries only.';
            container.appendChild(n);
        }

        if (isMentee&&!isReviewed&&!isGlobal) {
            const n=document.createElement('div');n.className='ms-notice';
            n.textContent='Mentor feedback is hidden until this map is marked as reviewed.';
            container.appendChild(n);
        }

        // Pending entries for this post
        const pending=getPending().filter(e=>e.postId===postId&&e.mentorshipId===mid);

        const all=[
            ...entries,
            ...pending.map(e=>({
                _pending:true,localId:e.localId,
                author_osu_id:myOsuId,author_username:null,
                author_role:e.authorRole,content:e.content,
                visibility:e.visibility,is_anonymous:e.isAnonymous,
                created_at:e.createdAt,
            })),
        ];

        if (!all.length) {
            const p=document.createElement('p');p.className='ms-empty';p.textContent='No feedback yet.';
            container.appendChild(p);
        }

        all.forEach(entry=>{
            const item=document.createElement('div');
            item.className=`ms-entry ms-role-${entry.author_role}${entry._pending?' ms-entry-pending':''}`;

            const name=entry.is_anonymous
                ?`Anonymous ${roleLabel(entry.author_role)}`
                :(entry.author_username||`user#${entry.author_osu_id}`);
            const date=new Date(entry.created_at).toLocaleDateString();
            const visNote=(!isReviewed&&entry.visibility==='immediate')?' · Visible now':'';

            const avatar=(!entry.is_anonymous&&entry.author_osu_id)
                ?`<img class="ms-avatar" src="${avatarUrl(entry.author_osu_id)}" alt=""/>`
                :`<div class="ms-avatar ms-avatar-anon">?</div>`;

            const nameEl=document.createElement('span');
            nameEl.className='ms-entry-name';nameEl.textContent=name;

            const metaEl=document.createElement('div');
            metaEl.className='ms-entry-meta';
            metaEl.appendChild(nameEl);

            // Badges
            const badges=getBadges(entry,menteeOsuId);
            metaEl.appendChild(renderBadges(badges));

            // --- UPDATED TIMESTAMPS ---
            // Create a proper native time node matching osu!'s timeago script engine
            const dateEl = document.createElement('time');
            dateEl.className = 'js-timeago ms-muted';

            // 1. Get the raw date string from the server or local pending state
            const rawDate = entry.created_at || entry.createdAt;
            let dateObj = new Date(rawDate);

            // 2. HOTFIX: If the entry came from the server, correct the 2-hour offset
            if (entry.created_at) {
                const localMinutesOffset = new Date().getTimezoneOffset(); // e.g., -120 for UTC+2
                // Shift the server time forward by your exact timezone offset to fix the backend bug
                dateObj = new Date(dateObj.getTime() - (localMinutesOffset * 60000));
            }

            const isoString = dateObj.toISOString();

            dateEl.setAttribute('datetime', isoString);
            dateEl.setAttribute('title', isoString);

            // Set fallback text
            dateEl.textContent = dateObj.toLocaleDateString();
            metaEl.appendChild(dateEl);

            // Visibility note separated to avoid breaking the timeago engine text node
            if (!isReviewed && entry.visibility === 'immediate') {
                const visEl = document.createElement('span');
                visEl.className = 'ms-muted';
                visEl.textContent = ' · Visible now';
                metaEl.appendChild(visEl);
            }

            if (entry._pending) {
                const tag=document.createElement('span');tag.className='ms-pending-tag';tag.textContent='⏳ unsent';
                metaEl.appendChild(tag);
            }

            const headEl=document.createElement('div');
            headEl.className='ms-entry-head';
            headEl.innerHTML=avatar;
            headEl.appendChild(metaEl);

            const bodyEl=document.createElement('div');
            bodyEl.className='ms-entry-body';bodyEl.textContent=entry.content;

            item.appendChild(headEl);
            item.appendChild(bodyEl);

            // ── Edit / Delete for own entries ─────────────────────────────────
            // For pending entries use localId check; for server entries use author_osu_id
            const isOwn=entry._pending
                ? true  // always own (we created it)
                : (entry.author_osu_id===myOsuId);

            if (isOwn&&!entry._pending) {
                const actions=document.createElement('div');
                actions.className='ms-entry-actions';

                // Edit button
                actions.appendChild(_btn('Edit','ms-link-btn',()=>{
                    // Replace body with inline editor
                    const ta=document.createElement('textarea');
                    ta.className='ms-textarea ms-edit-ta';ta.value=entry.content;
                    bodyEl.replaceWith(ta);ta.focus();
                    actions.innerHTML='';
                    actions.appendChild(_btn('Save','ms-link-btn',async b=>{
                        const newContent=ta.value.trim();if(!newContent)return;
                        b.textContent='Saving…';
                        const r=await apiPatch(`/feedback/${entry.id}`,{content:newContent});
                        if(r){entry.content=newContent;renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);}
                        else b.textContent='Save';
                    }));
                    actions.appendChild(_btn('Cancel','ms-link-btn',()=>{
                        renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);
                    }));
                }));

                // Delete button
                actions.appendChild(_btn('Delete','ms-link-btn ms-del-btn',async b=>{
                    if(!confirm('Delete this feedback? This cannot be undone.'))return;
                    b.textContent='Deleting…';
                    const r=await apiDel(`/feedback/${entry.id}`);
                    if(r){
                        const idx=entries.findIndex(e=>e.id===entry.id);
                        if(idx!==-1)entries.splice(idx,1);
                        // Update export cache
                        loadedFeedback.set(`${mid}-${postId}`,[...entries]);
                        renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);
                    } else b.textContent='Delete';
                }));

                item.appendChild(actions);
            }

            // Pending entry retry
            if (entry._pending) {
                const actions=document.createElement('div');actions.className='ms-entry-actions';
                actions.appendChild(_btn('Retry','ms-link-btn',async b=>{
                    b.textContent='Retrying…';
                    try {
                        const r=await apiPost(`/feedback/${postId}`,{
                            mentorship_id:mid,beatmapset_id:bsid,mentee_osu_id:menteeOsuId,
                            content:entry.content,visibility:entry.visibility,is_anonymous:entry.is_anonymous,
                        });
                        if(r){removePending(entry.localId);entries.push(r);renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);}
                        else b.textContent='Retry';
                    } catch{b.textContent='Retry';}
                }));
                item.appendChild(actions);
            }

            container.appendChild(item);
        });

        // ── Feedback form ─────────────────────────────────────────────────────
        const form=document.createElement('div');form.className='ms-form';
        const ta=document.createElement('textarea');
        ta.className='ms-textarea';ta.placeholder='Write your feedback…';
        form.appendChild(ta);

        const row=document.createElement('div');row.className='ms-form-row';

        // Visibility selector:
        //   - Hidden in global mode (always immediate)
        //   - Hidden once reviewed (irrelevant)
        //   - Mentors default "Hold until reviewed"; mentees default "Visible now"
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

        // Anonymous — mentors only, and NOT in global mode
        if (isMentor && !isGlobal) {
            row.innerHTML+=`<label class="ms-form-label">
                <input type="checkbox" class="ms-anon-chk"/> Anonymous</label>`;
        }

       const submitBtn=_btn('Post','ms-btn ms-btn-primary ms-btn-submit',async b=>{
            const content=ta.value.trim();
            if(!content)return;
            b.disabled=true;b.textContent='Posting…';
            const visibility=isGlobal?'immediate':(form.querySelector('.ms-vis-sel')?.value??(isMentor?'after_discussed':'immediate'));
            const isAnon=(!isGlobal)&&(form.querySelector('.ms-anon-chk')?.checked??false);
            const payload={mentorship_id:mid,beatmapset_id:bsid,mentee_osu_id:menteeOsuId,content,visibility,is_anonymous:isAnon};

            let result=null;
            try { result=await apiPost(`/feedback/${postId}`,payload); }
            catch {
                // --- FIX: Generate ISO string with local timezone offset preserved ---
                const tzOffset = new Date().getTimezoneOffset() * 60000; // offset in milliseconds
                const localISOTime = (new Date(Date.now() - tzOffset)).toISOString().slice(0, -1);
                const sign = new Date().getTimezoneOffset() > 0 ? '-' : '+';
                const pad = (num) => String(Math.abs(num)).padStart(2, '0');
                const offsetString = `${sign}${pad(Math.floor(new Date().getTimezoneOffset() / 60))}:${pad(new Date().getTimezoneOffset() % 60)}`;
                const localizedTimestamp = `${localISOTime}${offsetString}`;

                addPending({postId,mentorshipId:mid,beatmapsetId:bsid,menteeOsuId,content,visibility,
                    isAnonymous:isAnon,authorRole:myRole,createdAt:localizedTimestamp,isGlobal});
                ta.value='';
                renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);
                return;
            }
            if(result){
                ta.value='';
                entries.push(result);
                loadedFeedback.set(`${mid}-${postId}`,[...entries]);
                renderBody(container,mid,postId,bsid,menteeOsuId,entries,isReviewed,isGlobal);
            } else{b.disabled=false;b.textContent='Post';}
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
            if(!res.ok)throw new Error(`HTTP ${res.status}`);
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
        if(!p)alert('Allow popups for osu.ppy.sh to use the mentorship tool.');
    }
    window.addEventListener('message',e=>{
        if(e.origin!==API)return;
        if(e.data?.type==='osu-mentorship-auth'&&e.data.token){setToken(e.data.token);init();}
    });

    // ═════════════════════════════════════════════════════════════════════════
    // SPA NAVIGATION
    // ═════════════════════════════════════════════════════════════════════════

    let _lastPath=location.pathname;
    function _handleNav(){
        if(location.pathname===_lastPath)return;
        _lastPath=location.pathname;
        if(isDiscPage())setTimeout(init,800);
    }
    const _origPush=history.pushState.bind(history);
    const _origRepl=history.replaceState.bind(history);
    history.pushState    =(...a)=>{_origPush(...a);   _handleNav();};
    history.replaceState =(...a)=>{_origRepl(...a); _handleNav();};
    window.addEventListener('popstate',_handleNav);
    new MutationObserver(_handleNav).observe(
        document.querySelector('title')||document.documentElement,
        {childList:true,subtree:true,characterData:true}
    );
    new MutationObserver(()=>{if(initialized)scan();})
        .observe(document.body,{childList:true,subtree:true});

    // ═════════════════════════════════════════════════════════════════════════
    // UTIL
    // ═════════════════════════════════════════════════════════════════════════

    function _btn(text,cls,onClick){
        const b=document.createElement('button');
        b.className=cls;b.textContent=text;
        b.addEventListener('click',()=>onClick(b));
        return b;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // STYLES
    // ═════════════════════════════════════════════════════════════════════════

function injectStyles(){
        if(document.getElementById('ms-styles'))return;
        const s=document.createElement('style');s.id='ms-styles';
        s.textContent=`
        #ms-top-panel{margin:10px 0 14px}
        .ms-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#ddd}
        .ms-top-card{display:flex;flex-direction:column;gap:8px}
        .ms-top-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;position:relative;width:100%}
        .ms-top-right{margin-left:auto;display:flex;align-items:center}
        .ms-top-ctrl-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding-top:5px;border-top:1px solid rgba(255,255,255,.06)}
        .ms-top-body{display:flex;flex-direction:column;gap:7px}
        .ms-section-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700;color:rgba(255,255,255,.4)}
        .ms-m-name{color:rgba(255,255,255,.75);font-size:12px}
        .ms-muted{color:rgba(255,255,255,.32);font-size:11px}
        .ms-alt-note{font-size:10px}
        .ms-osz-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .ms-sess-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        .ms-badge-reviewed{display:inline-flex;align-items:center;padding:2px 10px;background:rgba(75,210,143,.15);color:#4bd28f;border-radius:10px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:700}
        .ms-offline-banner{padding:7px 10px;background:rgba(240,100,60,.1);border:1px solid rgba(240,100,60,.3);border-radius:5px;color:rgba(255,140,100,.9);font-size:11px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
        .ms-offline-notice{padding:4px 8px;background:rgba(240,100,60,.08);border-left:3px solid rgba(240,100,60,.4);color:rgba(255,140,100,.8);font-size:11px;margin-bottom:6px;border-radius:2px}
        .ms-panel {
            margin-top: 6px;
            border-top: 1px solid rgba(255,255,255,.06);
            padding: 6px 10px 5px; /* Added matching horizontal padding to fix edge jam */
            font-size: 12px;
        }
        .ms-panel-header {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            color: rgba(255,255,255,.38);
            user-select: none;
            width: 100%; /* Keeps full width hitbox */
            padding: 4px 0;
        }
        .ms-panel-header:hover {
            color: rgba(255,255,255,.75);
        }
        .ms-panel-header:has(.ms-m-pick:hover) {
            color: rgba(255,255,255,.38);
        }
        .ms-m-pick {
            pointer-events: auto;
            margin-left: 6px;
            vertical-align: middle;
        }
        .ms-select-sm {
            font-size: 11px;
            padding: 4px 26px 4px 10px;
            height: 26px; /* Uniform height bounding box */
            box-sizing: border-box;
        }
        .ms-panel-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .08em;
            font-weight: 700;
        }
        .ms-global-tag{font-size:9px;background:rgba(255,200,0,.2);color:#f0c040;padding:1px 5px;border-radius:4px;vertical-align:middle;margin-left:3px}
        .ms-chevron {
            font-size: 9px;
            pointer-events: none;
            width: 10px;
            text-align: center;
        }
        .ms-panel-body{margin-top:8px}
        .ms-entry{padding:7px 9px;margin-bottom:5px;background:rgba(255,255,255,.04);border-radius:4px;border-left:3px solid rgba(255,255,255,.1)}
        .ms-role-lead_mentor{border-color:#ffd93d}.ms-role-mentor{border-color:#ff6b6b}.ms-role-mentee{border-color:#6bcb77}
        .ms-entry-pending{opacity:.7;border-style:dashed}
        .ms-entry-head{display:flex;align-items:center;gap:7px;margin-bottom:5px}
        .ms-avatar{width:22px;height:22px;border-radius:50%;flex-shrink:0;object-fit:cover;background:rgba(255,255,255,.1)}
        .ms-avatar-anon{display:inline-flex;align-items:center;justify-content:center;font-size:12px;color:rgba(255,255,255,.3);border:1px solid rgba(255,255,255,.1);width:22px;height:22px;border-radius:50%}
        .ms-entry-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
        .ms-entry-name{font-weight:600;color:rgba(255,255,255,.82)}
        .ms-entry-body{color:rgba(255,255,255,.78);line-height:1.55;white-space:pre-wrap}
        .ms-entry-actions{display:flex;gap:8px;margin-top:5px;padding-top:4px;border-top:1px solid rgba(255,255,255,.05)}
        .ms-edit-ta{width:100%;min-height:50px;margin-top:4px}
        .ms-del-btn{color:rgba(255,100,100,.6)!important}
        .ms-del-btn:hover{color:rgba(255,100,100,.9)!important}
        .ms-badges{display:inline-flex;align-items:center;gap:3px}
        .ms-role-chip{font-size:9px;padding:1px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.04em;font-weight:700;cursor:default}
        .ms-role-chip-lead_mentor{background:rgba(255,217,61,.15);color:#ffd93d}
        .ms-role-chip-mentor{background:rgba(255,107,107,.15);color:#ff6b6b}
        .ms-role-chip-mentee{background:rgba(107,203,119,.15);color:#6bcb77}
        .ms-badge-op{font-size:9px;padding:1px 6px;border-radius:8px;text-transform:uppercase;letter-spacing:.04em;font-weight:700;background:rgba(100,160,255,.18);color:#88aaff;cursor:default}
        .ms-badge-more{display:inline-flex;align-items:center;gap:3px;cursor:pointer}
        .ms-badge-more-btn{font-size:9px;padding:1px 5px;border-radius:8px;background:rgba(255,255,255,.1);color:rgba(255,255,255,.5)}
        .ms-badge-more-btn:hover{background:rgba(255,255,255,.18)}
        .ms-badge-more-list{display:none;gap:3px}
        .ms-badge-more--open .ms-badge-more-list{display:inline-flex}
        .ms-badge-more--open .ms-badge-more-btn{display:none}
        .ms-pending-tag{color:#f0a500;font-size:10px}
        .ms-form {
            border-top: 1px solid rgba(255,255,255,.06);
            padding-top: 12px;
            margin-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .ms-textarea {
            width: 100%;
            min-height: 70px;
            background: rgba(0,0,0,.20); /* Sleek background matches native osu comments */
            border: 1px solid rgba(255,255,255,.05);
            border-radius: 6px;
            color: #eee;
            padding: 12px 16px; /* Inner spacing alignment from image_10513f.png */
            font-size: 13px;
            resize: vertical;
            box-sizing: border-box;
            font-family: inherit;
            line-height: 1.5;
        }
        .ms-textarea:focus {
            outline: none;
            border-color: rgba(255,255,255,.15);
            background: rgba(0,0,0,.25);
        }
        .ms-form-row {
            display: flex;
            align-items: center;
            justify-content: space-between; /* Positions the drop-down selector left and Post button right */
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 2px;
        }
        .ms-form-label{display:flex;align-items:center;gap:4px;color:rgba(255,255,255,.45);font-size:11px;cursor:pointer;user-select:none}
        .ms-global-wrap{color:rgba(255,255,255,.5)}
        .ms-btn-submit {
            padding: 6px 20px; /* Chunkier padding matches native brown 'Respond' layout */
            border-radius: 4px;
            font-size: 12px;
        }
        .ms-btn{padding:4px 12px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600;border:1px solid transparent}
        .ms-btn-sm{padding:2px 9px;font-size:10px}
        .ms-btn-primary{background:#e8496a;color:#fff}
        .ms-btn-primary:hover{background:#cf3f5e}
        .ms-btn-primary:disabled{opacity:.4;cursor:not-allowed}
        .ms-btn-ghost{background:transparent;color:rgba(255,255,255,.4);border-color:rgba(255,255,255,.15)}
        .ms-btn-ghost:hover{color:rgba(255,255,255,.75);border-color:rgba(255,255,255,.35)}

        /* --- FULLY CUSTOMIZED ACCENT DROPDOWNS --- */
        .ms-select {
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            color: #fff;
            padding: 3px 24px 3px 10px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            outline: none;
            font-family: inherit;
            box-sizing: border-box;
            transition: background 0.1s ease, border-color 0.1s ease;

            /* Overrides the OS appearance styling engine entirely to clean up image_0fca38.png */
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;

            /* Custom clean native-looking chevron accent arrow */
            background-image: url("data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 8px center;
            background-size: 9px;
        }

        /* Targets dropdown option lists directly to eliminate forced system gray colors */
        .ms-select option {
            background-color: #221c1c; /* Deep dark palette matching osu cards */
            color: #fff;
            padding: 6px;
            font-weight: 500;
        }

        .ms-select:hover {
            background-color: rgba(0, 0, 0, 0.5);
            border-color: rgba(255, 255, 255, 0.18);
        }

        /* Specific sizing optimization to make the top menu element smaller */
        .ms-m-pick.ms-select-sm {
            font-size: 11px;
            padding: 2px 20px 2px 8px;
            height: 22px; /* Shrunk down layout height */
            background-position: right 6px center;
            background-size: 8px;
            vertical-align: middle;
            margin-left: 4px;
        }

        .ms-select:focus {
            border-color: rgba(255, 255, 255, 0.25);
            background-color: rgba(0, 0, 0, 0.45);
        }
        .ms-input{background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.1);border-radius:4px;color:#eee;padding:4px 8px;font-size:11px;width:260px;max-width:100%}
        .ms-input:focus{outline:none;border-color:rgba(255,255,255,.28)}

        /* --- TOP PANEL SPECIFIC SKELETON ELEMENTS --- */
       .ms-skeleton-top-body {
            display: flex;
            flex-direction: column;
            gap: 8px; /* Matches the exact gap of the real .ms-top-body */
            animation: ms-pulse 1.5s infinite ease-in-out;
        }
        .ms-skeleton-top-line {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            height: 18px; /* Taller line to mimic text + button height */
        }

        /* --- SKELETON LOADER ANIMATION --- */
        @keyframes ms-pulse {
            0% { opacity: 0.6; }
            50% { opacity: 0.3; }
            100% { opacity: 0.6; }
        }
        .ms-skeleton-card {
            padding: 10px 15px;
            margin-bottom: 8px;
            background: rgba(255,255,255,.03);
            border-radius: 6px;
            border-left: 4px solid rgba(255,255,255,.05);
            display: flex;
            flex-direction: column;
            gap: 8px;
            animation: ms-pulse 1.5s infinite ease-in-out;
        }
        .ms-skeleton-line {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 3px;
        }
        .ms-skeleton-header {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .ms-skeleton-avatar {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.05);
        }
        .ms-skeleton-name {
            width: 80px;
            height: 12px;
        }
        .ms-skeleton-text-1 {
            width: 60%;
            height: 14px;
            margin-top: 4px;
        }
        .ms-skeleton-text-2 {
            width: 40%;
            height: 14px;
        }

        /* --- EXPORT BUTTON HITBOX FIXES --- */
        .ms-link-btn{display:inline-block;background:none;border:none;color:#88c0d0;cursor:pointer;font-size:11px;padding:0;text-decoration:underline;width:max-content}
        .ms-link-btn:hover{color:#b0d8ec}
        .ms-icon-btn{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#88c0d0;cursor:pointer;font-size:11px;padding:3px 8px;border-radius:4px;transition:all 0.1s ease;display:inline-flex;align-items:center}
        .ms-icon-btn:hover{background:rgba(255,255,255,.15);color:#b0d8ec;border-color:rgba(255,255,255,.25)}

        .ms-notice{padding:5px 9px;background:rgba(255,200,0,.07);border:1px solid rgba(255,200,0,.2);border-radius:4px;color:rgba(255,200,0,.7);font-size:11px;margin-bottom:4px}
        .ms-empty{color:rgba(255,255,255,.28);font-style:italic;font-size:11px;margin:0}
        .ms-pending-badge{display:inline-flex;align-items:center;gap:8px;padding:2px 8px;background:rgba(240,165,0,.1);border:1px solid rgba(240,165,0,.25);border-radius:6px;color:#f0a500;font-size:11px;flex-wrap:wrap}
        `;
        document.head.appendChild(s);
    }

    injectStyles();
    init();

})();
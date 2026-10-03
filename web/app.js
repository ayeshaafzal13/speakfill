/* SpeakFill - frontend (vanilla JS, no build step) */
const $ = (s) => document.querySelector(s);
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const sid = sessionStorage.getItem("sid") || (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2));
sessionStorage.setItem("sid", sid);

const state = { forms: [], form: null, values: {}, fields: {}, unresolved: [], round: 0, demo: false,
  busy: false, guidedIdx: 0, forceConfirm: false, pdfUrl: null };

/* ---------- helpers ---------- */
function toast(msg, ms = 4000) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms);
}
function show(id) {
  const idx = { "s-setup": 0, "s-speak": 1, "s-guided": 1, "s-review": 2, "s-pdf": 3 }[id];
  document.querySelectorAll("#steps li").forEach((li, i) => (li.className = i === idx ? "on" : i < idx ? "done" : ""));
  ["s-setup", "s-speak", "s-guided", "s-review", "s-pdf"].forEach((s) => $("#" + s).classList.toggle("hidden", s !== id));
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function setUsage(u) {
  if (!u) return;
  $("#u-llm").textContent = u.llm; $("#u-stt").textContent = u.stt; $("#u-cache").textContent = u.cache_hits;
}
async function api(path, body, opts = {}) {
  if (state.busy) { toast("Please wait, still working…"); throw new Error("busy"); }  // one request at a time
  state.busy = true;
  document.querySelectorAll("button.primary").forEach((b) => (b.disabled = true));
  try {
    const res = await fetch(path, opts.formData
      ? { method: "POST", body: opts.formData }
      : body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Something went wrong. Please try again.");
    if (data.usage) setUsage(data.usage);
    return data;
  } catch (e) {
    if (e.message !== "busy") toast(e.message || "Network problem. Check your internet and try again.");
    throw e;
  } finally {
    state.busy = false;
    document.querySelectorAll("button.primary").forEach((b) => (b.disabled = false));
  }
}
const lang = () => { const [bcp, wh, force] = $("#lang").value.split("|"); return { bcp, whisper: wh, force: force === "1" }; };

/* ---------- voice: Whisper (accurate) or browser STT, with live mic meter ---------- */
const clean = (el, t) => (el.dataset.replace ? t.trim().replace(/[.۔,،]+$/, "") : t);
/* every text field gets its own mic: tap, speak, the value is filled */
function withMic(el) {
  if (el.tagName === "SELECT") return el;
  el.dataset.replace = "1";
  const w = document.createElement("div"); w.className = "fm";
  const ctl = document.createElement("div"); ctl.className = "fm-ctl";
  const b = document.createElement("button"); b.type = "button"; b.className = "mic tiny"; b.textContent = "🎤"; b.setAttribute("aria-label", "Speak this answer");
  const m = document.createElement("div"); m.className = "meter"; m.innerHTML = "<i></i><i></i><i></i><i></i><i></i>";
  const t = document.createElement("span"); t.className = "timer"; t.textContent = "0:00";
  const st = document.createElement("span"); st.className = "state"; st.textContent = "Tap to speak";
  ctl.append(b, m, t, st); w.append(el, ctl);
  b.onclick = () => Recorder.toggle(b, t, el);
  return w;
}
const Recorder = {
  active: null, timerInt: null,
  say(btn, msg) { const el = btn.parentElement.querySelector(".state"); if (el) el.textContent = msg; },
  tick(timerEl) { const t0 = Date.now(); clearInterval(this.timerInt); this.timerInt = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000); timerEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= 90) this.stop(); }, 250); },
  async toggle(micBtn, timerEl, target) {
    if (this.active) { this.stop(); return; }
    const L = lang(), eng = $("#engine").value, server = state.sttServer;
    let browser = eng === "browser" || (eng === "auto" && !server && !L.force);
    if (L.force && eng !== "browser") browser = false;
    if (!browser && !server) browser = !!SR;                 // no Whisper key on server -> try browser
    if (browser && !SR) return toast("Voice typing needs Chrome. Please type your answer instead.");
    this.active = { micBtn, target, wantStop: false, peak: 0, restarts: 0 };
    micBtn.classList.add("rec"); this.tick(timerEl); this.say(micBtn, "Starting microphone…");
    if (browser) this.startBrowser(L); else await this.startWhisper(L);
  },
  startBrowser(L) {
    const a = this.active, begin = () => {
      const base = a.target.dataset.replace ? "" : a.target.value.trim(), r = new SR();
      r.lang = L.bcp; r.continuous = true; r.interimResults = true;
      r.onstart = () => this.say(a.micBtn, "Listening… speak now");
      r.onspeechstart = () => this.say(a.micBtn, "Hearing you ✓");
      r.onresult = (e) => {  // rebuild from ALL results each time: avoids duplicate text on Android
        const t = Array.from(e.results).map((x) => x[0].transcript).join(" ").trim();
        a.target.value = clean(a.target, (base ? base + " " : "") + t); a.gotText = true; a.target.dispatchEvent(new Event("input", { bubbles: true }));
      };
      r.onerror = async (e) => {
        if (e.error === "no-speech" || e.error === "aborted") return;           // onend restarts
        a.wantStop = true;
        if (e.error === "not-allowed") toast("Microphone is blocked. Tap the lock icon in the address bar and allow it.", 6000);
        else if (e.error === "audio-capture") toast("No microphone found. Plug in or enable a microphone.", 6000);
        else if (state.sttServer) { toast("Browser voice failed. Switching to Whisper…"); this.cleanup(); this.active = { ...a, wantStop: false, peak: 0 }; a.micBtn.classList.add("rec"); await this.startWhisper(L); return; }
        else toast("Browser voice is not working. Please type instead.", 6000);
      };
      r.onend = () => {  // Chrome stops after silence: restart while the user has not pressed stop
        if (this.active !== a) return;
        if (!a.wantStop && a.restarts++ < 25) { try { begin(); } catch (e) { this.cleanup(); } } else this.cleanup();
      };
      a.rec = r; r.start();
    };
    begin();
  },
  async startWhisper(L) {
    const a = this.active;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m));
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined), chunks = [];
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      // live level meter: proves the mic hears you
      const AC = window.AudioContext || window.webkitAudioContext, ctx = new AC(), an = ctx.createAnalyser();
      an.fftSize = 256; ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize), bars = a.micBtn.parentElement.querySelectorAll(".meter i");
      const loop = () => { an.getByteTimeDomainData(buf); let pk = 0; for (const v of buf) pk = Math.max(pk, Math.abs(v - 128) / 128);
        a.peak = Math.max(a.peak, pk); bars.forEach((b, i) => (b.style.height = 6 + Math.min(1, pk * (2 + i * 0.5)) * 30 + "px")); a.raf = requestAnimationFrame(loop); };
      loop(); a.ctx = ctx; a.stream = stream;
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: mr.mimeType || "audio/webm" }), peak = a.peak, btn = a.micBtn;
        this.cleanup();
        if (peak < 0.03 || blob.size < 2000) { this.say(btn, "We could not hear you."); return toast("We could not hear any sound. Check your microphone, speak closer, or type.", 6000); }
        this.say(btn, "Converting your voice to text…");
        try {
          const fd = new FormData(); fd.append("audio", blob, "voice." + (blob.type.includes("mp4") ? "m4a" : "webm")); fd.append("lang", L.whisper); fd.append("session_id", sid);
          const data = await api("/api/transcribe", null, { formData: fd });
          if (!data.text) { this.say(btn, "No words recognised."); return toast("No words recognised. Please try again or type."); }
          a.target.value = clean(a.target, (a.target.dataset.replace || !a.target.value ? "" : a.target.value.trim() + " ") + data.text); a.target.dispatchEvent(new Event("input", { bubbles: true })); this.say(btn, "Done. Check the text below ✓");
        } catch (e) { this.say(btn, "Voice failed. Please type instead."); }
      };
      a.mr = mr; mr.start(); this.say(a.micBtn, "Recording… speak, then tap to stop");
    } catch (e) {
      toast(e.name === "NotAllowedError" ? "Microphone is blocked. Allow it from the address bar." : "Cannot use the microphone. Please type instead.", 6000); this.cleanup();
    }
  },
  stop() {
    const a = this.active; if (!a) return;
    a.wantStop = true;
    if (a.rec) { try { a.rec.stop(); } catch (e) {} }
    if (a.mr && a.mr.state !== "inactive") { a.mr.stop(); return; }   // onstop will cleanup
    this.cleanup();
  },
  cleanup() {
    const a = this.active; clearInterval(this.timerInt);
    if (a) { a.micBtn.classList.remove("rec"); cancelAnimationFrame(a.raf); if (a.ctx) a.ctx.close().catch(() => {});
      a.micBtn.parentElement.querySelectorAll(".meter i").forEach((b) => (b.style.height = "6px"));
      if (a.rec && !a.mr) this.say(a.micBtn, a.gotText ? "Done. Check the text below ✓" : "Tap the microphone and speak"); }
    this.active = null;
  },
};
$("#mic-main").onclick = () => Recorder.toggle($("#mic-main"), $("#timer"), $("#transcript"));
$("#mic-clarify").onclick = () => Recorder.toggle($("#mic-clarify"), $("#timer-c"), $("#clarify-text"));
$("#mic-guided").onclick = () => Recorder.toggle($("#mic-guided"), $("#timer-g"), $("#g-input"));

/* ---------- step 1: choose form ---------- */
async function init() {
  try {
    const h = await (await fetch("/api/health")).json(); state.sttServer = h.stt_fallback;
    state.forms = await (await fetch("/api/forms")).json();
    const box = $("#form-list");
    state.forms.forEach((f, i) => {
      const b = document.createElement("button");
      b.className = "choice"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", i === 0);
      const ic = {job_application:"💼",university_admission:"🎓",bank_account:"🏦",complaint_letter:"📝"}[f.id] || "📄";
      b.innerHTML = `<span class="ic">${ic}</span><b>${f.title_en}</b><span class="ur" lang="ur">${f.title_ur}</span><small>${f.field_count} fields</small>`;
      b.onclick = () => { box.querySelectorAll(".choice").forEach((c) => c.setAttribute("aria-checked", c === b)); state.formId = f.id; };
      box.appendChild(b);
    });
    state.formId = state.forms[0].id;
    if (!SR && !state.sttServer) toast("Voice needs Chrome (or a Groq key on the server). You can still type.", 6000);
  } catch (e) { toast("Cannot reach the server. Is it running?"); }
}
async function loadForm(id) { state.form = await (await fetch("/api/forms/" + id)).json(); }

$("#btn-start").onclick = async () => {
  state.demo = false; state.values = {}; state.fields = {}; state.round = 0;
  await loadForm(state.formId);
  if ($("#mode").value === "guided") { state.guidedIdx = 0; renderGuided(); show("s-guided"); }
  else { $("#transcript").value = ""; show("s-speak"); }
};
$("#btn-back1").onclick = () => show("s-setup");

/* offline demo: pre-recorded transcript + cached model answer, works with every API down */
$("#btn-demo").onclick = async () => {
  try {
    const d = await (await fetch("/api/demo")).json();
    state.formId = d.form_id; await loadForm(d.form_id); state.demo = true; state.demoFollowup = d.followup_answers;
    $("#transcript").value = d.transcript; show("s-speak"); toast("Demo loaded. Press 'Fill the form'.");
  } catch (e) { toast("Demo data not available."); }
};

/* ---------- step 2: extract ---------- */
$("#btn-extract").onclick = async () => {
  const transcript = $("#transcript").value.trim();
  if (!transcript) return toast("Please speak or type something first.");
  Recorder.stop();
  try {
    const pkg = await api("/api/extract", { form_id: state.form.id, transcript, session_id: sid, demo: state.demo });
    state.round = 0; applyPackage(pkg, true); show("s-review");
    if (pkg.provider === "rules") toast("AI is busy right now. Filled what we could; please check the rest.", 6000);
  } catch (e) {}
};

function applyPackage(pkg, replaceAll = false) {
  if (replaceAll) { state.values = {}; state.fields = {}; }
  Object.entries(pkg.fields).forEach(([id, f]) => {
    state.fields[id] = f;
    if (f.value !== null && f.value !== undefined) state.values[id] = f.value;
    else if (!(id in state.values)) state.values[id] = "";
  });
  state.unresolved = pkg.unresolved || []; state.manual = pkg.manual || [];
  state.questions = pkg.questions || [];
  renderRows(); renderClarify();
}

/* ---------- step 3: review ---------- */
function inputFor(f, val) {
  let el;
  if (f.type === "select") {
    el = document.createElement("select");
    el.innerHTML = `<option value="">-- choose --</option>` + f.options.map((o) => `<option ${o === val ? "selected" : ""}>${o}</option>`).join("");
  } else if (f.type === "textarea" || f.type === "address") {
    el = document.createElement("textarea"); el.rows = f.type === "textarea" ? 3 : 2; el.value = val || ""; el.dir = "auto";
  } else {
    el = document.createElement("input"); el.type = "text"; el.value = val || ""; el.dir = "auto";
    if (f.type === "phone" || f.type === "cnic" || f.type === "number") el.inputMode = "numeric";
    if (f.example) el.placeholder = "e.g. " + f.example;
  }
  return el;
}
function renderRows() {
  const box = $("#rows"); box.innerHTML = "";
  state.form.fields.forEach((f) => {
    const info = state.fields[f.id] || { status: "empty", message: "" };
    const manual = state.manual && state.manual.includes(f.id);
    const row = document.createElement("div"); row.className = "row s-" + info.status; row.dataset.id = f.id;
    row.innerHTML = `<div class="lab"><b>${f.label_en}${f.required ? ' <span class="req" title="required">*</span>' : ""}</b><span class="ur" lang="ur">${f.label_ur}</span></div>`;
    const wrap = document.createElement("div"); const el = inputFor(f, state.values[f.id]);
    el.setAttribute("aria-label", f.label_en);
    el.oninput = () => { state.values[f.id] = el.value; row.className = "row s-edited"; const m = row.querySelector(".msg"); if (m) m.remove(); };  // local edit, no API call
    wrap.appendChild(withMic(el)); row.appendChild(wrap);
    const msg = manual ? "Please fill manually" : info.message;
    if (msg) { const p = document.createElement("p"); p.className = "msg"; p.textContent = msg; row.appendChild(p); }
    box.appendChild(row);
  });
}
function renderClarify() {
  const panel = $("#clarify"), list = $("#clarify-list");
  if (!state.questions.length) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden"); list.innerHTML = ""; $("#clarify-text").value = "";
  state.questions.forEach((q) => {
    const f = state.form.fields.find((x) => x.id === q.id);
    const d = document.createElement("div"); d.className = "q";
    d.innerHTML = `<label>${q.question_en}<span class="ur" lang="ur">${q.question_ur}</span></label>`;
    const el = inputFor(f, state.demo && state.demoFollowup ? (state.demoFollowup[q.id] || "") : ""); el.dataset.qid = q.id; d.appendChild(withMic(el));
    if (q.problem) { const p = document.createElement("p"); p.className = "msg"; p.style.color = "var(--red)"; p.textContent = q.problem; d.appendChild(p); }
    list.appendChild(d);
  });
}
$("#btn-clarify").onclick = async () => {
  const answers = {};
  document.querySelectorAll("#clarify-list [data-qid]").forEach((el) => { if (el.value.trim()) answers[el.dataset.qid] = el.value.trim(); });
  const answer_text = $("#clarify-text").value.trim();
  if (!Object.keys(answers).length && !answer_text) return toast("Type or say at least one answer.");
  Recorder.stop();
  try {
    const pkg = await api("/api/clarify", { form_id: state.form.id, unresolved: state.unresolved, answers, answer_text, round: state.round, session_id: sid });
    state.round += 1; applyPackage(pkg);
    if (pkg.manual && pkg.manual.length) toast("Some fields need to be filled by you. They are marked in red.", 6000);
  } catch (e) {}
};
$("#btn-skip-clarify").onclick = () => { state.manual = state.unresolved; state.unresolved = []; state.questions = []; renderRows(); renderClarify(); };

/* ---------- guided mode (zero AI calls until the final local check) ---------- */
function renderGuided() {
  const f = state.form.fields[state.guidedIdx];
  $("#g-title").textContent = `Question ${state.guidedIdx + 1} of ${state.form.fields.length}`;
  $("#g-ur").textContent = f.label_ur; $("#g-en").textContent = f.label_en + (f.required ? "" : " (optional)") + (f.example ? `  e.g. ${f.example}` : "");
  const wrap = $("#g-input-wrap"); wrap.innerHTML = ""; const el = inputFor(f, state.values[f.id] || ""); el.id = "g-input"; wrap.appendChild(el); el.focus();
  $("#g-progress").max = state.form.fields.length; $("#g-progress").value = state.guidedIdx;
  $("#g-prev").disabled = state.guidedIdx === 0;
  $("#g-next").textContent = state.guidedIdx === state.form.fields.length - 1 ? "Finish" : "Next";
}
async function guidedAdvance(skip) {
  Recorder.stop();
  const f = state.form.fields[state.guidedIdx];
  if (!skip) state.values[f.id] = $("#g-input").value.trim();
  if (state.guidedIdx < state.form.fields.length - 1) { state.guidedIdx++; renderGuided(); return; }
  try { const pkg = await api("/api/validate", { form_id: state.form.id, values: state.values, session_id: sid }); state.round = 0; applyPackage(pkg, true); show("s-review"); } catch (e) {}
}
$("#g-next").onclick = () => guidedAdvance(false);
$("#g-skip").onclick = () => guidedAdvance(true);
$("#g-prev").onclick = () => { if (state.guidedIdx > 0) { Recorder.stop(); state.guidedIdx--; renderGuided(); } };

/* ---------- confirm + PDF ---------- */
$("#btn-confirm").onclick = async () => {
  try {
    const pkg = await api("/api/validate", { form_id: state.form.id, values: state.values, session_id: sid });  // local check only
    Object.entries(pkg.fields).forEach(([id, f]) => { state.fields[id] = f; if (f.value) state.values[id] = f.value; });
    const blocking = Object.values(pkg.fields).filter((f) => f.status === "missing" || f.status === "invalid").length;
    state.manual = []; renderRows();
    if (blocking && !state.forceConfirm) {
      state.forceConfirm = true; $("#btn-confirm").textContent = "Make PDF anyway";
      toast(`${blocking} field(s) need attention (red). Fix them, or press again to continue.`, 6000); return;
    }
    state.forceConfirm = false; $("#btn-confirm").textContent = "Confirm and make PDF";
    const res = await fetch("/api/pdf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ form_id: state.form.id, values: state.values }) });
    if (!res.ok) throw new Error("Could not create the PDF. Please try again.");
    const blob = await res.blob();
    if (state.pdfUrl) URL.revokeObjectURL(state.pdfUrl);
    state.pdfUrl = URL.createObjectURL(blob);
    $("#pdf-download").href = state.pdfUrl; $("#pdf-download").download = state.form.id + ".pdf"; $("#pdf-frame").src = state.pdfUrl;
    show("s-pdf");
  } catch (e) { if (e.message !== "busy") toast(e.message); }
};
$("#btn-back-review").onclick = () => show("s-review");
$("#btn-restart").onclick = () => { state.demo = false; show("s-setup"); };

init();

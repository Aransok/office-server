"use strict";
const csrf = document.body.dataset.csrf;
const $ = (s) => document.querySelector(s);
const msg = (t, bad) => { const m = $("#msg"); if (m) { m.textContent = t; m.className = bad ? "bad" : ""; } };

async function api(url, body, method = "POST") {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json", "X-CSRF": csrf }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || "Грешка");
  return j;
}

function ask(text, bodyNode) {
  const d = $("#dlg");
  $("#dlg-text").textContent = text;
  const b = $("#dlg-body");
  b.replaceChildren(...(bodyNode ? [bodyNode] : []));
  return new Promise((res) => {
    d.onclose = () => res(d.returnValue === "ok");
    d.returnValue = "";
    d.showModal();
  });
}

function textInput(value = "") {
  const i = document.createElement("input");
  i.value = value;
  return i;
}

const fm = $("#fm");
if (fm) {
  const here = fm.dataset.path;
  const rows = () => [...document.querySelectorAll("tbody tr[data-path]")];
  const picked = () => rows().filter((r) => r.querySelector(".pick").checked);
  const paths = () => picked().map((r) => r.dataset.path);
  const refresh = () => {
    const n = picked().length;
    document.querySelectorAll(".sel").forEach((b) => (b.disabled = n === 0 || (b.classList.contains("one") && n !== 1)));
  };
  document.addEventListener("change", refresh);
  const run = async (fn) => { try { await fn(); location.reload(); } catch (e) { msg(e.message, true); } };
  const on = (id, fn) => { const b = $(id); if (b) b.onclick = fn; };

  on("#b-mkdir", async () => {
    const i = textInput();
    if (await ask("Име на новата папка:", i)) run(() => api("/api/mkdir", { p: here, name: i.value }));
  });
  on("#b-rename", async () => {
    const r = picked()[0], i = textInput(r.dataset.name);
    if (await ask("Ново име:", i)) run(() => api("/api/rename", { p: r.dataset.path, name: i.value }));
  });
  on("#b-del", async () => {
    if (await ask(`Да се изтрият ${picked().length} елемента? Могат да се върнат от кошчето.`)) run(() => api("/api/delete", { paths: paths() }));
  });
  on("#b-zip", () => {
    location.href = "/zip?" + paths().map((p) => "p=" + encodeURIComponent(p)).join("&");
  });

  async function pickFolder(text) {
    const list = await (await fetch("/api/folders")).json();
    const s = document.createElement("select");
    list.forEach((f) => s.add(new Option(f || "Начало", f)));
    return (await ask(text, s)) ? s.value : null;
  }
  for (const [id, url, text] of [["#b-move", "/api/move", "Премести в:"], ["#b-copy", "/api/copy", "Копирай в:"]]) {
    on(id, async () => {
      const dest = await pickFolder(text);
      if (dest !== null) run(() => api(url, { paths: paths(), dest }));
    });
  }

  // upload: one request per file, raw body, so big files are never held in memory
  async function sendOne(file, mode) {
    const q = new URLSearchParams({ p: here, name: file.name, mode });
    const r = await fetch("/api/upload?" + q, { method: "PUT", headers: { "X-CSRF": csrf }, body: file });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || "Грешка");
  }
  async function upload(files) {
    const max = Number(fm.dataset.max) * 1048576;
    let all = null, done = 0;
    for (const f of files) {
      if (f.size > max) { msg(`${f.name}: по-голям от ${fm.dataset.max} MB`, true); continue; }
      let mode = "";
      const ex = await (await fetch(`/api/exists?p=${encodeURIComponent(here)}&name=${encodeURIComponent(f.name)}`)).json();
      if (ex.exists) {
        mode = all;
        if (!mode) {
          const s = document.createElement("select");
          s.add(new Option("Замени", "replace")); s.add(new Option("Запази и двата", "both")); s.add(new Option("Пропусни", "skip"));
          const c = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox";
          c.append(cb, " за всички"); const box = document.createElement("div"); box.append(s, c);
          if (!(await ask(`„${f.name}“ вече съществува.`, box))) continue;
          mode = s.value;
          if (cb.checked) all = mode;
        }
      }
      try { msg(`Качване: ${f.name}`); await sendOne(f, mode); done++; } catch (e) { msg(`${f.name}: ${e.message}`, true); return; }
    }
    msg(`Качени: ${done}`);
    location.reload();
  }
  on("#b-upload", () => $("#file-in").click());
  const inp = $("#file-in");
  if (inp) inp.onchange = () => upload([...inp.files]);
  const drop = $("#drop");
  if (drop) {
    ["dragover", "drop"].forEach((e) => document.addEventListener(e, (ev) => ev.preventDefault()));
    document.addEventListener("drop", (ev) => upload([...ev.dataTransfer.files].filter((f) => f.type || f.size)));
    document.addEventListener("dragover", () => drop.classList.add("on"));
    document.addEventListener("dragleave", () => drop.classList.remove("on"));
  }
}

document.querySelectorAll(".restore").forEach((b) => (b.onclick = async () => {
  try { await api("/api/trash/restore", { id: Number(b.dataset.id) }); location.reload(); } catch (e) { msg(e.message, true); }
}));
const emp = $("#empty");
if (emp) emp.onclick = async () => {
  if (confirm("Да се изпразни кошчето завинаги?")) { await api("/api/trash/empty", {}); location.reload(); }
};

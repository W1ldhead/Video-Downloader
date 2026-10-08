"use strict";

// Единый доступ к API: Firefox — browser.* (обещания), Chrome/Edge/Яндекс — chrome.* (тоже обещания в MV3)
const api = globalThis.browser || globalThis.chrome;

// Имя файла по площадке — совпадает с названиями в Video Downloader
const PLATFORMS = [
  [/(^|\.)tiktok\.com$/i, "TikTok"],
  [/(^|\.)youtube\.com$/i, "YouTube"],
  [/(^|\.)youtu\.be$/i, "YouTube"],
  [/(^|\.)instagram\.com$/i, "Instagram"],
  [/(^|\.)x\.com$/i, "X"],
  [/(^|\.)twitter\.com$/i, "X"],
];

function platformName(host) {
  for (const [re, name] of PLATFORMS) {
    if (re.test(host)) return name;
  }
  return host || "cookies";
}

// Одна строка в формате Netscape: domain \t includeSubdomains \t path \t secure \t expiry \t name \t value
function cookieLine(c) {
  let domain, includeSub;
  if (c.hostOnly) {
    domain = c.domain.replace(/^\./, "");
    includeSub = "FALSE";
  } else {
    domain = c.domain.startsWith(".") ? c.domain : "." + c.domain;
    includeSub = "TRUE";
  }
  const secure = c.secure ? "TRUE" : "FALSE";
  const expiry = c.expirationDate ? Math.floor(c.expirationDate) : 0;
  // httpOnly cookies yt-dlp читает по префиксу #HttpOnly_ (сам же их туда и пишет)
  const prefix = c.httpOnly ? "#HttpOnly_" : "";
  return [prefix + domain, includeSub, c.path, secure, expiry, c.name, c.value].join("\t");
}

function toNetscape(cookies) {
  const lines = ["# Netscape HTTP Cookie File", "# Создано расширением «cookies.txt для загрузчика»", ""];
  for (const c of cookies) lines.push(cookieLine(c));
  return lines.join("\n") + "\n";
}

function setStatus(text, isError) {
  const el = document.getElementById("status");
  el.textContent = text;
  el.className = isError ? "error" : "";
}

async function currentTab() {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  return tab;
}

// Сохранение через ссылку с blob — работает одинаково в Chrome и Firefox,
// файл уходит в папку «Загрузки» (или спросит путь, если так настроен браузер)
function saveFile(text, filename) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function save() {
  const scope = document.querySelector('input[name="scope"]:checked').value;
  api.storage.local.set({ scope });

  let cookies;
  let filename;
  try {
    if (scope === "all") {
      cookies = await api.cookies.getAll({});
      filename = "cookies.txt";
    } else {
      const tab = await currentTab();
      if (!tab || !tab.url || !/^https?:/i.test(tab.url)) {
        setStatus("Откройте обычную страницу сайта (http/https) и попробуйте снова.", true);
        return;
      }
      const host = new URL(tab.url).hostname;
      cookies = await api.cookies.getAll({ url: tab.url });
      filename = platformName(host) + ".txt";
    }
  } catch (e) {
    setStatus("Не удалось прочитать cookies: " + e.message, true);
    return;
  }

  if (!cookies.length) {
    setStatus("Cookies не найдены. Войдите в аккаунт на сайте и попробуйте снова.", true);
    return;
  }

  saveFile(toNetscape(cookies), filename);
  setStatus(`Сохранено: ${cookies.length} cookies → ${filename} (папка «Загрузки»)`);
}

// Восстановить выбор и показать, какой файл получится
api.storage.local.get("scope").then(({ scope }) => {
  if (scope) {
    const el = document.querySelector(`input[name="scope"][value="${scope}"]`);
    if (el) el.checked = true;
  }
});

currentTab().then((tab) => {
  if (tab && tab.url && /^https?:/i.test(tab.url)) {
    const host = new URL(tab.url).hostname;
    document.getElementById("save").textContent = `Сохранить ${platformName(host)}.txt`;
  }
});

document.getElementById("save").addEventListener("click", save);

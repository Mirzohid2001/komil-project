/**
 * Admin panel: Telegram registratsiya so‘rovlari uchun ovozli + OS bildirishnoma.
 * YouTube / boshqa tab ochiq bo‘lsa ham eshitish uchun Browser Notification ishlatiladi.
 */
(function () {
  'use strict';

  if (!/\/admin\//.test(window.location.pathname)) return;

  var POLL_URL = '/admin/accounts/registrationrequest/pending-alerts/';
  var STORAGE_KEY = 'isomer_admin_alert_since';
  var PERM_HINT_KEY = 'isomer_admin_notif_hint_dismissed';
  var POLL_MS = 4000;
  var originalTitle = document.title;
  var audioCtx = null;
  var unlocked = false;
  var baselineReady = false;

  function getSinceId() {
    var raw = localStorage.getItem(STORAGE_KEY);
    var n = parseInt(raw || '0', 10);
    return isNaN(n) ? 0 : n;
  }

  function setSinceId(id) {
    localStorage.setItem(STORAGE_KEY, String(id));
  }

  function ensureAudio() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      if (!audioCtx) audioCtx = new Ctx();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      unlocked = true;
      return audioCtx;
    } catch (e) {
      return null;
    }
  }

  function playBeep() {
    var ctx = ensureAudio();
    if (!ctx) return;
    var now = ctx.currentTime;
    function tone(freq, start, dur, gain) {
      var osc = ctx.createOscillator();
      var g = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(gain, start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      osc.connect(g);
      g.connect(ctx.destination);
      osc.start(start);
      osc.stop(start + dur + 0.02);
    }
    // Ikki marta "ding" — e'tibor uchun
    tone(880, now, 0.18, 0.22);
    tone(1175, now + 0.22, 0.22, 0.2);
    tone(880, now + 0.55, 0.28, 0.24);
  }

  function showOsNotification(alert) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    try {
      var n = new Notification(alert.title || 'Isomer Oil', {
        body: alert.body || 'Yangi registratsiya hodisasi',
        tag: 'isomer-reg-' + alert.id,
        requireInteraction: alert.kind === 'reg_pending',
        silent: false, // OS ovozini yoqish
      });
      n.onclick = function () {
        window.focus();
        if (alert.link) {
          window.location.href = alert.link;
        }
        n.close();
      };
    } catch (e) {
      /* ignore */
    }
  }

  function flashTitle(text) {
    var ticks = 0;
    var timer = setInterval(function () {
      document.title = ticks % 2 === 0 ? '🔔 ' + text : originalTitle;
      ticks += 1;
      if (ticks > 10) {
        clearInterval(timer);
        document.title = originalTitle;
      }
    }, 800);
  }

  function toast(alert) {
    var el = document.getElementById('isomer-reg-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'isomer-reg-toast';
      el.setAttribute('role', 'alert');
      el.style.cssText =
        'position:fixed;right:18px;bottom:18px;z-index:99999;max-width:360px;' +
        'background:#0f2a1c;color:#f7f4ec;padding:14px 16px;border-radius:12px;' +
        'box-shadow:0 12px 40px rgba(0,0,0,.35);border:1px solid rgba(201,162,39,.45);' +
        'font-family:inherit;cursor:pointer;display:none;';
      document.body.appendChild(el);
    }
    el.innerHTML =
      '<div style="font-weight:700;margin-bottom:4px;color:#e8c96a;">' +
      escapeHtml(alert.title) +
      '</div><div style="font-size:13px;opacity:.92;">' +
      escapeHtml(alert.body || '') +
      '</div><div style="margin-top:8px;font-size:12px;color:#c9a227;">Bosib ochish →</div>';
    el.style.display = 'block';
    el.onclick = function () {
      if (alert.link) window.location.href = alert.link;
    };
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(function () {
      el.style.display = 'none';
    }, 12000);
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function handleAlerts(alerts) {
    if (!alerts || !alerts.length) return;
    var maxId = getSinceId();
    alerts.forEach(function (alert) {
      if (alert.id > maxId) maxId = alert.id;
      playBeep();
      showOsNotification(alert);
      toast(alert);
      flashTitle(alert.title || 'Yangi so‘rov');
    });
    setSinceId(maxId);
  }

  function poll() {
    var since = getSinceId();
    var url = POLL_URL + '?since_id=' + encodeURIComponent(since);
    fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) return null;
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data) return;
        updateBadge(data.pending_count || 0);
        // Birinchi poll:
        // - localStorage bo‘sh → eski backlogga ovoz chalmasin
        // - oldin kuzatilgan → admin yopiq paytda kelgan yangilar chalinsin
        if (!baselineReady) {
          baselineReady = true;
          if (!since) {
            if (data.latest_id) setSinceId(data.latest_id);
            return;
          }
        }
        handleAlerts(data.alerts || []);
      })
      .catch(function () {
        /* ignore network blips */
      });
  }

  function updateBadge(count) {
    var id = 'isomer-pending-reg-badge';
    var badge = document.getElementById(id);
    var link =
      document.querySelector('a[href*="/admin/accounts/registrationrequest/"]') ||
      null;
    if (count <= 0) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement('span');
      badge.id = id;
      badge.style.cssText =
        'display:inline-flex;align-items:center;justify-content:center;' +
        'min-width:1.35rem;height:1.35rem;padding:0 6px;margin-left:6px;' +
        'border-radius:999px;background:#dc2626;color:#fff;font-size:11px;font-weight:700;';
      if (link) link.appendChild(badge);
      else {
        badge.style.position = 'fixed';
        badge.style.top = '12px';
        badge.style.right = '12px';
        badge.style.zIndex = '99998';
        badge.style.marginLeft = '0';
        document.body.appendChild(badge);
      }
    }
    badge.textContent = String(count);
  }

  function showPermissionHint() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'granted') return;
    if (Notification.permission === 'denied') return;
    if (localStorage.getItem(PERM_HINT_KEY) === '1') return;

    var bar = document.createElement('div');
    bar.id = 'isomer-notif-hint';
    bar.style.cssText =
      'position:fixed;left:50%;transform:translateX(-50%);bottom:20px;z-index:100000;' +
      'background:#163528;color:#f7f4ec;padding:12px 16px;border-radius:12px;' +
      'box-shadow:0 10px 30px rgba(0,0,0,.3);border:1px solid rgba(201,162,39,.4);' +
      'display:flex;gap:12px;align-items:center;max-width:92vw;font-size:13px;';
    bar.innerHTML =
      '<span>YouTube / boshqa sahifada ham eshitish uchun brauzer bildirishnomasini yoqing.</span>';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = 'Ovozni yoqish';
    btn.style.cssText =
      'background:#c9a227;color:#0a1610;border:0;border-radius:8px;padding:8px 12px;' +
      'font-weight:700;cursor:pointer;white-space:nowrap;';
    btn.onclick = function () {
      ensureAudio();
      Notification.requestPermission().finally(function () {
        bar.remove();
      });
    };
    var dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.textContent = '×';
    dismiss.title = 'Yopish';
    dismiss.style.cssText =
      'background:transparent;border:0;color:#f7f4ec;font-size:20px;cursor:pointer;line-height:1;';
    dismiss.onclick = function () {
      localStorage.setItem(PERM_HINT_KEY, '1');
      bar.remove();
    };
    bar.appendChild(btn);
    bar.appendChild(dismiss);
    document.body.appendChild(bar);
  }

  // Birinchi klik — audio unlock (brauzer siyosati)
  ['pointerdown', 'keydown'].forEach(function (ev) {
    document.addEventListener(
      ev,
      function () {
        if (!unlocked) ensureAudio();
      },
      { once: false, passive: true }
    );
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', showPermissionHint);
  } else {
    showPermissionHint();
  }

  poll();
  // Asosiy tab timer + Worker (fon/YouTube tabda setInterval sekinlashadi)
  setInterval(poll, POLL_MS);
  try {
    var workerSrc =
      'setInterval(function(){postMessage(1)},' + POLL_MS + ');';
    var blob = new Blob([workerSrc], { type: 'application/javascript' });
    var worker = new Worker(URL.createObjectURL(blob));
    worker.onmessage = function () {
      poll();
    };
  } catch (e) {
    /* Worker bo‘lmasa setInterval yetarli */
  }
})();

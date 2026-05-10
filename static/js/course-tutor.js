/**
 * Course page "Talk to tutor" — conversational voice UX + persistent audio playback.
 * Expects DOM ids from course_detail.html and #course-tutor-config data-* URLs.
 */
(function () {
  'use strict';

  var cfg = document.getElementById('course-tutor-config');
  if (!cfg) return;

  var msgUrl = cfg.getAttribute('data-message-url');
  var courseId = cfg.getAttribute('data-course-id');
  var convStorageKey = 'tutor_conversation_id_' + courseId;
  var voicePrefKey = 'courseTutorVoiceEnabled';

  var fab = document.getElementById('course-tutor-open');
  var panel = document.getElementById('course-tutor-panel');
  var closeBtn = document.getElementById('course-tutor-close');
  var sendBtn = document.getElementById('course-tutor-send');
  var micBtn = document.getElementById('course-tutor-mic');
  var inp = document.getElementById('course-tutor-input');
  var box = document.getElementById('course-tutor-messages');
  var warnEl = document.getElementById('course-tutor-warnings');
  var speakToggle = document.getElementById('course-tutor-speak-toggle');
  var replayBtn = document.getElementById('course-tutor-replay');
  var statusEl = document.getElementById('course-tutor-status');
  if (!fab || !panel || !sendBtn || !inp || !box) return;

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  /** @type {SpeechRecognition|null} */
  var recognition = null;
  var conversationId = null;
  var lastAudioBase64 = null;
  var lastAudioMime = null;

  var state = 'idle';
  var isSending = false;

  /** Voice capture (reset each startListening). */
  var finalTranscript = '';
  var interimTranscript = '';
  /** Confidence from the last isFinal segment (if API provides it). */
  var lastFinalConfidence = null;
  var lastSpeechAt = 0;
  var autoSubmitTimer = null;

  var lastSentVoiceText = '';
  var lastSentVoiceAt = 0;

  var SILENCE_AFTER_FINAL_MS = 1500;
  var VOICE_DEDUPE_MS = 5000;
  var CONFIDENCE_AUTO_SEND = 0.65;

  /** Incremented each startListening so stale handlers/timers are ignored. */
  var listenGeneration = 0;

  if (!window.courseTutorAudio) {
    window.courseTutorAudio = new Audio();
  }
  var audio = window.courseTutorAudio;
  var activeBlobUrl = null;

  function logAudio() {
    return '[course-tutor-audio]';
  }

  function stopTutorPlayback() {
    try {
      audio.pause();
      audio.currentTime = 0;
      console.debug(logAudio(), 'pause/stop');
    } catch (e) {
      console.debug(logAudio(), 'stop error', e);
    }
  }

  function revokeActiveBlob() {
    if (activeBlobUrl) {
      try {
        URL.revokeObjectURL(activeBlobUrl);
      } catch (e) {}
      activeBlobUrl = null;
    }
  }

  function wireAudioDebug() {
    audio.addEventListener('playing', function () {
      console.debug(logAudio(), 'playing, duration=', audio.duration);
    });
    audio.addEventListener('ended', function () {
      console.debug(logAudio(), 'ended event, duration=', audio.duration);
    });
    audio.addEventListener('stalled', function () {
      console.warn(logAudio(), 'stalled');
    });
    audio.addEventListener('waiting', function () {
      console.debug(logAudio(), 'waiting');
    });
    audio.addEventListener('error', function () {
      var err = audio.error;
      console.warn(logAudio(), 'error', err ? err.code : null, err);
    });
    audio.addEventListener('abort', function () {
      console.debug(logAudio(), 'abort');
    });
  }
  wireAudioDebug();

  /**
   * Play MP3 from base64. Revokes previous blob only when replacing or after natural end.
   * Do NOT revoke in play() promise finally — that fires when playback starts and truncates audio.
   */
  function playFromBase64(b64, mime, onEnded) {
    if (!b64) return;
    stopTutorPlayback();
    revokeActiveBlob();

    try {
      var bin = atob(b64);
      var len = bin.length;
      console.debug(logAudio(), 'decoded bytes=', len);
      var bytes = new Uint8Array(len);
      for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
      var blob = new Blob([bytes], { type: mime || 'audio/mpeg' });
      activeBlobUrl = URL.createObjectURL(blob);

      audio.onended = function () {
        console.debug(logAudio(), 'onended handler, duration=', audio.duration);
        revokeActiveBlob();
        audio.onended = null;
        setState('idle');
        if (typeof onEnded === 'function') onEnded();
      };
      audio.onerror = function () {
        console.warn(logAudio(), 'onerror during playback');
        revokeActiveBlob();
        setState('idle');
      };

      audio.src = activeBlobUrl;
      audio.load();
      setState('speaking');
      var p = audio.play();
      if (p && typeof p.then === 'function') {
        p.then(function () {
          console.debug(logAudio(), 'play() promise resolved (started)');
        }).catch(function (err) {
          console.warn(logAudio(), 'play() rejected', err);
          setState('idle');
        });
      }
    } catch (e) {
      console.warn(logAudio(), 'decode/play failed', e);
      appendMsg('assistant', 'Could not play audio in this browser.', true);
      setState('idle');
    }
  }

  function loadVoicePref() {
    try {
      var raw = localStorage.getItem(voicePrefKey);
      if (raw === null || raw === '') return true;
      return raw === '1' || raw === 'true';
    } catch (e) {
      return true;
    }
  }

  function saveVoicePref(on) {
    try {
      localStorage.setItem(voicePrefKey, on ? '1' : '0');
    } catch (e) {}
  }

  if (speakToggle) {
    speakToggle.checked = loadVoicePref();
    speakToggle.addEventListener('change', function () {
      saveVoicePref(!!speakToggle.checked);
    });
  }

  function voiceEnabled() {
    return speakToggle ? !!speakToggle.checked : true;
  }

  function setState(s) {
    state = s;
    if (!statusEl) return;
    if (s === 'idle') statusEl.textContent = 'Ask me anything about this course';
    else if (s === 'listening') statusEl.textContent = 'Listening…';
    else if (s === 'thinking') statusEl.textContent = 'Thinking…';
    else if (s === 'speaking') statusEl.textContent = 'Speaking…';
  }

  function setStatusText(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  setState('idle');

  function updateMicPulse(listening) {
    if (!micBtn) return;
    if (listening) micBtn.classList.add('course-tutor-mic--active');
    else micBtn.classList.remove('course-tutor-mic--active');
  }

  try {
    var stored = localStorage.getItem(convStorageKey);
    if (stored && /^\d+$/.test(stored)) conversationId = parseInt(stored, 10);
  } catch (e) {}

  function getCookie(name) {
    var v = null;
    if (document.cookie) {
      document.cookie.split(';').forEach(function (c) {
        var p = c.trim().split('=');
        if (p[0] === name) v = decodeURIComponent(p.slice(1).join('='));
      });
    }
    return v;
  }

  function appendMsg(role, text, isErr) {
    var d = document.createElement('div');
    d.className =
      'course-tutor-msg' +
      (isErr
        ? ' course-tutor-msg--err'
        : role === 'user'
          ? ' course-tutor-msg--user'
          : ' course-tutor-msg--assistant');
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  }

  function setWarnings(lines) {
    if (!warnEl) return;
    warnEl.textContent = lines && lines.length ? lines.join(' ') : '';
  }

  function clearAutoSubmitTimer() {
    if (autoSubmitTimer) {
      clearTimeout(autoSubmitTimer);
      autoSubmitTimer = null;
    }
  }

  function resetListenBuffers() {
    finalTranscript = '';
    interimTranscript = '';
    lastFinalConfidence = null;
    lastSpeechAt = 0;
  }

  /** Rebuild final + interim strings and last final confidence from results list. */
  function rebuildFromResults(results) {
    var finals = '';
    var interim = '';
    var lastConf = null;
    for (var i = 0; i < results.length; i++) {
      var r = results[i];
      if (!r || !r[0]) continue;
      if (r.isFinal) {
        finals += r[0].transcript;
        if (typeof r[0].confidence === 'number' && !isNaN(r[0].confidence)) {
          lastConf = r[0].confidence;
        }
      } else {
        interim += r[0].transcript;
      }
    }
    return {
      finals: finals.trim(),
      interim: interim.trim(),
      lastConf: lastConf,
    };
  }

  function refreshInputDisplay() {
    var f = finalTranscript;
    var i = interimTranscript;
    var show = (f + (f && i ? ' ' : '') + i).trim();
    inp.value = show;
  }

  function hasAnyInterimInResults(results) {
    for (var j = 0; j < results.length; j++) {
      if (results[j] && !results[j].isFinal) return true;
    }
    return false;
  }

  function scheduleAutoSubmit(gen) {
    clearAutoSubmitTimer();
    autoSubmitTimer = setTimeout(function () {
      autoSubmitTimer = null;
      trySubmitVoiceMessage(gen);
    }, SILENCE_AFTER_FINAL_MS);
  }

  function wordCount(text) {
    return text
      .trim()
      .split(/\s+/)
      .filter(function (w) {
        return w.length > 0;
      }).length;
  }

  /**
   * Auto-send path: uses accumulated final transcript only (never interim).
   */
  function trySubmitVoiceMessage(gen) {
    if (gen !== listenGeneration) return;
    if (isSending) return;

    var text = finalTranscript.trim();
    if (!text) {
      setStatusText("I didn't catch that — try again.");
      setState('idle');
      resetListenBuffers();
      inp.value = '';
      return;
    }

    if (text === lastSentVoiceText && Date.now() - lastSentVoiceAt < VOICE_DEDUPE_MS) {
      console.debug('[course-tutor-voice] skip duplicate within window');
      setState('idle');
      resetListenBuffers();
      return;
    }

    var wc = wordCount(text);
    var conf = lastFinalConfidence;

    if (typeof conf === 'number' && !isNaN(conf) && conf < CONFIDENCE_AUTO_SEND) {
      inp.value = text;
      setStatusText('I heard this — tap Send if it looks right.');
      setState('idle');
      resetListenBuffers();
      return;
    }

    if ((conf === null || conf === undefined) && wc <= 3) {
      inp.value = text;
      setStatusText('I heard this — tap Send if it looks right.');
      setState('idle');
      resetListenBuffers();
      return;
    }

    setStatusText('Got it — sending…');
    lastSentVoiceText = text;
    lastSentVoiceAt = Date.now();
    sendMessage(text, { fromVoice: true });
  }

  /** Invalidate STT callbacks/timers (call before stopRecognition when ending a session). */
  function bumpListenGeneration() {
    listenGeneration += 1;
  }

  function stopRecognition() {
    clearAutoSubmitTimer();
    try {
      if (recognition) recognition.stop();
    } catch (e) {}
    updateMicPulse(false);
    if (state === 'listening') setState('idle');
  }

  function startListening() {
    if (!SR) return;
    if (!voiceEnabled()) return;
    if (state === 'thinking' || isSending) return;

    bumpListenGeneration();
    var gen = listenGeneration;
    resetListenBuffers();
    stopTutorPlayback();
    stopRecognition();
    inp.value = '';

    recognition = new SR();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function () {
      if (gen !== listenGeneration) return;
      stopTutorPlayback();
      setState('listening');
      setStatusText('Listening…');
      updateMicPulse(true);
    };

    recognition.onresult = function (ev) {
      if (gen !== listenGeneration) return;
      var live = rebuildFromResults(ev.results);
      finalTranscript = live.finals;
      interimTranscript = live.interim;
      lastFinalConfidence = live.lastConf;
      lastSpeechAt = Date.now();
      refreshInputDisplay();

      if (hasAnyInterimInResults(ev.results)) {
        clearAutoSubmitTimer();
        setStatusText('Listening… finish your thought');
        return;
      }

      if (finalTranscript.length > 0) {
        scheduleAutoSubmit(gen);
      }
    };

    recognition.onerror = function (ev) {
      if (gen !== listenGeneration) return;
      console.warn('[course-tutor-stt]', ev && ev.error);
      clearAutoSubmitTimer();
      updateMicPulse(false);
      if (state === 'listening') setState('idle');
    };

    recognition.onend = function () {
      if (gen !== listenGeneration) return;
      updateMicPulse(false);
      recognition = null;

      var f = finalTranscript.trim();
      var inter = interimTranscript.trim();

      if (f.length > 0) {
        if (!autoSubmitTimer) {
          scheduleAutoSubmit(gen);
        }
        return;
      }

      clearAutoSubmitTimer();

      if (inter.length > 0) {
        inp.value = inter;
        setStatusText('I heard this — tap Send if it looks right.');
        setState('idle');
        resetListenBuffers();
        return;
      }

      if (state === 'listening') setState('idle');
    };

    try {
      recognition.start();
    } catch (e) {
      console.warn('[course-tutor-stt] start failed', e);
      setState('idle');
    }
  }

  /**
   * @param {string} messageText - explicit text to send (never read from DOM for voice auto path).
   * @param {{ fromVoice?: boolean }} [opts]
   */
  function sendMessage(messageText, opts) {
    opts = opts || {};
    var fromVoice = !!opts.fromVoice;

    messageText = (messageText || '').trim();
    if (!messageText || isSending) return;

    bumpListenGeneration();
    isSending = true;
    clearAutoSubmitTimer();
    stopRecognition();

    setState('thinking');
    inp.value = messageText;
    appendMsg('user', messageText, false);
    inp.value = '';
    setWarnings([]);

    fetch(msgUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || '',
      },
      body: JSON.stringify({
        message: messageText,
        conversation_id: conversationId,
        speak: !!voiceEnabled(),
      }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j, status: r.status };
        });
      })
      .then(function (res) {
        console.debug(
          '[course-tutor] response status=',
          res.status,
          'audio_b64_len=',
          res.j && res.j.audio_base64 ? res.j.audio_base64.length : 0
        );
        if (res.j && res.j.conversation_id) {
          conversationId = res.j.conversation_id;
          try {
            localStorage.setItem(convStorageKey, String(conversationId));
          } catch (e) {}
        }
        if (!res.ok || !res.j.success) {
          appendMsg('assistant', res.j && res.j.error ? res.j.error : 'Request failed.', true);
          setState('idle');
          return;
        }
        appendMsg('assistant', res.j.reply || '', false);
        setWarnings(res.j.warnings || []);
        if (res.j.audio_base64) {
          lastAudioBase64 = res.j.audio_base64;
          lastAudioMime = res.j.audio_mime_type || 'audio/mpeg';
        }

        if (res.j.audio_base64 && voiceEnabled()) {
          playFromBase64(lastAudioBase64, lastAudioMime, function () {
            if (voiceEnabled() && SR) startListening();
          });
        } else {
          setState('idle');
          if (voiceEnabled() && SR) startListening();
        }
      })
      .catch(function (err) {
        console.warn('[course-tutor] network', err);
        appendMsg('assistant', 'Network error.', true);
        setState('idle');
      })
      .finally(function () {
        isSending = false;
      });
  }

  fab.addEventListener('click', function () {
    panel.classList.remove('d-none');
    fab.setAttribute('aria-expanded', 'true');
  });
  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      panel.classList.add('d-none');
      fab.setAttribute('aria-expanded', 'false');
      bumpListenGeneration();
      stopRecognition();
      stopTutorPlayback();
      revokeActiveBlob();
      setState('idle');
    });
  }

  sendBtn.addEventListener('click', function () {
    var t = inp.value.trim();
    if (!t) return;
    sendMessage(t, { fromVoice: false });
  });

  if (replayBtn) {
    replayBtn.addEventListener('click', function () {
      if (lastAudioBase64) {
        bumpListenGeneration();
        stopRecognition();
        playFromBase64(lastAudioBase64, lastAudioMime, function () {
          if (voiceEnabled() && SR) startListening();
        });
      }
    });
  }

  if (micBtn) {
    if (!SR) {
      micBtn.disabled = true;
      micBtn.title = 'Speech input not supported in this browser';
    } else {
      micBtn.addEventListener('click', function () {
        stopTutorPlayback();
        revokeActiveBlob();
        if (state === 'listening') {
          bumpListenGeneration();
          stopRecognition();
          return;
        }
        startListening();
      });
    }
  }
})();

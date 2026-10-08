/* Resume Agent — behaviour only.
   All markup lives in the Jinja templates. This file adds:
   password show/hide, Persian form validation, double-submit protection,
   confirm-before-delete, auto-growing textareas, Ctrl/Cmd+Enter to send, and chat scroll-to-latest. */
(function () {
  'use strict';

  var ERROR_REQUIRED = 'این فیلد را پر کن.';
  var ERROR_EMAIL = 'یک ایمیل معتبر وارد کن.';

  /* ---------- Password show / hide ---------- */
  function setupPasswordToggles() {
    document.querySelectorAll('[data-toggle-password]').forEach(function (button) {
      var input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;

      button.addEventListener('click', function () {
        var shouldShow = input.type === 'password';
        input.type = shouldShow ? 'text' : 'password';
        button.textContent = shouldShow ? 'پنهان' : 'نمایش';
        button.setAttribute('aria-pressed', String(shouldShow));
      });
    });
  }

  /* ---------- Validation ---------- */
  function getErrorMessage(input) {
    if (input.validity.typeMismatch && input.type === 'email') return ERROR_EMAIL;
    if (input.validity.valueMissing || (input.required && input.value.trim() === '')) return ERROR_REQUIRED;
    return '';
  }

  function showFieldError(input, message) {
    var errorBox = input.closest('.field').querySelector('.field-error');
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.hidden = message === '';
    input.setAttribute('aria-invalid', message ? 'true' : 'false');
  }

  function setupValidation() {
    document.querySelectorAll('form[data-validate]').forEach(function (form) {
      // The browser's English pop-ups are replaced by Persian messages below.
      form.noValidate = true;

      form.addEventListener('input', function (event) {
        if (event.target.matches('input, textarea')) showFieldError(event.target, '');
      });

      form.addEventListener('submit', function (event) {
        var firstInvalid = null;

        form.querySelectorAll('input, textarea').forEach(function (input) {
          var message = getErrorMessage(input);
          showFieldError(input, message);
          if (message && !firstInvalid) firstInvalid = input;
        });

        if (firstInvalid) {
          event.preventDefault();
          firstInvalid.focus();
        }
      });
    });
  }

  /* ---------- Confirm before destructive actions ---------- */
  // Must be registered BEFORE setupSubmitLock so a cancelled confirm
  // does not lock the form.
  function setupConfirm() {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
      });
    });
  }

  /* ---------- Double-submit protection ---------- */
  function setupSubmitLock() {
    document.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (event.defaultPrevented) return;      // validation failed
        if (form.dataset.submitting === 'true') {
          event.preventDefault();
          return;
        }
        form.dataset.submitting = 'true';
        var submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.setAttribute('aria-busy', 'true');
      });
    });

    // Coming back with the browser's back button should unlock the form.
    window.addEventListener('pageshow', function (event) {
      if (!event.persisted) return;
      document.querySelectorAll('form').forEach(function (form) {
        form.dataset.submitting = '';
        var submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.removeAttribute('aria-busy');
      });
    });
  }

  /* ---------- Textareas ---------- */
  function growTextarea(textarea) {
    textarea.style.height = 'auto';
    var borders = textarea.offsetHeight - textarea.clientHeight;
    textarea.style.height = textarea.scrollHeight + borders + 'px';
  }

  function setupTextareas() {
    document.querySelectorAll('textarea[data-autosize]').forEach(function (textarea) {
      textarea.addEventListener('input', function () { growTextarea(textarea); });
      growTextarea(textarea);
    });

    document.querySelectorAll('textarea[data-submit-shortcut]').forEach(function (textarea) {
      textarea.addEventListener('keydown', function (event) {
        var isShortcut = event.key === 'Enter' && (event.ctrlKey || event.metaKey);
        if (isShortcut && textarea.form) {
          event.preventDefault();
          textarea.form.requestSubmit();
        }
      });
    });
  }

  /* ---------- Chat: show the latest message ---------- */
  function setupChat() {
    var chat = document.getElementById('chat');
    if (!chat) return;

    window.scrollTo(0, document.documentElement.scrollHeight);

    var input = document.querySelector('.composer textarea');
    if (input) input.focus({ preventScroll: true });
  }

  setupPasswordToggles();
  setupValidation();
  setupConfirm();
  setupSubmitLock();
  setupTextareas();
  setupChat();
})();

/*!
 * HelpFlow embeddable widget loader (spec E7 Req 1).
 *
 *   <script src="https://widget.helpflow.example/embed.js" data-key="WIDGET_KEY"></script>
 *
 * Injects one iframe pointing at the built widget app; the widget key +
 * theme flow in as query params. `tenant_id` is NEVER trusted from this
 * script — it's resolved server-side from the key (invariant #2). The
 * iframe is resized between a small "bubble" footprint and the full chat
 * panel footprint via postMessage, since the widget's own floating UI lives
 * INSIDE the iframe (host-CSS isolation: nothing here reaches into the
 * host page's styles, and nothing from the host page reaches in).
 */
(function () {
  'use strict';

  function currentScript() {
    if (document.currentScript) return document.currentScript;
    var scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  }

  var script = currentScript();
  var key = script.getAttribute('data-key');
  if (!key) {
    console.warn('[HelpFlow] embed.js: missing required data-key attribute.');
    return;
  }
  var theme = script.getAttribute('data-theme') || 'auto'; // light | dark | auto

  var scriptUrl = new URL(script.src, window.location.href);
  var baseUrl = scriptUrl.href.slice(0, scriptUrl.href.lastIndexOf('/'));
  var widgetOrigin = scriptUrl.origin;

  var iframeSrc =
    baseUrl +
    '/index.html?key=' +
    encodeURIComponent(key) +
    '&theme=' +
    encodeURIComponent(theme);

  var iframe = document.createElement('iframe');
  iframe.src = iframeSrc;
  iframe.title = 'Chat widget';
  iframe.setAttribute('scrolling', 'no');
  iframe.setAttribute('allow', 'clipboard-write');
  iframe.style.cssText =
    'position:fixed;bottom:0;right:0;border:0;background:transparent;overflow:hidden;' +
    'z-index:2147483000;max-width:100vw;max-height:100dvh;transition:width 0.2s ease,height 0.2s ease;';

  var CLOSED_SIZE = { width: '88px', height: '88px' };
  var OPEN_DESKTOP_SIZE = { width: '420px', height: '700px' };

  function isMobile() {
    return window.innerWidth < 640;
  }

  function applySize(size) {
    iframe.style.width = size.width;
    iframe.style.height = size.height;
  }

  // The widget's own React tree always fills 100% of the iframe's box (no
  // internal Tailwind `sm:` breakpoint — the iframe is at most 420px wide
  // even "open on desktop", so a 640px rule could never fire from inside
  // it). Shaping the box — rounded floating card vs. mobile full-bleed — is
  // this loader's job, applied to the iframe element itself.
  function sizeClosed() {
    applySize(CLOSED_SIZE);
    iframe.style.borderRadius = '0';
    iframe.style.boxShadow = 'none';
  }

  function sizeOpen() {
    if (isMobile()) {
      applySize({ width: '100vw', height: '100dvh' });
      iframe.style.borderRadius = '0';
    } else {
      applySize(OPEN_DESKTOP_SIZE);
      iframe.style.borderRadius = '24px';
    }
    iframe.style.boxShadow = '0 20px 50px -12px rgba(15, 23, 42, 0.35)';
  }

  var lastOpen = false;
  sizeClosed();

  window.addEventListener('resize', function () {
    if (lastOpen) sizeOpen();
  });

  window.addEventListener('message', function (event) {
    if (event.origin !== widgetOrigin) return;
    if (event.source !== iframe.contentWindow) return;
    var data = event.data || {};
    if (data.type === 'hf:widget-state') {
      lastOpen = !!data.open;
      if (lastOpen) sizeOpen();
      else sizeClosed();
    }
  });

  function mount() {
    document.body.appendChild(iframe);
  }

  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();

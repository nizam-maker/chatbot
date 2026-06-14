/**
 * @chatplatform/widget
 * Embeddable chat bubble for ChatPlatform
 *
 * Usage (script tag):
 *   <script src="https://your-railway-url/widget.js"
 *     data-tenant="laman_auto"
 *     data-key="pk_la_xxxx"
 *     defer>
 *   </script>
 *
 * Usage (npm / ES module):
 *   import { initWidget } from '@chatplatform/widget';
 *   initWidget({ tenant: 'laman_auto', key: 'pk_la_xxxx' });
 */

'use strict';

var DEFAULT_BASE = 'https://web-production-f61d6.up.railway.app';

/**
 * Inject the chat widget iframe into the page.
 *
 * @param {Object} options
 * @param {string} options.tenant   - Tenant slug (e.g. 'laman_auto')
 * @param {string} options.key      - Public API key
 * @param {string} [options.base]   - Override platform base URL
 * @param {string} [options.position] - 'bottom-right' (default) | 'bottom-left'
 */
function initWidget(options) {
  var tenant   = options.tenant   || '';
  var key      = options.key      || '';
  var base     = options.base     || DEFAULT_BASE;
  var position = options.position || 'bottom-right';

  if (!tenant) {
    console.warn('[ChatPlatform] initWidget: tenant is required');
    return;
  }

  // Prevent duplicate mount
  if (document.getElementById('chatplatform-widget')) return;

  var iframe      = document.createElement('iframe');
  iframe.id       = 'chatplatform-widget';
  iframe.allowTransparency = true;
  iframe.setAttribute('allowtransparency', 'true');
  iframe.setAttribute('frameborder', '0');
  iframe.src      = base + '/embed/' + tenant + '?key=' + key + '&tenant=' + tenant;
  iframe.title    = 'Chat widget';
  iframe.setAttribute('allow', 'microphone');

  var right  = position === 'bottom-left' ? 'auto' : '0';
  var left   = position === 'bottom-left' ? '0'    : 'auto';

  iframe.style.cssText = [
    'position:fixed',
    'bottom:0',
    'right:'  + right,
    'left:'   + left,
    'width:420px',
    'height:600px',
    'border:none',
    'z-index:2147483647',
    'background:transparent',
    'background-color:transparent',
    'pointer-events:all'
  ].join(';');

  document.body.appendChild(iframe);
  return iframe;
}

/**
 * Remove the widget from the page.
 */
function destroyWidget() {
  var el = document.getElementById('chatplatform-widget');
  if (el) el.remove();
}

module.exports = { initWidget: initWidget, destroyWidget: destroyWidget };
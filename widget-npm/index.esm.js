/**
 * @chatplatform/widget — ES Module build
 * For React, Vue, Next.js, Vite projects
 *
 * Usage:
 *   import { initWidget } from '@chatplatform/widget';
 *
 *   // In React useEffect:
 *   useEffect(() => {
 *     initWidget({ tenant: 'laman_auto', key: 'pk_la_xxxx' });
 *     return () => destroyWidget();
 *   }, []);
 */

const DEFAULT_BASE = 'https://web-production-f61d6.up.railway.app';

export function initWidget({ tenant, key, base = DEFAULT_BASE, position = 'bottom-right' } = {}) {
  if (!tenant) {
    console.warn('[ChatPlatform] initWidget: tenant is required');
    return;
  }

  if (document.getElementById('chatplatform-widget')) return;

  const iframe = document.createElement('iframe');
  iframe.id    = 'chatplatform-widget';
  iframe.allowTransparency = true;
  iframe.setAttribute('allowtransparency', 'true');
  iframe.setAttribute('frameborder', '0');
  iframe.src   = `${base}/embed/${tenant}?key=${key}&tenant=${tenant}`;
  iframe.title = 'Chat widget';
  iframe.setAttribute('allow', 'microphone');

  const right = position === 'bottom-left' ? 'auto' : '0';
  const left  = position === 'bottom-left' ? '0'    : 'auto';

  iframe.style.cssText = [
    'position:fixed', 'bottom:0',
    `right:${right}`, `left:${left}`,
    'width:420px', 'height:600px',
    'border:none', 'z-index:2147483647',
    'background:transparent', 'background-color:transparent',
    'pointer-events:all'
  ].join(';');

  document.body.appendChild(iframe);
  return iframe;
}

export function destroyWidget() {
  document.getElementById('chatplatform-widget')?.remove();
}
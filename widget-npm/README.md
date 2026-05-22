# @chatplatform/widget

Embeddable AI chat bubble for ChatPlatform. Adds a floating chat widget to any website in one line.

## Installation

### Option 1 — Script tag (no install needed)

Paste before `</body>` on any webpage:

```html
<script
  src="https://web-production-f61d6.up.railway.app/widget.js"
  data-tenant="laman_auto"
  data-key="pk_la_your_public_key"
  defer>
</script>
```

### Option 2 — npm

```bash
npm install @chatplatform/widget
```

## Usage

### Plain JavaScript
```js
import { initWidget } from '@chatplatform/widget';

initWidget({
  tenant: 'laman_auto',
  key:    'pk_la_your_public_key',
});
```

### React
```jsx
import { useEffect } from 'react';
import { initWidget, destroyWidget } from '@chatplatform/widget';

export default function App() {
  useEffect(() => {
    initWidget({
      tenant: 'laman_auto',
      key:    'pk_la_your_public_key',
    });
    return () => destroyWidget();
  }, []);

  return <div>Your website content</div>;
}
```

### Vue
```js
import { initWidget, destroyWidget } from '@chatplatform/widget';

export default {
  mounted() {
    initWidget({ tenant: 'laman_auto', key: 'pk_la_xxx' });
  },
  beforeUnmount() {
    destroyWidget();
  }
}
```

### Next.js
```jsx
'use client';
import { useEffect } from 'react';
import { initWidget, destroyWidget } from '@chatplatform/widget';

export default function ChatWidget() {
  useEffect(() => {
    initWidget({ tenant: 'laman_auto', key: 'pk_la_xxx' });
    return () => destroyWidget();
  }, []);
  return null;
}
```

## Options

| Option | Type | Default | Description |
|---|---|---|---|
| `tenant` | string | required | Your tenant slug |
| `key` | string | required | Your public API key |
| `base` | string | Railway URL | Override platform URL |
| `position` | string | `bottom-right` | `bottom-right` or `bottom-left` |

## Get your keys

Log in to your ChatPlatform dashboard → Tenants → API keys tab.
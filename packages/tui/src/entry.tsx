import { render } from './vendor/ink-renderer/index.js';
import { App } from './app.js';
import type { TUIOptions } from './types.js';

export async function renderTUI(options: TUIOptions): Promise<void> {
  const instance = await render(<App options={options} />);
  await instance.waitUntilExit();
}

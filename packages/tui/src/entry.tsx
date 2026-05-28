import { useState } from 'react';
import { render } from './vendor/ink-renderer/index.js';
import { App } from './app.js';
import type { TUIOptions } from './types.js';
import { SetupScreen } from './SetupScreen.js';
import { needsJarvisOnboarding, resolveJarvisConfigDefaults, type JarvisConfig } from '@jarvis/shared';

function BootApp({ options }: { options: TUIOptions }) {
  const [runtimeOptions, setRuntimeOptions] = useState<TUIOptions>(options);
  const [setupDone, setSetupDone] = useState<boolean>(() => {
    if (options.forceOnboarding) return false;
    return !needsJarvisOnboarding();
  });

  if (!setupDone) {
    return (
      <SetupScreen
        onComplete={(config: JarvisConfig) => {
          const resolved = resolveJarvisConfigDefaults(config);
          setRuntimeOptions((prev) => ({
            ...prev,
            model: resolved.model,
            apiKey: resolved.api_key,
            baseURL: resolved.base_url,
            reasoningEffort: resolved.reasoning_effort,
            maxTurns: resolved.max_turns,
            systemPrompt: resolved.system_prompt,
            forceOnboarding: false,
          }));
          setSetupDone(true);
        }}
      />
    );
  }

  return <App options={runtimeOptions} />;
}

export async function renderTUI(options: TUIOptions): Promise<void> {
  const instance = await render(<BootApp options={options} />);
  await instance.waitUntilExit();
}

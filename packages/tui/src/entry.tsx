import { useState } from 'react';
import { render } from './vendor/ink-renderer/index.js';
import { App } from './app.js';
import type { TUIOptions } from './types.js';
import { SetupScreen } from './SetupScreen.js';
import { needsJarvisOnboarding, resolveJarvisConfigDefaults, type JarvisConfig } from '@jarvis/shared';
import { findModel } from '@jarvis/agent';

function resolveProviderForModel(modelName: string, config: JarvisConfig): { api_key?: string; base_url?: string } {
  const catalogEntry = findModel(modelName);
  const providerName = catalogEntry?.provider;
  if (providerName && config.providers?.[providerName]) {
    const p = config.providers[providerName];
    return {
      api_key: p.api_key ?? config.api_key ?? process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'],
      base_url: p.base_url ?? config.base_url ?? process.env['JARVIS_LLM_BASE_URL'] ?? process.env['JARVIS_BASE_URL'],
    };
  }
  return {
    api_key: config.api_key ?? process.env['JARVIS_LLM_API_KEY'] ?? process.env['OPENAI_API_KEY'],
    base_url: config.base_url ?? process.env['JARVIS_LLM_BASE_URL'] ?? process.env['JARVIS_BASE_URL'],
  };
}

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
          const activeModel = resolved.active_model ?? resolved.model ?? 'deepseek-chat';
          const provider = resolveProviderForModel(activeModel, config);
          setRuntimeOptions((prev) => ({
            ...prev,
            model: activeModel,
            apiKey: provider.api_key ?? resolved.api_key,
            baseURL: provider.base_url ?? resolved.base_url,
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

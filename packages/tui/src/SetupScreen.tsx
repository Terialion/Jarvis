import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Box, Text, useInput } from './vendor/ink-renderer/index.js';
import { PromptInput } from './vendor/ui/PromptInput.js';
import { ArcReactorLogo } from './vendor/ui/WelcomeScreen.js';
import {
  JARVIS_REASONING_EFFORTS,
  loadJarvisConfig,
  resolveJarvisConfigDefaults,
  saveJarvisConfig,
  getJarvisConfigPath,
  type JarvisConfig,
} from '@jarvis/shared';

type SetupScreenProps = {
  onComplete: (config: JarvisConfig) => void;
};

type FieldKey =
  | 'model'
  | 'base_url'
  | 'api_key'
  | 'reasoning_effort'
  | 'max_turns'
  | 'permission_mode'
  | 'output_style'
  | 'system_prompt';

type SetupField = {
  key: FieldKey;
  label: string;
  section: 'Connection' | 'Behavior';
  help: string;
};

const FIELDS: SetupField[] = [
  { key: 'model', label: 'Model', section: 'Connection', help: 'Default model slug for new Jarvis sessions.' },
  { key: 'base_url', label: 'Base URL', section: 'Connection', help: 'API endpoint used for model requests.' },
  { key: 'api_key', label: 'API key', section: 'Connection', help: 'Credential stored in your user config.' },
  { key: 'reasoning_effort', label: 'Reasoning effort', section: 'Behavior', help: 'auto, minimal, low, medium, high, xhigh, or max.' },
  { key: 'max_turns', label: 'Max turns', section: 'Behavior', help: 'Default turn budget for each run.' },
  { key: 'permission_mode', label: 'Permission mode', section: 'Behavior', help: 'workspace_write, accept_edits, or bypass.' },
  { key: 'output_style', label: 'Output style', section: 'Behavior', help: 'default, concise, or verbose.' },
  { key: 'system_prompt', label: 'Custom global instruction', section: 'Behavior', help: 'Optional. Press Enter to skip and keep the built-in behavior.' },
];

function maskSecret(value?: string): string {
  return value ? `${value.slice(0, 4)}...${value.slice(-4)}` : '(not set)';
}

function normalizeConfigValue(key: FieldKey, value: string): string {
  if (key === 'system_prompt') return value;
  return value.trim();
}

function validateField(key: FieldKey, value: string): string | null {
  if (key === 'system_prompt') return null;
  if (!value) return 'This value is required.';
  if (key === 'max_turns') {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? null : 'Max turns must be a positive integer.';
  }
  if (key === 'permission_mode') {
    return ['workspace_write', 'accept_edits', 'bypass'].includes(value)
      ? null
      : 'Choose one of: workspace_write, accept_edits, bypass';
  }
  if (key === 'reasoning_effort') {
    return JARVIS_REASONING_EFFORTS.includes(value as NonNullable<JarvisConfig['reasoning_effort']>)
      ? null
      : `Choose one of: ${JARVIS_REASONING_EFFORTS.join(', ')}`;
  }
  if (key === 'output_style') {
    return ['default', 'concise', 'verbose'].includes(value)
      ? null
      : 'Choose one of: default, concise, verbose';
  }
  return null;
}

export function SetupScreen({ onComplete }: SetupScreenProps): React.ReactNode {
  const existing = useMemo(() => loadJarvisConfig(), []);
  const defaults = useMemo(() => resolveJarvisConfigDefaults(existing), [existing]);
  const [draft, setDraft] = useState<Record<FieldKey, string>>({
    model: defaults.active_model ?? defaults.model ?? '',
    base_url: defaults.base_url,
    api_key: defaults.api_key ?? '',
    reasoning_effort: defaults.reasoning_effort,
    max_turns: String(defaults.max_turns),
    permission_mode: defaults.permission_mode,
    output_style: defaults.output_style,
    system_prompt: defaults.system_prompt ?? '',
  });
  const [index, setIndex] = useState(0);
  const [input, setInput] = useState(draft[FIELDS[0]!.key]);
  const [error, setError] = useState<string | null>(null);

  const currentField = index < FIELDS.length ? FIELDS[index]! : null;
  const inReview = currentField === null;
  const configPath = getJarvisConfigPath();

  useEffect(() => {
    if (!currentField) {
      setInput('y');
      return;
    }
    setInput(draft[currentField.key] ?? '');
    setError(null);
  }, [currentField, draft]);

  useInput((value, key) => {
    if (key.escape) {
      if (inReview) {
        setIndex(FIELDS.length - 1);
        return;
      }
      if (index > 0) {
        setIndex((prev) => Math.max(0, prev - 1));
      }
      return;
    }
    if (!inReview) return;
    if (key.return) return;
    if (value.toLowerCase() === 'n') {
      setIndex(FIELDS.length - 1);
    }
  });

  const submitField = (rawValue: string) => {
    if (!currentField) {
      const answer = rawValue.trim().toLowerCase();
      if (!answer || answer === 'y' || answer === 'yes') {
        const nextConfig: JarvisConfig = {
          ...existing,
          model: draft.model,
          base_url: draft.base_url,
          api_key: draft.api_key,
          reasoning_effort: draft.reasoning_effort as JarvisConfig['reasoning_effort'],
          max_turns: Number.parseInt(draft.max_turns, 10),
          permission_mode: draft.permission_mode as JarvisConfig['permission_mode'],
          output_style: draft.output_style as JarvisConfig['output_style'],
          system_prompt: draft.system_prompt.trim() || undefined,
        };
        saveJarvisConfig(nextConfig);
        onComplete(nextConfig);
        return;
      }
      if (answer === 'n' || answer === 'no') {
        setIndex(FIELDS.length - 1);
        return;
      }
      setError('Press Enter to save, or type n to go back.');
      return;
    }

    const normalized = normalizeConfigValue(currentField.key, rawValue);
    const validationError = validateField(currentField.key, normalized);
    if (validationError) {
      setError(validationError);
      return;
    }

    setDraft((prev) => ({ ...prev, [currentField.key]: normalized }));
    setIndex((prev) => prev + 1);
  };

  return (
    <Box flexDirection="column" paddingX={1} paddingY={1}>
      <Box flexDirection="row" gap={2} alignItems="center">
        <ArcReactorLogo color="#00BFFF" />
        <Box flexDirection="column">
          <Text bold color="#00BFFF">Jarvis setup</Text>
          <Text dimColor>Configure API access and default behavior</Text>
          <Text dimColor>{configPath}</Text>
        </Box>
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <Text dimColor>This setup creates your user config inside the TUI, so Jarvis can start without relying on project .env files.</Text>
        <Text dimColor>Press Enter to accept a value. Press Esc to go back one step.</Text>
      </Box>

      {!inReview && currentField && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold color="#00BFFF">{currentField.section}</Text>
          <Text dimColor>{currentField.help}</Text>
          <Box marginTop={1}>
            <PromptInput
              value={input}
              onChange={setInput}
              onSubmit={submitField}
              allowEmptySubmit={currentField.key === 'system_prompt'}
              prefix={`${currentField.label}:`}
              prefixColor="cyan"
              placeholder={currentField.key === 'system_prompt' ? 'Press Enter to skip' : (draft[currentField.key] ?? '')}
            />
          </Box>
        </Box>
      )}

      {inReview && (
        <Box flexDirection="column" marginTop={1}>
          <Text bold color="#00BFFF">Review</Text>
          <Text dimColor>The following user config will be saved:</Text>
          <Box flexDirection="column" marginTop={1} marginLeft={2}>
            <Text>{`model           ${draft.model}`}</Text>
            <Text>{`base_url        ${draft.base_url}`}</Text>
            <Text>{`api_key         ${maskSecret(draft.api_key)}`}</Text>
            <Text>{`reasoning_effort ${draft.reasoning_effort}`}</Text>
            <Text>{`max_turns       ${draft.max_turns}`}</Text>
            <Text>{`permission_mode ${draft.permission_mode}`}</Text>
            <Text>{`output_style    ${draft.output_style}`}</Text>
            <Text>{`system_prompt   ${draft.system_prompt.trim() ? '(configured)' : '(not set)'}`}</Text>
          </Box>
          <Box marginTop={1}>
            <PromptInput
              value={input}
              onChange={setInput}
              onSubmit={submitField}
              prefix="Save this configuration now?"
              prefixColor="cyan"
              placeholder="Press Enter to save, or type n to edit"
            />
          </Box>
        </Box>
      )}

      {error && (
        <Box marginTop={1}>
          <Text color="red">{error}</Text>
        </Box>
      )}
    </Box>
  );
}

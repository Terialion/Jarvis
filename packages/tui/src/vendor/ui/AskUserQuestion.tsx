import { Box, TerminalSizeContext, Text, useInput } from '../ink-renderer/index.js';
import type React from 'react';
import { useCallback, useContext, useState } from 'react';
import type { AskQuestionDef } from '@jarvis/tools';

export type AskUserQuestionProps = {
  questions: AskQuestionDef[];
  onSubmit: (answers: Record<string, string>) => void;
  onCancel: () => void;
};

/** Formats a multiSelect answer as comma-separated labels. */
function formatMultiAnswer(labels: string[]): string {
  return labels.join(', ');
}

// ============================================================================
// Shared header component (matches PermissionRequest style)
// ============================================================================

function QuestionHeader({ label, width }: { label: string; width: number }) {
  const text = ` ${label} `;
  const textLen = label.length + 2;
  const leftLen = 3;
  const rightLen = Math.max(0, width - leftLen - textLen);
  return (
    <Text>
      <Text dimColor>{'─'.repeat(leftLen)}</Text>
      <Text bold color="cyan">
        {text}
      </Text>
      <Text dimColor>{'─'.repeat(rightLen)}</Text>
    </Text>
  );
}

function HorizontalRule({ width }: { width: number }) {
  return <Text dimColor>{'─'.repeat(width)}</Text>;
}

// ============================================================================
// Single question block (inline options, no sub-box)
// ============================================================================

function QuestionBlock({
  question,
  qIndex,
  total,
  onSubmit,
  terminalWidth,
}: {
  question: AskQuestionDef;
  qIndex: number;
  total: number;
  onSubmit: (answer: string) => void;
  terminalWidth: number;
}) {
  const [focusIndex, setFocusIndex] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const options = question.options;
  const isMulti = question.multiSelect ?? false;

  const confirm = useCallback(() => {
    if (isMulti) {
      const labels = [...selected].sort().map((i) => options[i]!.label);
      if (labels.length === 0) return; // require at least one selection
      onSubmit(formatMultiAnswer(labels));
    } else {
      onSubmit(options[focusIndex]!.label);
    }
  }, [isMulti, selected, focusIndex, options, onSubmit]);

  useInput((input, key) => {
    if (key.upArrow || input === 'k') {
      setFocusIndex((prev) => (prev - 1 + options.length) % options.length);
    } else if (key.downArrow || input === 'j') {
      setFocusIndex((prev) => (prev + 1) % options.length);
    } else if (key.return) {
      confirm();
    } else if (input === ' ') {
      if (isMulti) {
        setSelected((prev) => {
          const next = new Set(prev);
          if (next.has(focusIndex)) next.delete(focusIndex);
          else next.add(focusIndex);
          return next;
        });
      }
    } else if (input === 'y' && !isMulti) {
      // Quick-select first option
      onSubmit(options[0]!.label);
    } else if (input === 'n' && !isMulti && options.length >= 2) {
      // Quick-select last option (usually "No" / cancel)
      onSubmit(options[options.length - 1]!.label);
    } else if (input >= '1' && input <= '9' && !isMulti) {
      const idx = parseInt(input, 10) - 1;
      if (idx < options.length) {
        onSubmit(options[idx]!.label);
      }
    }
  });

  const headerText = question.header
    ? `${question.header} (${qIndex + 1}/${total})`
    : `Q${qIndex + 1}/${total}`;

  return (
    <Box flexDirection="column">
      <QuestionHeader label={headerText} width={terminalWidth} />

      <Box marginTop={1} marginLeft={2}>
        <Text>{question.question}</Text>
      </Box>

      <Box marginTop={1}>
        <HorizontalRule width={terminalWidth} />
      </Box>

      <Box marginTop={1} flexDirection="column">
        {options.map((opt, i) => {
          const isFocused = i === focusIndex;
          const isSelected = isMulti && selected.has(i);

          if (isMulti) {
            const marker = isSelected ? '◉' : '○';
            return (
              <Box key={i}>
                <Text color={isFocused ? 'cyan' : undefined}>
                  {isFocused ? '❯' : ' '} {marker}{' '}
                </Text>
                <Text color={isFocused ? 'cyan' : undefined} bold={isFocused}>
                  {i + 1}. {opt.label}
                </Text>
                {opt.description ? (
                  <Text dimColor={!isFocused}> — {opt.description}</Text>
                ) : null}
              </Box>
            );
          }

          return (
            <Box key={i}>
              <Text color={isFocused ? 'cyan' : undefined}>
                {isFocused ? '❯' : ' '}{' '}
              </Text>
              <Text color={isFocused ? 'cyan' : undefined} bold={isFocused}>
                {i + 1}. {opt.label}
              </Text>
              {opt.description ? (
                <Text dimColor={!isFocused}> — {opt.description}</Text>
              ) : null}
            </Box>
          );
        })}
      </Box>

      <Box marginTop={1}>
        {isMulti ? (
          <Text dimColor>
            Space to toggle · Enter to confirm ({selected.size} selected) · Esc to cancel
          </Text>
        ) : (
          <Text dimColor>Enter to confirm · Esc to cancel</Text>
        )}
      </Box>
    </Box>
  );
}

// ============================================================================
// AskUserQuestion — multi-question flow with PermissionRequest-style UI
// ============================================================================

export function AskUserQuestion({
  questions,
  onSubmit,
  onCancel,
}: AskUserQuestionProps): React.ReactNode {
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const terminalSize = useContext(TerminalSizeContext);
  const terminalWidth = Math.min((terminalSize?.columns ?? 80) - 2, 80);

  const handleAnswer = useCallback(
    (answer: string) => {
      const nextAnswers = { ...answers, [questions[currentQ]!.question]: answer };
      if (currentQ + 1 >= questions.length) {
        onSubmit(nextAnswers);
      } else {
        setAnswers(nextAnswers);
        setCurrentQ((q) => q + 1);
      }
    },
    [answers, currentQ, questions, onSubmit],
  );

  // Escape cancels the entire flow
  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const question = questions[currentQ]!;

  return (
    <Box flexDirection="column" marginLeft={2}>
      <QuestionBlock
        question={question}
        qIndex={currentQ}
        total={questions.length}
        onSubmit={handleAnswer}
        terminalWidth={terminalWidth}
      />
    </Box>
  );
}

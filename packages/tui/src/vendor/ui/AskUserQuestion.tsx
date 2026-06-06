import { Box, Text, useInput } from '../ink-renderer/index.js';
import type React from 'react';
import { useCallback, useState } from 'react';
import type { AskQuestionDef } from '@jarvis/tools';

export type AskUserQuestionProps = {
  questions: AskQuestionDef[];
  onSubmit: (answers: Record<string, string>) => void;
  onCancel: () => void;
};

function formatMultiAnswer(labels: string[]): string {
  return labels.join(', ');
}

function QuestionBlock({
  question,
  qIndex,
  total,
  onSubmit,
}: {
  question: AskQuestionDef;
  qIndex: number;
  total: number;
  onSubmit: (answer: string) => void;
}) {
  const [focusIndex, setFocusIndex] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const options = question.options;
  const isMulti = question.multiSelect ?? false;

  const confirm = useCallback(() => {
    if (isMulti) {
      const labels = [...selected].sort().map((i) => options[i]!.label);
      if (labels.length === 0) return;
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
      onSubmit(options[0]!.label);
    } else if (input === 'n' && !isMulti && options.length >= 2) {
      onSubmit(options[options.length - 1]!.label);
    } else if (input >= '1' && input <= '9' && !isMulti) {
      const idx = parseInt(input, 10) - 1;
      if (idx < options.length) {
        onSubmit(options[idx]!.label);
      }
    }
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Compact header: question on one line */}
      <Box>
        <Text bold color="cyan">{question.header ?? 'Question'}</Text>
        {total > 1 && <Text dimColor> ({qIndex + 1}/{total})</Text>}
        <Text dimColor> — </Text>
        <Text>{question.question}</Text>
      </Box>

      {/* Options */}
      <Box marginTop={1} flexDirection="column">
        {options.map((opt, i) => {
          const isFocused = i === focusIndex;
          const isSelected = isMulti && selected.has(i);

          if (isMulti) {
            const marker = isSelected ? '[x]' : '[ ]';
            return (
              <Box key={i}>
                <Text color={isFocused ? 'cyan' : undefined}>
                  {isFocused ? '❯' : ' '} {marker}{' '}
                </Text>
                <Text color={isFocused ? 'cyan' : undefined} bold={isFocused}>
                  {i + 1}. {opt.label}
                </Text>
                {opt.description ? (
                  <Text dimColor={!isFocused}> - {opt.description}</Text>
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
                <Text dimColor={!isFocused}> - {opt.description}</Text>
              ) : null}
            </Box>
          );
        })}
      </Box>

      {/* Hint */}
      <Box marginTop={0}>
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

export function AskUserQuestion({
  questions,
  onSubmit,
  onCancel,
}: AskUserQuestionProps): React.ReactNode {
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});

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

  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const question = questions[currentQ]!;

  return (
    <QuestionBlock
      question={question}
      qIndex={currentQ}
      total={questions.length}
      onSubmit={handleAnswer}
    />
  );
}

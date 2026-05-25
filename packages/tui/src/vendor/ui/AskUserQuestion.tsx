import { Box, Text, useInput } from '../ink-renderer/index.js';
import type React from 'react';
import { useCallback, useState } from 'react';
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

/** Renders a single question with selectable options. */
function QuestionBlock({
  question,
  qIndex,
  onSubmit,
}: {
  question: AskQuestionDef;
  qIndex: number;
  onSubmit: (answer: string) => void;
}) {
  const [focusIndex, setFocusIndex] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const options = question.options;
  const isMulti = question.multiSelect ?? false;

  const confirm = useCallback(() => {
    if (isMulti) {
      const labels = [...selected].map((i) => options[i]!.label);
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
      if (isMulti) {
        confirm();
      } else {
        onSubmit(options[focusIndex]!.label);
      }
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
    }
  });

  const label = question.header ? `[${question.header}]` : `Q${qIndex + 1}`;

  return (
    <Box flexDirection="column" marginTop={qIndex > 0 ? 1 : 0}>
      <Box>
        <Text bold color="cyan">
          {label}
        </Text>
        <Text> {question.question}</Text>
      </Box>
      <Box marginTop={1} flexDirection="column">
        {options.map((opt, i) => {
          const isFocused = i === focusIndex;
          const isSelected = isMulti && selected.has(i);
          const marker = isMulti
            ? isSelected
              ? '◉'
              : '○'
            : isFocused
              ? '❯'
              : ' ';
          return (
            <Box key={i}>
              <Text color={isFocused ? 'cyan' : undefined}>
                {marker}{' '}
              </Text>
              <Text color={isFocused ? 'cyan' : undefined} bold={isFocused}>
                {opt.label}
              </Text>
              {opt.description ? (
                <Text dimColor> — {opt.description}</Text>
              ) : null}
            </Box>
          );
        })}
      </Box>
      {isMulti && (
        <Box marginTop={1}>
          <Text dimColor>
            Space to toggle · Enter to confirm ({selected.size} selected)
          </Text>
        </Box>
      )}
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

  // Escape cancels the entire flow
  useInput((_input, key) => {
    if (key.escape) {
      onCancel();
    }
  });

  const question = questions[currentQ]!;

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text dimColor>┌</Text>
        <Text bold color="#DA7756">
          {' AskUserQuestion '}
        </Text>
        <Text dimColor>
          ({currentQ + 1}/{questions.length})
        </Text>
        <Text dimColor> Esc to cancel</Text>
      </Box>
      <Box marginLeft={2} flexDirection="column">
        <QuestionBlock
          question={question}
          qIndex={currentQ}
          onSubmit={handleAnswer}
        />
      </Box>
    </Box>
  );
}

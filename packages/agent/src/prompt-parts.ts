export type PromptPartCategory = 'instruction' | 'context' | 'history' | 'intent';

export type PromptPartBucket =
  | 'system'
  | 'project'
  | 'settings'
  | 'skills'
  | 'memory'
  | 'summary'
  | 'history'
  | 'intent';

export interface PromptPartMeta {
  category: PromptPartCategory;
  bucket: PromptPartBucket;
  id: string;
}

export type PromptPartRole = 'system' | 'user' | 'assistant' | 'tool' | 'developer';

export interface PromptPart {
  role: PromptPartRole;
  content: string;
  tool_call_id?: string;
  tool_calls?: Array<{
    id: string;
    type: 'function';
    function: { name: string; arguments: string };
  }>;
  promptPart: PromptPartMeta;
}

export interface PromptPartMessageShape {
  promptPart?: PromptPartMeta;
}

import { SkillRegistry, SkillExecutor } from '@jarvis/skills';

const registry = new SkillRegistry();
const skills = registry.discover({
  builtinDir: 'D:/agent/Jarvis/skills',
  projectDir: 'D:/agent/Jarvis/.jarvis/skills',
});

console.log('=== Skills loaded:', skills.length, '===\n');

const executor = new SkillExecutor(registry);

// Test queries with expected skill matches
const tests = [
  { q: '帮我搜索AI新闻', expect: 'search' },
  { q: '生成一份年终总结PPT', expect: 'pptx' },
  { q: 'review the code in packages/agent', expect: 'code' },
  { q: '把这个网页总结一下', expect: 'summar' },
  { q: '今天天气怎么样', expect: 'weather' },
  { q: '帮我commit这些改动', expect: 'commit' },
  { q: 'Gongfeng lint and comment this PR', expect: 'gongfeng' },
  { q: '帮我设计一个画布', expect: 'canvas' },
  { q: '帮我给小红书写个营销文案', expect: 'xiaohongshu' },
  { q: '读一下这篇论文', expect: 'arxiv' },
];

for (const { q, expect } of tests) {
  const result = executor.execute({ taskText: q, maxSkills: 3 });
  const names = result.included.map((s) => s.name).join(', ') || '(none)';
  const hit = result.included.some((s) => s.name.toLowerCase().includes(expect));
  const mark = hit ? '✓' : '✗';
  console.log(`${mark} "${q}"`);
  console.log(`  → ${names}`);
  if (result.instructionBlock) {
    // Show first 120 chars of the instruction block
    const preview = result.instructionBlock.slice(0, 120).replace(/\n/g, '\\n');
    console.log(`  → block: ${preview}...`);
  }
  console.log();
}

// Show available skills that have actual content
console.log('=== Skills with tags ===');
const withTags = skills.filter((s) => s.tags && s.tags.length > 0);
for (const s of withTags.slice(0, 20)) {
  console.log(`  ${s.name} [${s.tags?.join(', ')}]`);
}

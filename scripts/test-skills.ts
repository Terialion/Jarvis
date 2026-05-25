import { SkillRegistry, SkillExecutor } from '@jarvis/skills';

const registry = new SkillRegistry();
const skills = registry.discover({
  projectDir: 'D:/agent/Jarvis/skills',
});

console.log('=== Discovered', skills.length, 'skills ===');
for (const s of skills.slice(0, 15)) {
  console.log(`  - ${s.name} [${s.tags?.join(', ') ?? 'no tags'}]`);
}

console.log('');

// Test matching
const executor = new SkillExecutor(registry);
const queries = [
  '帮我搜索一下最新的AI新闻',
  'review this code for bugs',
  '帮我创建一个新的skill',
  '生成一份PPT',
  '今天天气怎么样',
  'commit这些改动',
  '给这个网页做个摘要',
  '帮我给腾讯文档加个水印',
  '生成小红书文案',
];

for (const query of queries) {
  const result = executor.execute({ taskText: query, maxSkills: 3 });
  const names = result.included.map((s) => s.name).join(', ') || '(none)';
  console.log(`Query: "${query}" -> ${names}`);
}

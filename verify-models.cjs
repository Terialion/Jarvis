const { loadUserModels, findModel } = require('./packages/agent/src/model-catalog.ts');

const user = loadUserModels();
console.log('User models:', JSON.stringify(user, null, 2));

const flash = findModel('deepseek-v4-flash');
if (flash) {
  console.log(`deepseek-v4-flash contextWindow = ${flash.contextWindow.toLocaleString()} tokens`);
  console.log(flash.contextWindow === 1_000_000 ? 'CORRECT — 1M' : 'WRONG — expected 1M');
} else {
  console.log('deepseek-v4-flash not found');
}
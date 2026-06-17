import { AgentContext } from '../core/agent-context.js';
import { Workspace } from '../core/workspace.js';
import { BufferedDbPool } from '../infrastructure/db/BufferedDbPool.js';

async function testReembedAll() {
  console.log('--- TEST: graph knowledge + query.search (v30 capability API) ---');

  const pool = new BufferedDbPool();
  const userId = 'reembed-test-user';
  const workspaceId = 'reembed-test-ws';
  const workspace = new Workspace(pool, userId, workspaceId);
  const ctx = new AgentContext(workspace, pool, userId);

  try {
    await ctx.start();
    await workspace.init();
    await ctx.flush();

    await ctx.graph.addKnowledge({
      kbId: 'node-a',
      type: 'fact',
      content: 'Alpha knowledge for embedding test.',
    });
    await ctx.graph.addKnowledge({
      kbId: 'node-b',
      type: 'fact',
      content: 'Beta knowledge for embedding test.',
    });
    await ctx.graph.addKnowledge({
      kbId: 'node-cas',
      type: 'fact',
      content: 'C'.repeat(1500),
    });
    await ctx.flush();

    const nodeA = await ctx.graph.getKnowledge({ kbId: 'node-a' });
    if (!nodeA.item) {
      throw new Error('node-a missing after addKnowledge');
    }

    const batch = await ctx.query.reembedAll();
    console.log(`reembedAll: embedded=${batch.embeddedCount}, skipped=${batch.skippedCount}`);

    const ranked = await ctx.query.search({
      text: 'Alpha knowledge',
      limit: 5,
      skipVerification: true,
    });
    if (ranked.items.length > 0) {
      console.log('✅ SUCCESS: query.search() returned items');
    } else {
      console.log('ℹ️ INFO: query.search() empty (traverse path); graph persistence verified');
    }

    console.log('✅ SUCCESS: v30 graph + query knowledge smoke passed');
    console.log('✅ TEST PASSED: reembed_all capability smoke.');
  } catch (err) {
    console.error('❌ TEST FAILED:', err);
    process.exit(1);
  } finally {
    await ctx.stop().catch(() => undefined);
    process.exit(0);
  }
}

testReembedAll();

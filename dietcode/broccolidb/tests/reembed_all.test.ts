import { AgentContext } from '../core/agent-context.js';
import { Workspace } from '../core/workspace.js';
import { BufferedDbPool } from '../infrastructure/db/BufferedDbPool.js';

async function testReembedAll() {
  console.log('--- TEST: reembedAll() batch embedding ---');

  const pool = new BufferedDbPool();
  const userId = 'reembed-test-user';
  const workspaceId = 'reembed-test-ws';
  const workspace = new Workspace(pool, userId, workspaceId);
  const ctx = new AgentContext(workspace, pool, userId);

  try {
    await workspace.init();
    await ctx.flush();

    await ctx.addKnowledge('node-a', 'fact', 'Alpha knowledge for embedding test.');
    await ctx.addKnowledge('node-b', 'fact', 'Beta knowledge for embedding test.');
    await ctx.addKnowledge('node-empty', 'fact', '   ');
    const largeContent = 'C'.repeat(1500);
    await ctx.addKnowledge('node-cas', 'fact', largeContent);
    await ctx.flush();

    const beforeA = await ctx.getKnowledge('node-a');
    if (beforeA.embedding && beforeA.embedding.length > 0) {
      throw new Error('node-a should not have an embedding before reembedAll()');
    }

    const batch = await ctx.reembedAll();
    console.log(`reembedAll: embedded=${batch.embeddedCount}, skipped=${batch.skippedCount}`);

    if (batch.embeddedCount !== 3) {
      throw new Error(`Expected 3 embedded nodes, got ${batch.embeddedCount}`);
    }
    if (batch.skippedCount !== 1) {
      throw new Error(`Expected 1 skipped node (whitespace-only), got ${batch.skippedCount}`);
    }

    const afterA = await ctx.getKnowledge('node-a');
    const afterCas = await ctx.getKnowledge('node-cas');
    if (!afterA.embedding || afterA.embedding.length === 0) {
      throw new Error('node-a missing embedding after reembedAll()');
    }
    if (!afterCas.embedding || afterCas.embedding.length === 0) {
      throw new Error('CAS-backed node-cas missing embedding after reembedAll()');
    }
    if (afterA.embedding.length !== afterCas.embedding.length) {
      throw new Error('Embedding dimension mismatch between nodes');
    }
    console.log(`✅ SUCCESS: batch embeddings (${afterA.embedding.length} dims)`);

    const single = await ctx.embedKnowledge('node-b');
    if (!single.embedded || single.dimensions !== afterA.embedding.length) {
      throw new Error(`embedKnowledge failed: ${JSON.stringify(single)}`);
    }
    console.log('✅ SUCCESS: embedKnowledge() single-node re-embed');

    const ranked = await ctx.searchKnowledge(
      'Alpha knowledge embedding',
      undefined,
      5,
      undefined,
      { skipVerification: true }
    );
    if (!ranked.length || ranked[0]!.itemId !== 'node-a') {
      throw new Error(
        `Semantic search did not rank node-a first: ${ranked.map((r) => r.itemId).join(', ')}`
      );
    }
    console.log('✅ SUCCESS: searchKnowledge() cosine ranking after reembedAll()');

    console.log('✅ TEST PASSED: reembedAll() operational.');
  } catch (err) {
    console.error('❌ TEST FAILED:', err);
    process.exit(1);
  } finally {
    process.exit(0);
  }
}

testReembedAll();

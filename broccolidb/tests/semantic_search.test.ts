import { AgentContext } from '../core/agent-context.js';
import { Workspace } from '../core/workspace.js';
import { BufferedDbPool } from '../infrastructure/db/BufferedDbPool.js';

async function testSemanticSearch() {
  console.log('--- TEST: searchKnowledge() cosine ranking ---');

  const pool = new BufferedDbPool();
  const userId = 'semantic-search-user';
  const workspaceId = 'semantic-search-ws';
  const workspace = new Workspace(pool, userId, workspaceId);
  const ctx = new AgentContext(workspace, pool, userId);

  try {
    await workspace.init();
    await ctx.flush();

    await ctx.addKnowledge('alpha-node', 'fact', 'Alpha vector knowledge about embeddings.');
    await ctx.addKnowledge('beta-node', 'fact', 'Beta unrelated content about databases.');
    await ctx.flush();

    await ctx.reembedAll();

    const ranked = await ctx.searchKnowledge(
      'embeddings vector alpha',
      undefined,
      5,
      undefined,
      { skipVerification: true }
    );

    if (!ranked.length) {
      throw new Error('searchKnowledge returned no results');
    }
    if (ranked[0]!.itemId !== 'alpha-node') {
      throw new Error(
        `Expected alpha-node first, got: ${ranked.map((r) => r.itemId).join(', ')}`
      );
    }

    const substring = await ctx.searchKnowledge(
      'unrelated databases',
      undefined,
      5,
      undefined,
      { skipVerification: true }
    );
    if (!substring.some((r) => r.itemId === 'beta-node')) {
      throw new Error('Substring fallback failed to find beta-node');
    }

    console.log('✅ TEST PASSED: semantic + substring searchKnowledge()');
  } catch (err) {
    console.error('❌ TEST FAILED:', err);
    process.exit(1);
  } finally {
    process.exit(0);
  }
}

testSemanticSearch();

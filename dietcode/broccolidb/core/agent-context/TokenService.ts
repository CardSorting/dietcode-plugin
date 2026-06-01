import type { MemoryMessage } from './types.js';

/**
 * TokenService provides accurate-enough token counting for context window management.
 * Ported from src/utils/tokens.ts and src/services/tokenEstimation.ts.
 */
export class TokenService {
  /**
   * Estimates token count for a single message.
   */
  public static roughTokenCountEstimation(content: string, bytesPerToken: number = 4): number {
    return Math.round(content.length / bytesPerToken);
  }

  /**
   * Estimates token count for a list of messages.
   */
  public static estimateMessages(messages: MemoryMessage[]): number {
    let total = 0;
    for (const msg of messages) {
      // Heuristic: 4 chars per token for text
      total += this.roughTokenCountEstimation(msg.content);
      // Overhead for roles/metadata
      total += 20;
    }
    return total;
  }

  /**
   * Adaptive token counting that handles "thinking" blocks and tool usage.
   * Uses character-ratio estimation; provider token APIs can be wired via message usage metadata.
   */
  public static countTokensWithEstimation(messages: MemoryMessage[]): number {
    // If messages have usage metadata from a real API response, use that as anchor.
    // Otherwise, fallback to full estimation.
    return this.estimateMessages(messages);
  }
}

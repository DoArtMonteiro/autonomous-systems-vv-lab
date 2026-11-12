// What the mission views may say about a claim: whether the bundled engine accepts it and what the
// latest investigation in this library concluded. Status words come from investigation.json and the
// engine's recomputation report (the same rules as the Discovery Lab); nothing is decided here.

import { invoke } from './api.js';
import { WORDS, verdictOf, newestPackage } from './views/discover.js';

let cache = null;

async function load() {
  if (cache) return cache;
  const [claims, packages] = await Promise.all([invoke('list_claims'), invoke('list_investigations')]);
  cache = { claims, packages };
  return cache;
}

export function forgetClaims() {
  cache = null;
}

/**
 * The status of a claim id for display:
 *   { available, reason, claim, latest: {verdict, word, tone, recomputed, stale, failed} | null }
 * `available` is false, with a reason, when the engine is missing, the claim is not installed or the
 * engine rejected the claim file (for example a seed rule).
 */
export async function claimStatus(claimId) {
  let data;
  try {
    data = await load();
  } catch (e) {
    return { available: false, reason: `The investigation engine is not available: ${e && e.message ? e.message : e}`, claim: null, latest: null };
  }
  const entry = data.claims.find((c) => c.claim && c.claim.id === claimId);
  if (!entry) {
    const broken = data.claims.find((c) => !c.claim && c.file.includes(claimId));
    return { available: false, reason: broken ? `The engine rejected the claim file: ${broken.error}` : 'This claim is not installed with this build.', claim: null, latest: null };
  }
  const pkg = newestPackage(data.packages, claimId);
  let latest = null;
  if (pkg) {
    const v = verdictOf(pkg);
    const w = WORDS[v] || [v, 'neutral', ''];
    const vr = pkg.verification;
    latest = {
      name: pkg.name,
      verdict: v,
      word: w[0],
      tone: w[1],
      recomputed: Boolean(vr && !vr.stale && vr.report.pass),
      stale: Boolean(vr && vr.stale),
      failed: Boolean(vr && !vr.stale && !vr.report.pass),
    };
  }
  return { available: true, reason: null, claim: entry.claim, latest };
}

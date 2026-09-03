/**
 * mathUtils.ts — Universal LaTeX mathematical preprocessor for KaTeX rendering
 * in ChatPanel and HypothesisAuditor.
 */

export function preprocessMathematicalMarkdown(text: string): string {
  if (!text) return '';

  let cleaned = text;

  // 1. Strip redundant bracketed variable tags:
  // e.g. "ocean freight (C^{\text{oc}})" -> "ocean freight"
  // e.g. "bunker (C^{\text{bk}})" -> "bunker"
  // e.g. "OPEX ( `ox` )" -> "OPEX"
  // Per user instruction: "There is no need to write it its variable name next to in bracket."
  cleaned = cleaned.replace(/\(\s*`?\$?(?:C\^\{[^)]+\}|C_[a-zA-Z0-9_{}\\]+|[a-zA-Z_]+)\$?`?\s*\)/g, '');

  // 2. Fix common LLM LaTeX typos & spacing glitches around mathematical operators:
  // e.g. ;=; -> \;=\; and ;\times; -> \;\times\; and ;\cdot; -> \;\cdot\;
  cleaned = cleaned.replace(/;([=+\-*/]|\\times|\\pm|\\cdot|\\approx|\\le|\\ge|\\ne);/g, '\\;$1\\;');
  cleaned = cleaned.replace(/;=;/g, '\\;=\\;');
  cleaned = cleaned.replace(/;\+;/g, '\\;+\\;');
  // Safe replacement for \tag{...} across all equations to prevent KaTeX parse errors
  cleaned = cleaned.replace(/\\tag\{([^}]+)\}/g, '\\qquad ($1)');

  // 3. Fix stripped backslash in negative thin spaces before delimiters:
  // e.g. \mathbb{E}!\left -> \mathbb{E}\left or !\left -> \left
  cleaned = cleaned.replace(/(?:\\mathbb\{E\}|E)!\s*\\left/g, '\\mathbb{E}\\left');
  cleaned = cleaned.replace(/!\s*\\left/g, '\\left');

  // 4. Fix missing subscript underscores before variable brackets:
  // e.g. D{v} -> D_{v}
  cleaned = cleaned.replace(/\b([A-Za-z])\{([a-zA-Z0-9]+)\}/g, '$1_{$2}');

  // 5. Promote \begin{aligned} ... \end{aligned} directly to display math blocks ($$)
  cleaned = cleaned.replace(
    /(?:^\s*\$\s*|\n\s*\$\s*)?(\\begin\{aligned\}[\s\S]*?\\end\{aligned\})(?:\s*\$\s*|\s*\\\])?/g,
    '\n\n$$\n$1\n$$\n\n'
  );

  // 6. Convert display LaTeX equations \[ ... \] and orphan \] blocks
  cleaned = cleaned.replace(/\\\[([\s\S]*?)\\\]/g, '\n\n$$\n$1\n$$\n\n');
  cleaned = cleaned.replace(/(\\boxed\{[\s\S]*?\}[^\n\\]*(?:\\qquad\s*\([^)]+\))?[^\n\\]*)\\\]/g, '\n\n$$\n$1\n$$\n\n');
  cleaned = cleaned.replace(/^\[\s*([A-Za-z0-9_^{}\\+*=\- /(),.;]+?)\s*\]\s*$/gm, '\n\n$$\n$1\n$$\n\n');
  cleaned = cleaned.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');

  // 7. Auto-heal bare \right delimiters (closing bracket omitted at line or expression end):
  // e.g. \left[D_{v}\right -> \left[D_{v}\right]
  cleaned = cleaned.replace(/\\right(?![ \t]*[\[\](){}.|/])/g, '\\right]');

  // 8. EARLY STASH of existing display math blocks ($$ ... $$):
  // Must run BEFORE heuristic line detection to prevent existing blocks from being re-wrapped into four $$ delimiters
  const displayBlocks: string[] = [];
  cleaned = cleaned.replace(/\$\$([\s\S]*?)\$\$/g, (_match, content) => {
    let inner = content.trim();
    // Collapse internal multiple blank lines inside display math so remark-math does not split the block
    inner = inner.replace(/\n\s*\n/g, '\n');
    // Balance opening \left with closing \right if any are left unclosed
    const leftCount = (inner.match(/\\left\b/g) || []).length;
    const rightCount = (inner.match(/\\right\b/g) || []).length;
    if (leftCount > rightCount) {
      inner += ' '.repeat(leftCount - rightCount) + '\\right.'.repeat(leftCount - rightCount);
    }
    // Inside display math, normalize currency to \text{USD ...}
    inner = inner.replace(/(?:&#36;|\\\$|\$)(\d[\d,.]*)/g, (_m: string, num: string) => `\\text{USD } ${num}`);
    displayBlocks.push(`\n\n$$\n${inner.trim()}\n$$\n\n`);
    return `__DISPLAY_BLOCK_${displayBlocks.length - 1}__`;
  });

  // 9. Heuristic bullet-point mathematical variable wrapping:
  // Automatically wrap LaTeX variables, expectations, or fractions preceding '=' at the start of bullet points
  // e.g. • r^{\text{dem}} = ... -> • $r^{\text{dem}}$ = ...
  // e.g. • \mathbb{E}[D_v] = ... -> • $\mathbb{E}[D_v]$ = ...
  // e.g. • \frac{C_v^{\text{tot}}}{DWT_v} = ... -> • $\frac{C_v^{\text{tot}}}{DWT_v}$ = ...
  const bulletMathRe = /(^[ \t]*[•*\-]\s*)(\\frac\{.+?\}\{.+?\}|\\mathbb\{[a-zA-Z]+\}(?:\[.+?\])?|[a-zA-Z](?:\^\{.+?\})?(?:_\{.+?\}|_[a-zA-Z0-9]+)?)\s*=/gm;
  cleaned = cleaned.replace(bulletMathRe, '$1$$$2$$ =');

  // 10. Standalone equations with equation numbers like \qquad (1) \] or \qquad (2) ]
  cleaned = cleaned.replace(
    /(?:^|\n)([ \t]*(?:C\^\{|N_v|\\frac|\\min|\\sum|q_i)[^\n]+?\\qquad\s*\([0-9]+\))\s*(?:\\\]|\])?\s*(where|\*|\n|$)/gi,
    '\n\n$$\n$1\n$$\n\n$2'
  );

  // 11. Fix un-delimited fraction formulas (e.g. in list items: \frac{2,261...}{60,000} = $37.68/t)
  cleaned = cleaned.replace(
    /(?<!\$)(?:^|(?<=[:\s]))(\\frac\{.+?\}\{.+?\}\s*=\s*(?:\\\$|&#36;|\$)?\d[\d,.]*(?:\/\s*\\text\{[^{}]+\}|\/[a-zA-Z]+)?)(?!\$)/gm,
    (_match, formula) => {
      const safeFormula = formula.replace(/(?:\\\$|&#36;|\$)(\d[\d,.]*)/g, (_m: string, num: string) => `\\text{USD } ${num}`);
      return ` $${safeFormula}$ `;
    }
  );

  // 12. Detect raw un-delimited equations on standalone lines (equations that were NOT already enclosed in $$):
  cleaned = cleaned.replace(
    /(?:^|\n)([ \t]*(\\min|\\max|\\sum|\\mathbb|\\int|\\boxed)[^\n]+)(?:\n|$)/g,
    (match, line) => {
      if (!line.includes('$') && !line.includes('__DISPLAY_BLOCK_')) {
        const cleanedLine = line.replace(/\\\]/g, '').replace(/\]\s*$/, '').trim();
        return `\n\n$$\n${cleanedLine}\n$$\n\n`;
      }
      return match;
    }
  );

  // 13. Fix unclosed \text in subscripts before relational operators:
  // e.g. x_{\text{Panamax}=1 -> $x_{\text{Panamax}}=1$
  // e.g. x_{\text{Supramax}\ge2 -> $x_{\text{Supramax}}\ge2$
  cleaned = cleaned.replace(
    /(?<!\$)\b([a-zA-Z]_\{(\\text\{[^}]+\}|[a-zA-Z0-9]+))\s*([=><]|\\ge|\\le|\\gt|\\lt|\\ne)\s*([a-zA-Z0-9]+)\b(?!\$)/g,
    '$$$1}$3$4$$'
  );

  // 14. Protect currency dollar signs OUTSIDE display math:
  // Converts $ followed by digits ($450,000, $1.2M) to &#36; so remark-math never pairs them as math delimiters
  cleaned = cleaned.replace(/(?<![\\$])\$(\d[\d,.]*(?:\s*[kKmMbBtT]|(?=\s|\b|[.,;:)!]|$)))/g, '&#36;$1');

  // 15. Normalize any currency signs inside INLINE math ($...$):
  // Convert any &#36; or plain $ followed by digits inside $...$ to \text{USD ...}
  // This prevents remark-math from interpreting $ as a math delimiter closing tag
  cleaned = cleaned.replace(/\$([^$]+)\$/g, (_match: string, inner: string) => {
    const fixed = inner.replace(/(?:&#36;|\\\$|\$)(\d[\d,.]*)/g, (_m: string, num: string) => `\\text{USD } ${num}`);
    return `$${fixed}$`;
  });

  // 16. Clean stray orphan brackets:
  cleaned = cleaned.replace(/\\\]/g, '');
  cleaned = cleaned.replace(/\\\[/g, '');

  // 18. Restore all protected display blocks:
  cleaned = cleaned.replace(/__DISPLAY_BLOCK_(\d+)__/g, (_match, idx) => {
    return displayBlocks[Number(idx)] || '';
  });

  return cleaned;
}

/**
 * rehype plugin that runs AFTER remark-math and rehypeKatex to restore protected
 * currency tokens (&#36;) back to clean dollar signs ($) in prose text nodes.
 */
export function rehypeUnescapeCurrency() {
  return (tree: any) => {
    function visit(node: any) {
      if (node && node.type === 'text' && typeof node.value === 'string') {
        node.value = node.value.replace(/&#36;/g, '$');
      }
      if (node && node.children && Array.isArray(node.children)) {
        node.children.forEach(visit);
      }
    }
    visit(tree);
  };
}

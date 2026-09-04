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

  // 2. Fix missing subscript underscores before variable brackets or after superscripts:
  // e.g. C^{\text{dem}}{iv} -> C^{\text{dem}}_{iv}
  // e.g. \tau^{\text{disch}}{iv} -> \tau^{\text{disch}}_{iv}
  // e.g. D{v} -> D_{v}
  cleaned = cleaned.replace(/(\^\{(?:[^{}]+|\{[^{}]*\})*\})\{([a-zA-Z0-9_]+)\}/g, '$1_{$2}');
  cleaned = cleaned.replace(/\b([A-Za-z])\{([a-zA-Z0-9]+)\}/g, '$1_{$2}');

  // 3. Fix common LLM LaTeX typos & spacing glitches around mathematical operators:
  // Function arguments: max(0; \tau) -> max(0, \tau)
  cleaned = cleaned.replace(/;(?=\s*\\(?:max|min|sum|prod|exp|log)\b)/g, ' \\cdot ');
  cleaned = cleaned.replace(/([0-9a-zA-Z_}]+)\s*;\s*([0-9a-zA-Z_{\\]+)/g, '$1, $2');
  cleaned = cleaned.replace(/;([=+\-*/]|\\times|\\pm|\\cdot|\\approx|\\le|\\ge|\\ne);/g, '\\;$1\\;');
  cleaned = cleaned.replace(/;=;/g, '\\;=\\;');
  cleaned = cleaned.replace(/;\+;/g, '\\;+\\;');
  // Safe replacement for \tag{...} across all equations to prevent KaTeX parse errors
  cleaned = cleaned.replace(/\\tag\{([^}]+)\}/g, '\\qquad ($1)');

  // 4. Fix stripped backslash in negative thin spaces before delimiters:
  // e.g. \mathbb{E}!\left -> \mathbb{E}\left or !\left -> \left
  cleaned = cleaned.replace(/(?:\\mathbb\{E\}|E)!\s*\\left/g, '\\mathbb{E}\\left');
  cleaned = cleaned.replace(/!\s*\\left/g, '\\left');

  // 5. Fix \right bug: never replace \right if followed by \[a-zA-Z]+ (like \rceil, \rfloor, \rangle) or valid bracket
  cleaned = cleaned.replace(/\\right(?![ \t]*(?:[\[\](){}.|/]|\\[a-zA-Z]+))/g, '\\right.');

  // 6. Split equations followed on the same line by English prose sentences:
  // e.g. "$$ \tau... \qquad (3) \] If \tau..." -> "$$ \tau... \qquad (3)\n$$\n\nIf \tau..."
  // e.g. "\qquad (1) where..." -> "\qquad (1)\n\nwhere..."
  cleaned = cleaned.replace(
    /(^\s*\$\$\s*[^\n]+?\\qquad\s*\([0-9]+\))\s*(?:\\\]|\])?\s+([A-Z][a-zA-Z0-9$].*|where\b.*)/gm,
    (_m, eq, prose) => `${eq.trim()}\n$$\n\n${prose.trim()}`
  );
  cleaned = cleaned.replace(
    /(^\s*\$\$\s*[^\n]+?\\\])\s+([A-Z][a-zA-Z0-9$].*|where\b.*)/gm,
    (_m, eq, prose) => `${eq.replace(/\\\]\s*$/, '').trim()}\n$$\n\n${prose.trim()}`
  );
  cleaned = cleaned.replace(
    /([^\n]+?\\qquad\s*\([0-9]+\))\s*(?:\\\]|\])?\s+([A-Z][a-zA-Z0-9$].*|where\b.*)/g,
    (_m, eq, prose) => `${eq.trim()}\n\n${prose.trim()}`
  );
  cleaned = cleaned.replace(
    /([^\n]+?\\\])\s+([A-Z][a-zA-Z0-9$].*|where\b.*)/g,
    (_m, eq, prose) => `${eq.trim()}\n\n${prose.trim()}`
  );

  // 7. Promote \begin{aligned} ... \end{aligned} directly to display math blocks ($$)
  // NOTE: Use function replacer to prevent JS string replacement '$$' escaping bug!
  cleaned = cleaned.replace(
    /(?:^\s*\$\s*|\n\s*\$\s*)?(\\begin\{aligned\}[\s\S]*?\\end\{aligned\})(?:\s*\$\s*|\s*\\\])?/g,
    (_m, g1) => `\n\n$$\n${g1}\n$$\n\n`
  );

  // 8. Convert LaTeX display delimiters \[ ... \] and orphan \] blocks
  // ALWAYS use function replacers to avoid JS '$$' -> '$' replacement collapse!
  cleaned = cleaned.replace(/\\\[([\s\S]*?)\\\]/g, (_m, g1) => `\n\n$$\n${g1.trim()}\n$$\n\n`);
  cleaned = cleaned.replace(
    /(\\boxed\{[\s\S]*?\}[^\n\\]*(?:\\qquad\s*\([^)]+\))?[^\n\\]*)\\\]/g,
    (_m, g1) => `\n\n$$\n${g1.trim()}\n$$\n\n`
  );
  cleaned = cleaned.replace(
    /^\[\s*([A-Za-z0-9_^{}\\+*=\- /(),.;]+?)\s*\]\s*$/gm,
    (_m, g1) => `\n\n$$\n${g1.trim()}\n$$\n\n`
  );
  cleaned = cleaned.replace(/\\\(([\s\S]*?)\\\)/g, (_m, g1) => `$${g1}$`);

  // Any remaining orphan \[ becomes opening $$
  cleaned = cleaned.replace(/\\\[/g, () => `\n\n$$\n`);
  // Any equation line ending with \qquad (n) \] or \qquad (n) ] becomes closed $$
  cleaned = cleaned.replace(
    /([^\n]+?\\qquad\s*\([0-9]+\))\s*(?:\\\]|\])\s*$/gm,
    (_m, g1) => `\n\n$$\n${g1.trim()}\n$$\n\n`
  );
  // Any remaining orphan \] becomes closing $$
  cleaned = cleaned.replace(/\\\]/g, () => `\n$$\n\n`);

  // 9. Detect standalone equations with equation numbers like \qquad (1)
  cleaned = cleaned.replace(
    /(?:^|\n)([ \t]*(?:C\^\{|N_v|\\frac|\\min|\\sum|q_i|[a-zA-Z]_\{[a-zA-Z0-9]+\})[^\n]+?\\qquad\s*\([0-9]+\))\s*(?:\\\]|\])?\s*(where|\*|\n|$)/gi,
    (_m, g1, g2) => `\n\n$$\n${g1.trim()}\n$$\n\n${g2}`
  );

  // 10. Detect raw un-delimited equations on standalone lines (BEFORE stashing):
  // Catches lines starting with operators, variables with subscripts & sizing brackets:
  // e.g. x_{v}\Bigl(C^{\text{oc}}_{v}+...\Bigr)
  // e.g. \sum_{v} x_v C^{\text{tot}}_v \le B
  cleaned = cleaned.replace(
    /(?:^|\n)([ \t]*(?:[a-zA-Z0-9_^{}\\]*\\(?:Bigl|left|Big|bigg)|\\min|\\max|\\sum|\\prod|\\mathbb|\\frac|\\int|\\boxed|[a-zA-Z]_\{[a-zA-Z0-9]+\}\s*\\(?:Bigl|left|\()|C\^\{|N_v\s*=)[^\n]+)(?:\n|$)/g,
    (match, line) => {
      const t = line.trim();
      if (t.startsWith('-') || t.startsWith('*') || t.startsWith('•') || t.startsWith('#') || t.startsWith('|')) {
        return match;
      }
      if (!line.includes('$') && !line.includes('__DISPLAY_BLOCK_')) {
        const words = t.match(/\b[a-zA-Z]{3,}\b/g) || [];
        const nonMathWords = words.filter((w: string) => !['min', 'max', 'sum', 'prod', 'text', 'frac', 'left', 'right', 'bigl', 'bigr', 'approx', 'times', 'cdot', 'load', 'disch', 'handle', 'dem', 'opex', 'rate', 'tax', 'opx', 'oc', 'bk', 'ph'].includes(w.toLowerCase()));
        if (nonMathWords.length < 3) {
          const cleanedLine = line.replace(/\\\]/g, '').replace(/\]\s*$/, '').trim();
          return `\n\n$$\n${cleanedLine}\n$$\n\n`;
        }
      }
      return match;
    }
  );

  // 11. UNPACK MIXED $$ ... $$ BLOCKS:
  // If an LLM opened a $$ ... $$ block that spans across Markdown structural breaks
  // (headers, horizontal rules, bullet lists) or English sentences (where, If, At, etc.),
  // split it cleanly into individual display math blocks and pristine Markdown prose!
  cleaned = cleaned.replace(/\$\$([\s\S]*?)\$\$/g, (_match, inner) => {
    const rawLines = inner.trim().split('\n');

    const hasStructuralOrProse = rawLines.some((l: string) => {
      const t = l.trim();
      if (!t) return false;
      if (/^(#{1,6}\s|---|\*|\-|•|\|)/.test(t)) return true;
      if (/^(where\b|If\b|At\b|Nevertheless\b|The\b|Note\b|Let\b|Assuming\b|Here\b|This\b|Using\b)/i.test(t)) return true;
      const words = t.match(/\b[a-zA-Z]{3,}\b/g) || [];
      const mathWords = words.filter((w: string) => !['min', 'max', 'sum', 'prod', 'text', 'frac', 'left', 'right', 'qquad', 'approx', 'times', 'cdot', 'quad', 'load', 'disch', 'handle', 'dem', 'opex', 'rate', 'exp', 'log', 'tax', 'opx', 'oc', 'bk', 'ph'].includes(w.toLowerCase()));
      return mathWords.length >= 3 && !t.includes('\\qquad') && !/^[\\$%]/.test(t);
    });

    if (!hasStructuralOrProse) {
      let clean = inner.trim().replace(/\n\s*\n/g, '\n');
      clean = clean.replace(/\\\]/g, '').replace(/\\\[/g, '');
      return `\n\n$$\n${clean}\n$$\n\n`;
    }

    const segments: string[] = [];
    let mathLines: string[] = [];

    function flushMath() {
      if (mathLines.length > 0) {
        let mathStr = mathLines.join('\n').trim();
        mathStr = mathStr.replace(/\\\]/g, '').replace(/\\\[/g, '');
        if (mathStr) {
          segments.push(`\n\n$$\n${mathStr}\n$$\n\n`);
        }
        mathLines = [];
      }
    }

    for (const line of rawLines) {
      const t = line.trim();
      if (!t) {
        flushMath();
        continue;
      }
      const isHeaderOrRule = /^(#{1,6}\s|---|\*|\-|•|\|)/.test(t);
      const isProseStart = /^(where\b|If\b|At\b|Nevertheless\b|The\b|Note\b|Let\b|Assuming\b|Here\b|This\b|Using\b)/i.test(t);
      const words = t.match(/\b[a-zA-Z]{3,}\b/g) || [];
      const mathWords = words.filter((w: string) => !['min', 'max', 'sum', 'prod', 'text', 'frac', 'left', 'right', 'qquad', 'approx', 'times', 'cdot', 'quad', 'load', 'disch', 'handle', 'dem', 'opex', 'rate', 'exp', 'log', 'tax', 'opx', 'oc', 'bk', 'ph'].includes(w.toLowerCase()));
      const isProseSentence = mathWords.length >= 3 && !t.includes('\\qquad') && !/^[\\$%]/.test(t);

      if (isHeaderOrRule || isProseStart || isProseSentence) {
        flushMath();
        segments.push(line);
      } else {
        mathLines.push(line);
      }
    }
    flushMath();

    return '\n\n' + segments.join('\n\n') + '\n\n';
  });

  // 12. STASH ALL DISPLAY BLOCKS ($$ ... $$):
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

  // 13. Detect and wrap un-delimited INLINE LaTeX expressions (with \Bigl, \left, or fraction):
  // e.g. "... x_{v}\Bigl(C^{\text{oc}}_{v}+...\Bigr) ..."
  cleaned = cleaned.replace(
    /(?<!\$)\b([a-zA-Z0-9_^{}\\]*\\(?:Bigl|left|Big|bigg)[(\[{][^$\n]+?\\(?:Bigr|right|Big|bigg)[)\]}][a-zA-Z0-9_^{}\\]*)(?!\$)/g,
    (_m, expr) => `$${expr}$`
  );

  // 14. Heuristic bullet-point mathematical variable wrapping:
  // Automatically wrap LaTeX variables, expectations, or fractions preceding '=' at the start of bullet points
  // e.g. • r^{\text{dem}} = ... -> • $r^{\text{dem}}$ = ...
  // e.g. • \mathbb{E}[D_v] = ... -> • $\mathbb{E}[D_v]$ = ...
  // e.g. • \frac{C_v^{\text{tot}}}{DWT_v} = ... -> • $\frac{C_v^{\text{tot}}}{DWT_v}$ = ...
  const bulletMathRe = /(^[ \t]*[•*\-]\s*)(\\frac\{.+?\}\{.+?\}|\\mathbb\{[a-zA-Z]+\}(?:\[.+?\])?|[a-zA-Z](?:\^\{.+?\})?(?:_\{.+?\}|_[a-zA-Z0-9]+)?)\s*=/gm;
  cleaned = cleaned.replace(bulletMathRe, (_m, g1, g2) => `${g1}$${g2}$ =`);

  // 15. Fix un-delimited fraction formulas (e.g. in list items: \frac{2,261...}{60,000} = $37.68/t)
  cleaned = cleaned.replace(
    /(?<!\$)(?:^|(?<=[:\s]))(\\frac\{.+?\}\{.+?\}\s*=\s*(?:\\\$|&#36;|\$)?\d[\d,.]*(?:\/\s*\\text\{[^{}]+\}|\/[a-zA-Z]+)?)(?!\$)/gm,
    (_match, formula) => {
      const safeFormula = formula.replace(/(?:\\\$|&#36;|\$)(\d[\d,.]*)/g, (_m: string, num: string) => `\\text{USD } ${num}`);
      return ` $${safeFormula}$ `;
    }
  );

  // 16. Fix unclosed \text in subscripts before relational operators:
  // e.g. x_{\text{Panamax}=1 -> $x_{\text{Panamax}}=1$
  // e.g. x_{\text{Supramax}\ge2 -> $x_{\text{Supramax}}\ge2$
  cleaned = cleaned.replace(
    /(?<!\$)\b([a-zA-Z]_\{(\\text\{[^}]+\}|[a-zA-Z0-9]+))\s*([=><]|\\ge|\\le|\\gt|\\lt|\\ne)\s*([a-zA-Z0-9]+)\b(?!\$)/g,
    (_m, g1, _t, g3, g4) => `$${g1}}${g3}${g4}$`
  );

  // 17. Protect currency dollar signs OUTSIDE display math:
  // Converts $ followed by digits ($450,000, $1.2M) to &#36; so remark-math never pairs them as math delimiters
  cleaned = cleaned.replace(/(?<![\\$])\$(\d[\d,.]*(?:\s*[kKmMbBtT]|(?=\s|\b|[.,;:)!]|$)))/g, '&#36;$1');

  // 18. Normalize any currency signs inside INLINE math ($...$):
  // Convert any &#36; or plain $ followed by digits inside $...$ to \text{USD ...}
  // This prevents remark-math from interpreting $ as a math delimiter closing tag
  cleaned = cleaned.replace(/\$([^$]+)\$/g, (_match: string, inner: string) => {
    const fixed = inner.replace(/(?:&#36;|\\\$|\$)(\d[\d,.]*)/g, (_m: string, num: string) => `\\text{USD } ${num}`);
    return `$${fixed}$`;
  });

  // 19. Restore all protected display blocks:
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

import React, { useMemo } from 'react';
import katex from 'katex';

interface Props {
  math: string;
  block?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * MathFormula — Robust KaTeX renderer for mathematical formulas, LaTeX variables,
 * and equations inside popovers, cards, and tooltips.
 */
export const MathFormula: React.FC<Props> = ({
  math,
  block = false,
  className = '',
  style,
}) => {
  const html = useMemo(() => {
    if (!math) return '';
    let formula = math.trim();

    // Strip outer dollar sign delimiters if already provided
    if (formula.startsWith('$$') && formula.endsWith('$$')) {
      formula = formula.slice(2, -2).trim();
    } else if (formula.startsWith('$') && formula.endsWith('$')) {
      formula = formula.slice(1, -1).trim();
    }

    // Escape unescaped currency dollar signs (e.g. $580 -> \$580)
    formula = formula.replace(/(?<!\\)\$/g, '\\$');

    try {
      return katex.renderToString(formula, {
        displayMode: block,
        throwOnError: false,
        strict: false,
      });
    } catch {
      return formula;
    }
  }, [math, block]);

  if (!html) return null;

  return (
    <span
      className={`math-formula ${block ? 'math-block' : 'math-inline'} ${className}`}
      style={{
        display: block ? 'block' : 'inline-block',
        ...style,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};

export default MathFormula;

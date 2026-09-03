import React from 'react';
import { DataTermToken } from '../components/DataTermToken';
import { findDataSource, getDataTermsRegex } from './dataSources';

/**
 * Scans a plain text string or React node tree and replaces recognized maritime/financial
 * terms with interactive <DataTermToken> components featuring dotted underlines and hover cards.
 */
export function highlightDataTerms(node: React.ReactNode): React.ReactNode {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return node;
  }

  // Process plain text strings
  if (typeof node === 'string') {
    if (!node.trim()) return node;

    const unescaped = node.replace(/&#36;/g, '$');
    const regex = getDataTermsRegex();
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(unescaped)) !== null) {
      const matchIndex = match.index;
      const matchedText = match[0];

      // Add preceding plain text
      if (matchIndex > lastIndex) {
        parts.push(unescaped.substring(lastIndex, matchIndex));
      }

      const definition = findDataSource(matchedText);
      if (definition) {
        parts.push(
          <DataTermToken
            key={`term-${matchIndex}-${matchedText}`}
            term={matchedText}
            definition={definition}
          >
            {matchedText}
          </DataTermToken>
        );
      } else {
        parts.push(matchedText);
      }

      lastIndex = matchIndex + matchedText.length;
    }

    // Add trailing text
    if (lastIndex < unescaped.length) {
      parts.push(unescaped.substring(lastIndex));
    }

    return parts.length > 0 ? <>{parts}</> : unescaped;
  }

  // Process arrays of nodes
  if (Array.isArray(node)) {
    return React.Children.map(node, (child) => highlightDataTerms(child));
  }

  // Process React elements (e.g. <strong>, <em>, <span>) but skip KaTeX / code blocks
  if (React.isValidElement(node)) {
    // Do not highlight inside existing DataTermTokens or KaTeX math spans
    const props = node.props as { className?: string; children?: React.ReactNode };
    if (
      props?.className?.includes('katex') ||
      props?.className?.includes('math') ||
      node.type === DataTermToken
    ) {
      return node;
    }

    if (props?.children) {
      return React.cloneElement(
        node,
        undefined,
        highlightDataTerms(props.children)
      );
    }
  }

  return node;
}

export default highlightDataTerms;

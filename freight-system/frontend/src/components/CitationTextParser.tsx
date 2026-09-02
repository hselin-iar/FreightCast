import React from 'react';
import type { CitationItem } from '../lib/types';
import CitationToken from './CitationToken';

interface Props {
  text: string;
  citations: Record<string, CitationItem>;
}

/**
 * Parses markdown-like strings formatted as `[Token Text]{ref-id}`
 * into interactive <CitationToken> elements with hoverable evidence cards.
 */
export const CitationTextParser: React.FC<Props> = ({ text, citations }) => {
  // Regex to match [token]{citation_id}
  const regex = /\[(.*?)\]\{(ref-[a-zA-Z0-9_-]+)\}/g;
  const elements: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    const [fullMatch, tokenText, refId] = match;
    const matchIndex = match.index;

    // Push preceding plain text
    if (matchIndex > lastIndex) {
      elements.push(text.substring(lastIndex, matchIndex));
    }

    const citation = citations[refId];
    if (citation) {
      elements.push(
        <CitationToken key={`${refId}-${matchIndex}`} citation={citation}>
          {tokenText}
        </CitationToken>
      );
    } else {
      elements.push(<span key={`fallback-${matchIndex}`}>{tokenText}</span>);
    }

    lastIndex = matchIndex + fullMatch.length;
  }

  // Push any remaining text
  if (lastIndex < text.length) {
    elements.push(text.substring(lastIndex));
  }

  return <span>{elements}</span>;
};

export default CitationTextParser;

import React from 'react';

interface MarkdownTextProps {
    content: string;
    className?: string;
}

/**
 * Simple markdown renderer for chat messages.
 * Supports: **bold**, *italic*, `code`, line breaks, and numbered lists.
 */
const MarkdownText: React.FC<MarkdownTextProps> = ({ content, className = '' }) => {
    /**
     * Parse markdown text and return React elements
     */
    const parseMarkdown = (text: string): React.ReactNode[] => {
        // Split by lines first
        const lines = text.split('\n');
        const elements: React.ReactNode[] = [];
        let isInList = false;
        let listItems: React.ReactNode[] = [];

        lines.forEach((line, lineIndex) => {
            // Check for numbered list items (e.g., "1. ", "2. ")
            const listMatch = line.match(/^(\d+)\.\s+(.*)$/);

            if (listMatch) {
                // It's a list item
                if (!isInList) {
                    isInList = true;
                    listItems = [];
                }
                listItems.push(
                    <li key={`li-${lineIndex}`} className="ml-4 mb-2">
                        {parseInlineMarkdown(listMatch[2])}
                    </li>
                );
            } else {
                // Not a list item
                if (isInList && listItems.length > 0) {
                    // Close the previous list
                    elements.push(
                        <ol key={`ol-${lineIndex}`} className="list-decimal list-inside mb-3 space-y-1">
                            {listItems}
                        </ol>
                    );
                    isInList = false;
                    listItems = [];
                }

                // Check for headers (# Header)
                const headerMatch = line.match(/^(#{1,3})\s+(.*)$/);
                if (headerMatch) {
                    const level = headerMatch[1].length;
                    const headerText = parseInlineMarkdown(headerMatch[2]);
                    if (level === 1) {
                        elements.push(
                            <h2 key={`h-${lineIndex}`} className="text-lg font-bold mb-2 mt-3">
                                {headerText}
                            </h2>
                        );
                    } else if (level === 2) {
                        elements.push(
                            <h3 key={`h-${lineIndex}`} className="text-base font-semibold mb-2 mt-2">
                                {headerText}
                            </h3>
                        );
                    } else {
                        elements.push(
                            <h4 key={`h-${lineIndex}`} className="text-sm font-semibold mb-1 mt-1">
                                {headerText}
                            </h4>
                        );
                    }
                } else if (line.trim() === '') {
                    // Empty line - add spacing
                    elements.push(<div key={`br-${lineIndex}`} className="h-2" />);
                } else if (line.startsWith('- ')) {
                    // Bullet point
                    elements.push(
                        <div key={`bullet-${lineIndex}`} className="flex items-start mb-1 ml-2">
                            <span className="mr-2">•</span>
                            <span>{parseInlineMarkdown(line.slice(2))}</span>
                        </div>
                    );
                } else if (line.startsWith('| ')) {
                    // Table row - simplified rendering
                    const cells = line.split('|').filter(c => c.trim());
                    elements.push(
                        <div key={`table-${lineIndex}`} className="flex gap-4 text-sm py-1 border-b border-gray-200 dark:border-gray-600">
                            {cells.map((cell, i) => (
                                <span key={i} className="flex-1">{parseInlineMarkdown(cell.trim())}</span>
                            ))}
                        </div>
                    );
                } else {
                    // Regular text
                    elements.push(
                        <p key={`p-${lineIndex}`} className="mb-1">
                            {parseInlineMarkdown(line)}
                        </p>
                    );
                }
            }
        });

        // Handle remaining list items at end
        if (isInList && listItems.length > 0) {
            elements.push(
                <ol key="ol-final" className="list-decimal list-inside mb-3 space-y-1">
                    {listItems}
                </ol>
            );
        }

        return elements;
    };

    /**
     * Parse inline markdown (bold, italic, code)
     */
    const parseInlineMarkdown = (text: string): React.ReactNode => {
        // Pattern to match **bold**, *italic*, `code`, and emojis
        const parts: React.ReactNode[] = [];
        let remaining = text;
        let keyIndex = 0;

        while (remaining.length > 0) {
            // Check for **bold**
            const boldMatch = remaining.match(/\*\*([^*]+)\*\*/);
            // Check for *italic*
            const italicMatch = remaining.match(/(?<!\*)\*([^*]+)\*(?!\*)/);
            // Check for `code`
            const codeMatch = remaining.match(/`([^`]+)`/);

            // Find the earliest match
            const matches = [
                boldMatch ? { match: boldMatch, type: 'bold', index: remaining.indexOf(boldMatch[0]) } : null,
                italicMatch ? { match: italicMatch, type: 'italic', index: remaining.indexOf(italicMatch[0]) } : null,
                codeMatch ? { match: codeMatch, type: 'code', index: remaining.indexOf(codeMatch[0]) } : null,
            ].filter(m => m !== null).sort((a, b) => a!.index - b!.index);

            if (matches.length === 0 || matches[0]!.index === -1) {
                // No more matches, add remaining text
                if (remaining) {
                    parts.push(remaining);
                }
                break;
            }

            const firstMatch = matches[0]!;

            // Add text before the match
            if (firstMatch.index > 0) {
                parts.push(remaining.substring(0, firstMatch.index));
            }

            // Add the formatted element
            const matchText = firstMatch.match![1];
            if (firstMatch.type === 'bold') {
                parts.push(
                    <strong key={`bold-${keyIndex++}`} className="font-bold">
                        {matchText}
                    </strong>
                );
            } else if (firstMatch.type === 'italic') {
                parts.push(
                    <em key={`italic-${keyIndex++}`} className="italic">
                        {matchText}
                    </em>
                );
            } else if (firstMatch.type === 'code') {
                parts.push(
                    <code key={`code-${keyIndex++}`} className="bg-gray-200 dark:bg-gray-600 px-1 rounded text-sm font-mono">
                        {matchText}
                    </code>
                );
            }

            // Update remaining text
            remaining = remaining.substring(firstMatch.index + firstMatch.match![0].length);
        }

        return parts.length === 1 ? parts[0] : <>{parts}</>;
    };

    return (
        <div className={`markdown-content ${className}`}>
            {parseMarkdown(content)}
        </div>
    );
};

export default MarkdownText;

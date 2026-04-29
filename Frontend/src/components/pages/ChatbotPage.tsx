import React, { useEffect, useRef, useState } from 'react';
import { Bot, FileText, MessageSquare, Send, Trash2, User } from 'lucide-react';
import { apiService } from '../../services/api';
import { ChatMessage, LooseDocument } from '../../types';
import MarkdownText from '../MarkdownText';

const ChatbotPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [documents, setDocuments] = useState<LooseDocument[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadDocuments = async () => {
      try {
        const docs = await apiService.getLooseDocuments();
        setDocuments(docs.filter((doc) => doc.is_processed));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load processed documents');
      }
    };

    void loadDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      content: inputMessage,
      sender: 'user',
      timestamp: new Date().toISOString(),
    };

    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setInputMessage('');
    setIsLoading(true);
    setIsTyping(true);
    setError(null);

    try {
      const response = await apiService.queryDocuments(
        userMessage.content,
        selectedDocumentIds.length > 0 ? selectedDocumentIds : undefined
      );

      const assistantMessage: ChatMessage = {
        id: `${Date.now()}-assistant`,
        content: response.answer,
        sender: 'assistant',
        timestamp: new Date().toISOString(),
        contextFound: response.context_found,
        usedDocuments: response.used_documents,
      };

      setMessages([...nextMessages, assistantMessage]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed');
      setMessages([
        ...nextMessages,
        {
          id: `${Date.now()}-error`,
          content: 'Sorry, I encountered an error while querying the selected documents.',
          sender: 'assistant',
          timestamp: new Date().toISOString(),
          contextFound: false,
          usedDocuments: [],
        },
      ]);
    } finally {
      setIsLoading(false);
      setIsTyping(false);
    }
  };

  const clearChat = () => {
    if (window.confirm('Clear the current chat transcript?')) {
      setMessages([]);
      setError(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg p-6 border border-white/20 dark:border-gray-700/20">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">RAG Chat</h1>
            <p className="text-gray-600 dark:text-gray-300">Query processed loose documents through `/rag/query`.</p>
          </div>
          <button
            onClick={clearChat}
            className="flex items-center space-x-2 px-4 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            type="button"
          >
            <Trash2 className="h-4 w-4" />
            <span>Clear Chat</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <p className="text-sm text-error-700 dark:text-error-300">{error}</p>
        </div>
      )}

      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg p-6 border border-white/20 dark:border-gray-700/20">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Document Scope</h2>
        {documents.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No processed loose documents are available yet. Upload and process documents in the Documents page first.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {documents.map((doc) => {
              const checked = selectedDocumentIds.includes(doc.id);
              return (
                <label
                  key={doc.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${
                    checked
                      ? 'border-primary-500 bg-primary-50 dark:border-primary-400 dark:bg-primary-900/20'
                      : 'border-gray-200 dark:border-white/10'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4"
                    checked={checked}
                    onChange={(event) => {
                      setSelectedDocumentIds((current) =>
                        event.target.checked
                          ? [...current, doc.id]
                          : current.filter((id) => id !== doc.id)
                      );
                    }}
                  />
                  <div className="min-w-0">
                    <p className="break-all text-sm font-medium text-gray-900 dark:text-white">{doc.filename}</p>
                    <p className="mt-1 break-all text-xs text-gray-500 dark:text-gray-400">{doc.id}</p>
                  </div>
                </label>
              );
            })}
          </div>
        )}
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Leave all boxes unchecked to search across every processed loose document.
        </p>
      </div>

      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg border border-white/20 dark:border-gray-700/20 flex flex-col h-[600px]">
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
              <div className="text-center">
                <MessageSquare className="h-16 w-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
                <p className="text-lg font-medium">Ask a question</p>
                <p className="text-sm mt-1 max-w-xs mx-auto">
                  Ask about the selected documents, or leave the scope empty to search all processed documents.
                </p>
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div key={message.id} className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-xs lg:max-w-md px-4 py-2 rounded-2xl ${
                    message.sender === 'user'
                      ? 'bg-blue-600 dark:bg-blue-500 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                  }`}
                >
                  <div className="flex items-start space-x-2">
                    {message.sender === 'assistant' ? (
                      <Bot className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                    ) : (
                      <User className="h-5 w-5 text-blue-100 mt-0.5 flex-shrink-0" />
                    )}
                    <div className="flex-1">
                      {message.sender === 'assistant' ? (
                        <MarkdownText content={message.content} className="text-sm" />
                      ) : (
                        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                      )}

                      {message.sender === 'assistant' && (
                        <div className="mt-2">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                              message.contextFound
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                            }`}
                          >
                            {message.contextFound ? 'Context found' : 'No matching context'}
                          </span>
                        </div>
                      )}

                      {message.sender === 'assistant' && message.usedDocuments && message.usedDocuments.length > 0 && (
                        <div className="mt-2 flex items-center gap-1 flex-wrap">
                          {message.usedDocuments.map((docId) => (
                            <span
                              key={docId}
                              className="flex items-center gap-1 text-[10px] bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded-full border border-blue-100 dark:border-blue-800"
                            >
                              <FileText className="h-2 w-2" />
                              {docId}
                            </span>
                          ))}
                        </div>
                      )}

                      <p
                        className={`text-xs mt-1 ${
                          message.sender === 'user' ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
                        }`}
                      >
                        {new Date(message.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}

          {isTyping && (
            <div className="flex justify-start">
              <div className="max-w-xs lg:max-w-md px-4 py-2 rounded-2xl bg-gray-100 dark:bg-gray-700">
                <div className="flex items-center space-x-2">
                  <Bot className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="p-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-4">
            <div className="flex-1 relative">
              <textarea
                value={inputMessage}
                onChange={(event) => setInputMessage(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSendMessage();
                  }
                }}
                placeholder="Ask a question about the selected documents..."
                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                rows={2}
                disabled={isLoading}
              />
            </div>
            <button
              onClick={() => void handleSendMessage()}
              disabled={isLoading || !inputMessage.trim()}
              className="px-6 py-3 bg-blue-600 dark:bg-blue-500 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center space-x-2"
              type="button"
            >
              {isLoading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              ) : (
                <Send className="h-5 w-5" />
              )}
              <span>Send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatbotPage;


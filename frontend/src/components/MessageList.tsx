'use client';

import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
}

export default function MessageList({ messages, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-6">
        {messages.map((message) => (
          <div key={message.id} className={`message-container ${message.sender === 'user' ? 'user-message' : ''}`}>
            {message.sender === 'user' ? (
              <div className="user-bubble">
                <div className="user-text">
                  {message.content}
                </div>
              </div>
            ) : (
              <div className="assistant-message">
                <ReactMarkdown
                  components={{
                    h1: ({children}) => <h1 className="md-heading-1">{children}</h1>,
                    h2: ({children}) => <h2 className="md-heading-2">{children}</h2>,
                    h3: ({children}) => <h3 className="md-heading-3">{children}</h3>,
                    p: ({children}) => <p className="md-paragraph">{children}</p>,
                    ul: ({children}) => <ul className="md-list-unordered">{children}</ul>,
                    ol: ({children}) => <ol className="md-list-ordered">{children}</ol>,
                    li: ({children}) => <li className="md-list-item">{children}</li>,
                    strong: ({children}) => <strong className="md-strong">{children}</strong>,
                    code: ({children}) => <code className="md-code-inline">{children}</code>,
                    pre: ({children}) => <pre className="md-code-block">{children}</pre>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
        
        {isLoading && (
          <div className="loading-container">
            <div className="loading-content">
              <div className="loading-indicator">
                <div className="loading-dots">
                  <div className="loading-dot"></div>
                  <div className="loading-dot" style={{ animationDelay: '0.1s' }}></div>
                  <div className="loading-dot" style={{ animationDelay: '0.2s' }}></div>
                </div>
                <span className="loading-text">VibeDining is thinking...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
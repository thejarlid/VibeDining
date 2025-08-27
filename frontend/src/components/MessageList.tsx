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
        {messages.map((message, index) => (
          <div key={message.id} className={`mb-6 ${message.sender === 'user' ? 'flex justify-end' : ''}`}>
            {message.sender === 'user' ? (
              <div className="max-w-[80%] bg-gray-100 dark:bg-[#2f2f2f] rounded-2xl rounded-br-md px-5 py-3 text-gray-900 dark:text-white">
                <div className="whitespace-pre-wrap leading-relaxed text-sm">
                  {message.content}
                </div>
              </div>
            ) : (
              <div className="w-full prose prose-gray dark:prose-invert max-w-none leading-relaxed text-gray-900 dark:text-white">
                <ReactMarkdown
                  components={{
                    h1: ({children}) => <h1 className="text-2xl font-semibold mb-4 mt-6 text-gray-900 dark:text-white">{children}</h1>,
                    h2: ({children}) => <h2 className="text-xl font-semibold mb-3 mt-5 text-gray-900 dark:text-white">{children}</h2>,
                    h3: ({children}) => <h3 className="text-lg font-semibold mb-2 mt-4 text-gray-900 dark:text-white">{children}</h3>,
                    p: ({children}) => <p className="mb-4 text-gray-900 dark:text-white leading-relaxed">{children}</p>,
                    ul: ({children}) => <ul className="mb-4 ml-6 list-disc text-gray-900 dark:text-white">{children}</ul>,
                    ol: ({children}) => <ol className="mb-4 ml-6 list-decimal text-gray-900 dark:text-white">{children}</ol>,
                    li: ({children}) => <li className="mb-1 text-gray-900 dark:text-white">{children}</li>,
                    strong: ({children}) => <strong className="font-semibold text-gray-900 dark:text-white">{children}</strong>,
                    code: ({children}) => <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm font-mono text-gray-900 dark:text-gray-100">{children}</code>,
                    pre: ({children}) => <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg mb-4 overflow-x-auto text-sm font-mono text-gray-900 dark:text-gray-100">{children}</pre>,
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
        
        {isLoading && (
          <div className="mb-6">
            <div className="w-full">
              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                <div className="flex space-x-1">
                  <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
                <span className="text-sm">VibeDining is thinking...</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
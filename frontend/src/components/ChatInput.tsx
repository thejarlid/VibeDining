'use client';

import { useState, useRef, useEffect } from 'react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
  isInitial?: boolean;
}

export default function ChatInput({ onSendMessage, disabled, isInitial = false }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [message]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || disabled) return;
    
    onSendMessage(message.trim());
    setMessage('');
    
    // Reset height after sending
    setTimeout(() => {
      adjustTextareaHeight();
    }, 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
  };

  // Calculate if we should show more rounded corners based on height
  const currentHeight = textareaRef.current?.scrollHeight || 48;
  const isExpanded = currentHeight > 60;
  const borderRadius = isExpanded ? '20px' : '24px';
  
  // Position button differently for single line vs expanded
  const buttonPosition = isInitial && !isExpanded 
    ? 'right-2 top-1/2 -translate-y-1/2' 
    : 'right-2 bottom-2';

  return (
    <div className={`${isInitial ? 'p-0' : 'p-4 bg-white dark:bg-[#0f0f0f] border-t border-gray-200/60 dark:border-gray-800/60'}`}>
      <form onSubmit={handleSubmit} className={`${isInitial ? 'max-w-3xl' : 'max-w-3xl'} mx-auto`}>
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isInitial ? "Ask anything" : "Message VibeDining"}
            disabled={disabled}
            className={`w-full ${isInitial ? 'pl-4 pr-12 py-3' : 'p-4 pr-12'} border border-gray-300/60 dark:border-gray-700/60 bg-white dark:bg-[#1f1f1f] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 resize-none focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600 focus:border-transparent disabled:opacity-50 transition-all duration-200 shadow-lg ${
              isInitial ? 'text-base' : 'text-base'
            } overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600 scrollbar-track-transparent`}
            rows={1}
            style={{ 
              minHeight: isInitial ? '48px' : '52px', 
              maxHeight: '200px',
              borderRadius: isInitial ? borderRadius : '16px'
            }}
          />
          <button
            type="submit"
            disabled={!message.trim() || disabled}
            className={`absolute ${isInitial ? buttonPosition : 'right-3 bottom-3'} p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:text-gray-300 dark:disabled:text-gray-600 disabled:hover:text-gray-300 dark:disabled:hover:text-gray-600 transition-all duration-200 ${
              isInitial ? 'rounded-full hover:bg-gray-100 dark:hover:bg-gray-800' : ''
            }`}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round" 
              strokeLinejoin="round"
            >
              <path d="M22 2L11 13"/>
              <path d="M22 2L15 22L11 13L2 9L22 2Z"/>
            </svg>
          </button>
        </div>
      </form>
    </div>
  );
}
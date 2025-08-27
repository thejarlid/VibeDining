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

  // Get CSS classes based on state
  const containerClass = isInitial ? 'input-container-initial' : 'input-container';
  const textareaClass = `input-textarea ${isInitial ? 'input-textarea-initial' : 'input-textarea-chat'}`;
  
  let buttonClass = 'input-send-btn';
  if (isInitial) {
    buttonClass += isExpanded ? ' input-send-btn-bottom' : ' input-send-btn-initial-centered';
  } else {
    buttonClass += ' input-send-btn-chat';
  }

  return (
    <div className={containerClass}>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isInitial ? "Ask anything" : "Message VibeDining"}
            disabled={disabled}
            className={textareaClass}
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
            className={buttonClass}
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
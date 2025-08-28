'use client';

import { useState, useEffect } from 'react';
import Header from './Header';
import MessageList from './MessageList';
import ChatInput from './ChatInput';

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);

  const handleSendMessage = async (content: string) => {
    const newMessage: Message = {
      id: Date.now().toString(),
      content,
      sender: 'user',
      timestamp: new Date(),
    };

    // Start transition animation if this is the first message
    if (messages.length === 0) {
      setIsTransitioning(true);
      // Add the message after a short delay to allow animation to start
      setTimeout(() => {
        setMessages([newMessage]);
        setIsLoading(true);
      }, 100);
    } else {
      setMessages(prev => [...prev, newMessage]);
      setIsLoading(true);
    }

    // TODO: Add restaurant agent API call here
    // This should call the backend API to get the restaurant recommendations
    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: `I'd be happy to help you find great restaurants! Based on your request "${content}", here are some recommendations...`,
        sender: 'assistant',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1000);
  };

  const handleNewChat = () => {
    setMessages([]);
    setIsTransitioning(false);
  };

  const hasMessages = messages.length > 0;

  // Handle transition timing
  useEffect(() => {
    if (isTransitioning) {
      const timer = setTimeout(() => {
        setIsTransitioning(false);
      }, 600); // Match animation duration (reduced from 800ms to 600ms)
      return () => clearTimeout(timer);
    }
  }, [isTransitioning]);

  return (
    <div className="chat-container">
      <Header onNewChat={handleNewChat} />

      <div className="chat-content">
        {/* Welcome Screen */}
        {!hasMessages && !isTransitioning && (
          <div className="welcome-screen">
            <div className="welcome-content">
              <div className="welcome-text">
                <h1 className="welcome-title">
                  VibeDining
                </h1>
                <p className="welcome-subtitle">
                  How can I help you discover amazing restaurants today?
                </p>
              </div>
              <div>
                <ChatInput
                  onSendMessage={handleSendMessage}
                  disabled={isLoading}
                  isInitial={true}
                />
              </div>
            </div>
          </div>
        )}

        {/* Transition Animation - Pill sliding down */}
        {isTransitioning && (
          <div className="transition-container">
            <div className="transition-input-wrapper">
              <ChatInput
                onSendMessage={() => { }} // Disabled during transition
                disabled={true}
                isInitial={true}
              />
            </div>
          </div>
        )}

        {/* Chat Interface - appears instantly after animation */}
        {hasMessages && !isTransitioning && (
          <div className="chat-interface">
            <MessageList messages={messages} isLoading={isLoading} />
            <ChatInput
              onSendMessage={handleSendMessage}
              disabled={isLoading}
              isInitial={true}
            />
          </div>
        )}
      </div>
    </div>
  );
}
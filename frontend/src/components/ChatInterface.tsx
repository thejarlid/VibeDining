'use client';

import { useState, useEffect } from 'react';
import Header from './Header';
import MessageList from './MessageList';
import ChatInput from './ChatInput';
import { useChat } from '../hooks/useChat';

export default function ChatInterface() {
  const { messages, isLoading, error, sendChatMessage, clearMessages } = useChat();
  const [isTransitioning, setIsTransitioning] = useState(false);

  const handleSendMessage = async (content: string) => {
    // Start transition animation of the pill box down if this is the first message
    if (messages.length === 0) {
      setIsTransitioning(true);
      // Add the message after a short delay to allow animation to start
      setTimeout(() => {
        sendChatMessage(content);
      }, 100);
    } else {
      sendChatMessage(content);
    }
  };

  const handleNewChat = async () => {
    await clearMessages();
    setIsTransitioning(false);
  };

  const hasMessages = messages.length > 0;

  // Handle transition timing
  useEffect(() => {
    if (isTransitioning) {
      const timer = setTimeout(() => {
        setIsTransitioning(false);
      }, 600); // Match animation duration 
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
                  VibeDine
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

        {/* Error Display */}
        {error && (
          <div className="error-message">
            Error: {error}
          </div>
        )}
      </div>
    </div>
  );
}

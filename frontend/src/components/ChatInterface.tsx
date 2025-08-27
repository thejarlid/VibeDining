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
      console.log('Starting transition animation');
      setIsTransitioning(true);
      // Add the message after a short delay to allow animation to start
      setTimeout(() => {
        console.log('Adding message after delay');
        setMessages([newMessage]);
        setIsLoading(true);
      }, 100);
    } else {
      setMessages(prev => [...prev, newMessage]);
      setIsLoading(true);
    }

    // TODO(human): Add your restaurant agent API call here
    // This should call your backend API to get the restaurant recommendations
    // Replace this with actual API integration
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
    <div className="flex flex-col h-screen bg-white dark:bg-[#0f0f0f] transition-colors">
      <Header onNewChat={handleNewChat} />
      
      <div className="flex-1 flex flex-col relative overflow-hidden">
        {/* Welcome Screen */}
        {!hasMessages && !isTransitioning && (
          <div className="flex-1 flex items-center justify-center px-4">
            <div className="w-full max-w-4xl mx-auto">
              <div className="text-center mb-16">
                <h1 className="text-4xl font-normal text-gray-900 dark:text-white mb-4">
                  VibeDining
                </h1>
                <p className="text-gray-500 dark:text-gray-300 text-lg">
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
          <div className="flex-1 flex flex-col justify-end animate-[slideToBottom_0.6s_ease-out_forwards]">
            <div className="p-4">
              <ChatInput 
                onSendMessage={() => {}} // Disabled during transition
                disabled={true}
                isInitial={true}
              />
            </div>
          </div>
        )}

        {/* Chat Interface - appears instantly after animation */}
        {hasMessages && !isTransitioning && (
          <div className="flex flex-col h-full">
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
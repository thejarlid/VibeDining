import { useState, useCallback } from 'react';
import { sendMessage, endSession, ChatMessage, ChatAPIError } from '../lib/api/chat';

export const useChat = () => {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);

    const sendChatMessage = useCallback(async (content: string) => {
        // Add user message immediately for better UX
        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            content,
            sender: 'user',
            timestamp: new Date(),
        };

        setMessages(prev => [...prev, userMessage]);
        setIsLoading(true);
        setError(null);

        try {
            const response = await sendMessage({
                content,
                session_id: sessionId || undefined
            });

            // Update session ID if this was the first message
            if (!sessionId) {
                setSessionId(response.session_id);
            }

            // Add assistant message from API response
            const assistantMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                content: response.response,
                sender: 'assistant',
                timestamp: new Date(),
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (err) {
            const errorMessage = err instanceof ChatAPIError
                ? err.message
                : 'Failed to send message';
            setError(errorMessage);

            // Optionally remove the user message if the API call failed
            // setMessages(prev => prev.filter(msg => msg.id !== userMessage.id));

            // Or add an error message
            const errorMsg: ChatMessage = {
                id: (Date.now() + 1).toString(),
                content: 'Sorry, I encountered an error. Please try again.',
                sender: 'assistant',
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const clearMessages = useCallback(async () => {
        // Clean up current session before starting new one
        if (sessionId) {
            try {
                await endSession(sessionId);
            } catch (error) {
                console.warn('Failed to clean up session:', error);
            }
        }

        setMessages([]);
        setError(null);
        setSessionId(null);
    }, [sessionId]);

    return {
        messages,
        isLoading,
        error,
        sessionId,
        sendChatMessage,
        clearMessages,
    };
}; 
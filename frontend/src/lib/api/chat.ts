// Client-side API service for chat functionality
export interface ChatMessage {
    id: string;
    content: string;
    sender: 'user' | 'assistant';
    timestamp: Date;
}

export interface SendMessageRequest {
    content: string;
    session_id?: string;
}

export interface SendMessageResponse {
    message: ChatMessage;
    session_id: string;
}

export interface ApiChatMessage {
    id?: string;
    content: string;
    sender: 'user' | 'assistant';
    timestamp?: string | number;
}

export class ChatAPIError extends Error {
    constructor(message: string, public status?: number) {
        super(message);
        this.name = 'ChatAPIError';
    }
}

export const endSession = async (sessionId: string): Promise<void> => {
    try {
        await fetch('/api/session', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ session_id: sessionId }),
        });
    } catch (error) {
        console.warn('Failed to end session:', error);
    }
};

export const sendMessage = async (request: SendMessageRequest): Promise<SendMessageResponse> => {
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                content: request.content,
                session_id: request.session_id
            }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new ChatAPIError(
                errorData.error || `API request failed: ${response.statusText}`,
                response.status
            );
        }

        const data = await response.json();

        // Convert timestamp string back to Date object if needed
        const message = {
            ...data.message,
            timestamp: new Date(data.message.timestamp)
        };

        return {
            message,
            session_id: data.session_id
        };
    } catch (error) {
        if (error instanceof ChatAPIError) {
            throw error;
        }
        throw new ChatAPIError(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
};

// Utility function to format API response
export const formatChatMessage = (apiResponse: ApiChatMessage): ChatMessage => {
    return {
        id: apiResponse.id || Date.now().toString(),
        content: apiResponse.content,
        sender: apiResponse.sender,
        timestamp: new Date(apiResponse.timestamp || Date.now()),
    };
};
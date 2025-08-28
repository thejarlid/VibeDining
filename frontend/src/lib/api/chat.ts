// Client-side API service for chat functionality
export interface ChatMessage {
    id: string;
    content: string;
    sender: 'user' | 'assistant';
    timestamp: Date;
}

export interface SendMessageRequest {
    content: string;
}

export interface SendMessageResponse {
    message: ChatMessage;
    // Add any other response fields from your backend
}

export class ChatAPIError extends Error {
    constructor(message: string, public status?: number) {
        super(message);
        this.name = 'ChatAPIError';
    }
}

export const sendMessage = async (request: SendMessageRequest): Promise<SendMessageResponse> => {
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(request),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new ChatAPIError(
                errorData.error || `API request failed: ${response.statusText}`,
                response.status
            );
        }

        const data = await response.json();
        return data;
    } catch (error) {
        if (error instanceof ChatAPIError) {
            throw error;
        }
        throw new ChatAPIError(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
};

// Utility function to format API response
export const formatChatMessage = (apiResponse: any): ChatMessage => {
    return {
        id: apiResponse.id || Date.now().toString(),
        content: apiResponse.content,
        sender: apiResponse.sender,
        timestamp: new Date(apiResponse.timestamp || Date.now()),
    };
}; 
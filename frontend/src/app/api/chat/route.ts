import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();

        // Validate request
        if (!body.content || typeof body.content !== 'string') {
            return NextResponse.json(
                { error: 'Content is required and must be a string' },
                { status: 400 }
            );
        }

        // Call your Railway backend
        const baseUrl = process.env.RAILWAY_API_URL || 'http://localhost:8000';
        const railwayApiKey = process.env.RAILWAY_API_KEY;

        if (!railwayApiKey) {
            console.error('RAILWAY_API_KEY environment variable is not set');
            return NextResponse.json(
                { error: 'Server configuration error' },
                { status: 500 }
            );
        }

        // Ensure URL has protocol
        const railwayUrl = baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`;

        const response = await fetch(`${railwayUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': railwayApiKey,
            },
            body: JSON.stringify({
                query: body.content,
                // Add any other fields your backend expects
            }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Railway backend error:', response.status, errorText);

            return NextResponse.json(
                { error: `Backend error: ${response.status} - ${errorText}` },
                { status: response.status }
            );
        }

        const data = await response.json();

        // Transform the response if needed
        return NextResponse.json({
            message: {
                id: Date.now().toString(),
                content: data.response || data.message || 'No response from backend',
                sender: 'assistant',
                timestamp: new Date().toISOString(),
            },
            // Include any additional data from your backend
            ...data,
        });

    } catch (error) {
        console.error('API route error:', error);

        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
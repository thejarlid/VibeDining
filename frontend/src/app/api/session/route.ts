import { NextRequest, NextResponse } from 'next/server';

export async function DELETE(request: NextRequest) {
    try {
        const body = await request.json();
        const { session_id } = body;

        if (!session_id) {
            return NextResponse.json(
                { error: 'Session ID is required' },
                { status: 400 }
            );
        }

        // Get backend URL and API key
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

        // Forward DELETE request to FastAPI backend with session_id in URL path
        const response = await fetch(`${railwayUrl}/session/${session_id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': railwayApiKey,
            },
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Backend session delete error:', response.status, errorText);
            return NextResponse.json(
                { error: `Backend error: ${response.status}` },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);

    } catch (error) {
        console.error('Session API route error:', error);
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
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

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 150000); // 2.5 minutes

        const response = await fetch(`${railwayUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': railwayApiKey,
            },
            body: JSON.stringify({
                query: body.content,
                session_id: body.session_id,
                location_context: body.location_context,
            }),
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Railway backend error:', response.status, errorText);

            return NextResponse.json(
                { error: `Backend error: ${response.status} - ${errorText}` },
                { status: response.status }
            );
        }

        const data = await response.json();

        // Return fully formed ChatMessage object
        return NextResponse.json({
            message: {
                id: Date.now().toString(),
                content: data.response || 'No response from backend',
                sender: 'assistant' as const,
                timestamp: new Date(), // Frontend expects Date object, not string
            },
            session_id: data.session_id,
        });

    } catch (error) {
        console.error('API route error:', error);

        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
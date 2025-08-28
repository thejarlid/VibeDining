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
        const railwayUrl = process.env.RAILWAY_API_URL || 'http://localhost:8000';
        const response = await fetch(`${railwayUrl}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // Add any authentication headers your backend needs
                // 'Authorization': `Bearer ${process.env.RAILWAY_API_KEY}`,
            },
            body: JSON.stringify({
                content: body.content,
                // Add any other fields your backend expects
            }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Railway backend error:', response.status, errorText);

            return NextResponse.json(
                { error: 'Backend service unavailable' },
                { status: 503 }
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

// Optional: Add a health check endpoint
export async function GET() {
    try {
        const railwayUrl = process.env.RAILWAY_API_URL || 'http://localhost:8000';
        const response = await fetch(`${railwayUrl}/health`, {
            method: 'GET',
        });

        if (response.ok) {
            return NextResponse.json({ status: 'healthy' });
        } else {
            return NextResponse.json({ status: 'unhealthy' }, { status: 503 });
        }
    } catch (error) {
        return NextResponse.json({ status: 'unhealthy' }, { status: 503 });
    }
} 
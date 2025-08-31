# VibeDining Frontend

## Overview

Modern chat interface for AI-powered restaurant recommendations built with Next.js 15, React 19, and TypeScript. Features real-time conversations with LangGraph agents through a clean, responsive UI.

## 🛠️ Tech Stack

- **Framework**: Next.js 15 with App Router + Turbopack
- **Language**: TypeScript 5
- **Styling**: Tailwind CSS 4
- **UI Components**: React 19 with Server Components
- **Markdown**: react-markdown for rich text rendering
- **Linting**: ESLint 9 with Next.js config

## 🏗️ Architecture

```
src/
├── app/                    # Next.js App Router
│   ├── api/               # API route handlers
│   │   ├── chat/          # Chat API endpoint
│   │   └── session/       # Session management
│   ├── layout.tsx         # Root layout with providers
│   ├── page.tsx          # Home page with chat interface
│   └── globals.css       # Global styles + Tailwind
│
├── components/            # React components
│   ├── ChatInterface.tsx  # Main chat container
│   ├── ChatInput.tsx     # Message input component  
│   ├── MessageList.tsx   # Chat message display
│   └── Header.tsx        # App header/navigation
│
├── hooks/                # Custom React hooks
│   └── useChat.ts       # Chat state management
│
└── lib/                  # Utility functions
    └── api/
        └── chat.ts       # API client functions
```

## 🚀 Getting Started

### Prerequisites
- Node.js 18+
- npm, yarn, or pnpm

### Installation
```bash
# Install dependencies
npm install

# Start development server with Turbopack
npm run dev
```

### Environment Variables
Create `.env.local`:
```bash
# Backend API endpoint
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Available Scripts
```bash
npm run dev      # Start dev server with Turbopack
npm run build    # Build for production with Turbopack
npm run start    # Start production server
npm run lint     # Run ESLint
```

## 📱 Key Features

### Real-time Chat Interface
- Streaming responses from AI agents
- Markdown rendering for rich restaurant recommendations
- Session persistence across page reloads
- Responsive design for mobile and desktop

### API Integration
- RESTful communication with FastAPI backend
- Session management for conversation continuity
- Error handling and loading states
- Type-safe API client with TypeScript

### User Experience
- Clean, minimal chat UI inspired by modern messaging apps
- Auto-scrolling message list
- Input validation and submission handling
- Loading indicators and error states

## 🔧 Development

### Component Structure
Each component follows consistent patterns:
```tsx
// Modern React component with TypeScript
interface ComponentProps {
  // Props with clear types
}

export function Component({ prop }: ComponentProps) {
  // Local state with React hooks
  // Event handlers
  // JSX with Tailwind classes
}
```

### State Management
- **Local State**: React useState for component-specific state
- **Chat State**: Custom useChat hook for conversation management
- **Server State**: API calls with error boundaries
- **Session State**: Browser localStorage for persistence

### Styling Guidelines
- **Tailwind CSS 4**: Utility-first styling with modern features
- **Responsive Design**: Mobile-first approach with breakpoint prefixes
- **Design System**: Consistent spacing, colors, and typography
- **Dark Mode Ready**: CSS variables for theme switching

## 🧩 Component Guide

### ChatInterface.tsx
Main chat container that orchestrates the entire conversation flow:
- Manages chat state with useChat hook
- Renders MessageList and ChatInput components
- Handles session loading and error states

### MessageList.tsx  
Displays conversation history with rich formatting:
- Maps through message array with proper keys
- Renders user messages and AI responses differently
- Auto-scrolls to latest message on updates
- Uses react-markdown for AI response formatting

### ChatInput.tsx
Handles user message input and submission:
- Form validation and submission handling
- Auto-focus and enter key submission
- Loading state management during API calls
- Clear input on successful submission

### useChat.ts Hook
Custom hook managing all chat state:
```tsx
const {
  messages,        // Array of conversation messages
  sendMessage,     // Function to send new message
  isLoading,       // Loading state for API calls
  error,           // Error state for failed requests
  clearChat        // Function to reset conversation
} = useChat();
```

## 🔗 API Integration

### Chat Endpoint (`/api/chat`)
```tsx
// POST /api/chat
interface ChatRequest {
  message: string;
  sessionId?: string;
}

interface ChatResponse {
  response: string;
  sessionId: string;
}
```

### Session Endpoint (`/api/session`)
```tsx  
// GET /api/session/:id
// Returns conversation history for session
```

## 🎨 Styling & Theming

### Tailwind Configuration
```javascript
// tailwind.config.js uses Tailwind CSS 4
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // Custom design tokens
    }
  }
}
```

### Color Palette
- **Primary**: Blue tones for interactive elements
- **Secondary**: Gray scale for text and backgrounds  
- **Accent**: Green for success states
- **Error**: Red for error states

## 🚀 Production Deployment

### Build Process
```bash
# Build with Turbopack optimization
npm run build

# Start production server
npm start
```

### Deployment Options
- **Vercel**: Zero-config deployment (recommended)
- **Docker**: Containerized deployment with multi-stage builds
- **Static Export**: Generate static files for CDN hosting

### Performance Considerations
- **Turbopack**: Ultra-fast builds and hot reloading
- **Code Splitting**: Automatic route-based splitting
- **Image Optimization**: Next.js built-in image optimization
- **Bundle Analysis**: Use `@next/bundle-analyzer`

## 🧪 Testing (Future)

### Recommended Testing Stack
```bash
# Test framework suggestions
npm install --save-dev jest @testing-library/react @testing-library/jest-dom
npm install --save-dev playwright  # For e2e testing
```

### Testing Patterns
- **Unit Tests**: Component logic and utilities
- **Integration Tests**: API interactions and hooks
- **E2E Tests**: Full user workflows with Playwright

## 🎯 Development Workflow

### Code Quality
- **TypeScript**: Strict mode enabled for type safety
- **ESLint**: Next.js recommended rules + custom rules
- **Prettier**: Code formatting (to be configured)
- **Husky**: Git hooks for quality gates (to be added)

### Best Practices
- Use Server Components where possible for better performance
- Implement proper error boundaries for production resilience
- Follow Next.js conventions for file organization
- Write semantic, accessible HTML with proper ARIA labels

This frontend provides a solid foundation for the VibeDining chat interface with modern React patterns, excellent developer experience, and production-ready architecture.

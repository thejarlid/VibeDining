interface HeaderProps {
  onNewChat: () => void;
}

export default function Header({ onNewChat }: HeaderProps) {
  return (
    <header className="header-container">
      <div className="header-logo">
        <h1 className="header-title">
          VibeDining
        </h1>
      </div>

      <button
        onClick={onNewChat}
        className="header-new-chat-btn"
      >
        {/* SVG Plus Icon:
            M12 5v14 - Move to (12,5) and draw vertical line down 14 units
            M5 12h14 - Move to (5,12) and draw horizontal line right 14 units */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        New chat
      </button>
    </header>
  );
}
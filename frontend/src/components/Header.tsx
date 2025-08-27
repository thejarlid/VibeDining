interface HeaderProps {
  onNewChat: () => void;
}

export default function Header({ onNewChat }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200/60 dark:border-gray-800/60 bg-white/80 dark:bg-[#0f0f0f]/80 backdrop-blur-sm">
      <div className="flex items-center">
        <h1 className="text-lg font-medium text-gray-900 dark:text-white">
          VibeDining
        </h1>
      </div>
      
      <button
        onClick={onNewChat}
        className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1f1f1f] rounded-lg transition-colors border border-gray-200 dark:border-gray-800"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        New chat
      </button>
    </header>
  );
}